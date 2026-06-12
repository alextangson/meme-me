"""设备权益与裂变账本 — 定价方案（docs/specs/2026-06-12-pricing-growth.md）的执行层。

无账号体系：设备 = 浏览器 localStorage 里的 uuid，随 API 调用上报。
权益落盘 devices_dir/{id}.json（out/ 是部署排除的持久层，与 job 数据同寿命）。
清 localStorage 可重置免费额度——v1 接受；真正的硬护栏是全局并发与上游预算。

定价三层：免费（每日限额 + 视频尝鲜 1 条）/ ¥9.9 unlocked / ¥29.9 custom。
裂变：邀请人在被邀设备首次生成成功时得视频额度，设备终身有上限。
变现通道是兑换码：人工收款过渡，将来接正式支付只是把发码自动化。
"""

import json
import re
import secrets
import threading
import time
from os import environ
from pathlib import Path

# 额度旋钮全部环境变量可调——调定价不用改代码
FREE_DAILY = int(environ.get("MEMEME_FREE_DAILY", "3"))
PAID_DAILY = int(environ.get("MEMEME_PAID_DAILY", "10"))
# 单张重摇也是真实出图（抽卡的无底洞），按日限次
FREE_RETRY_DAILY = int(environ.get("MEMEME_FREE_RETRY_DAILY", "8"))
PAID_RETRY_DAILY = int(environ.get("MEMEME_PAID_RETRY_DAILY", "30"))
FREE_VIDEO_CREDITS = int(environ.get("MEMEME_FREE_VIDEO_CREDITS", "1"))
REFERRAL_REWARD = int(environ.get("MEMEME_REFERRAL_REWARD", "2"))
REFERRAL_CAP = int(environ.get("MEMEME_REFERRAL_CAP", "10"))
PLAN_VIDEO_CREDITS = {
    "unlocked": int(environ.get("MEMEME_UNLOCK_VIDEO_CREDITS", "6")),
    "custom": int(environ.get("MEMEME_CUSTOM_VIDEO_CREDITS", "15")),
}
_PLAN_RANK = {"free": 0, "unlocked": 1, "custom": 2}

_DEVICE_RE = re.compile(r"[A-Za-z0-9_-]{8,64}")
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # 去掉易混的 0O1IL


def valid_device(device: str) -> bool:
    return bool(_DEVICE_RE.fullmatch(device or ""))


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _new_record(device: str) -> dict:
    return {
        "device": device,
        "plan": "free",
        "video_credits": FREE_VIDEO_CREDITS,
        "daily": {"date": _today(), "count": 0},
        "jobs_done": 0,
        "referred_by": "",
        "referral_earned": 0,
        "redeemed": [],
        "created_at": time.time(),
    }


class Store:
    """单进程文件存储：与 jobs/events 同一持久化哲学，够用到接正式支付。"""

    def __init__(self, devices_dir: Path, codes_file: Path):
        self.devices_dir = devices_dir
        self.codes_file = codes_file
        self._lock = threading.Lock()

    # ---- 设备记录 ----

    def _path(self, device: str) -> Path:
        return self.devices_dir / f"{device}.json"

    def _load(self, device: str) -> dict:
        path = self._path(device)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                pass  # 损坏的记录按新设备处理，别让一个坏文件挡住生成
        return _new_record(device)

    def _save(self, rec: dict) -> None:
        self.devices_dir.mkdir(parents=True, exist_ok=True)
        self._path(rec["device"]).write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8"
        )

    def _daily_limit(self, rec: dict) -> int:
        return PAID_DAILY if rec["plan"] != "free" else FREE_DAILY

    def _rollover(self, rec: dict) -> None:
        if rec["daily"].get("date") != _today():
            rec["daily"] = {"date": _today(), "count": 0, "retries": 0}

    def plan(self, device: str) -> str:
        with self._lock:
            return self._load(device)["plan"]

    def snapshot(self, device: str) -> dict:
        """只读视图给 /api/me——不落盘，看一眼不该创建记录。"""
        with self._lock:
            rec = self._load(device)
            self._rollover(rec)
            retry_limit = (
                PAID_RETRY_DAILY if rec["plan"] != "free" else FREE_RETRY_DAILY
            )
            return {
                "plan": rec["plan"],
                "video_credits": rec["video_credits"],
                "daily_remaining": max(
                    0, self._daily_limit(rec) - rec["daily"]["count"]
                ),
                "retry_remaining": max(
                    0, retry_limit - rec["daily"].get("retries", 0)
                ),
                "referral_earned": rec["referral_earned"],
            }

    # ---- 生成额度（每日限套数，防"无限换画风"烧穿预算） ----

    def charge_generation(self, device: str, ref: str = "") -> tuple[bool, str]:
        with self._lock:
            rec = self._load(device)
            self._rollover(rec)
            limit = self._daily_limit(rec)
            if rec["daily"]["count"] >= limit:
                if rec["plan"] == "free":
                    return False, (
                        f"今天的 {limit} 次免费生成用完啦——解锁后每天 {PAID_DAILY} 次，"
                        "或者明天再来"
                    )
                return False, f"今天的 {limit} 次生成用完啦，明天再来～"
            rec["daily"]["count"] += 1
            # 邀请归因：只认首个 ref、只在还没生成过时记，发奖等首套真出图
            if (
                ref
                and ref != device
                and not rec["referred_by"]
                and rec["jobs_done"] == 0
            ):
                rec["referred_by"] = ref
            self._save(rec)
            return True, ""

    def refund_generation(self, device: str) -> None:
        """整套全失败不扣当日额度。"""
        with self._lock:
            rec = self._load(device)
            self._rollover(rec)
            rec["daily"]["count"] = max(0, rec["daily"]["count"] - 1)
            self._save(rec)

    # ---- 重摇额度（单张重生成=抽卡，真实出图按日限次） ----

    def charge_retry(self, device: str) -> tuple[bool, str]:
        with self._lock:
            rec = self._load(device)
            self._rollover(rec)
            limit = PAID_RETRY_DAILY if rec["plan"] != "free" else FREE_RETRY_DAILY
            used = rec["daily"].get("retries", 0)
            if used >= limit:
                if rec["plan"] == "free":
                    return False, (
                        f"今天的 {limit} 次重摇用完啦——解锁后每天 "
                        f"{PAID_RETRY_DAILY} 次，或者明天再来"
                    )
                return False, f"今天的 {limit} 次重摇用完啦，明天手气更好～"
            rec["daily"]["retries"] = used + 1
            self._save(rec)
            return True, ""

    def refund_retry(self, device: str) -> None:
        """重摇失败不扣次数。"""
        with self._lock:
            rec = self._load(device)
            self._rollover(rec)
            rec["daily"]["retries"] = max(0, rec["daily"].get("retries", 0) - 1)
            self._save(rec)

    def note_job_done(self, device: str) -> str | None:
        """首套生成成功 → 给邀请人发视频额度；返回获奖的邀请人设备 id。"""
        with self._lock:
            rec = self._load(device)
            first = rec["jobs_done"] == 0
            rec["jobs_done"] += 1
            self._save(rec)
            if not (first and rec["referred_by"]):
                return None
            referrer = self._load(rec["referred_by"])
            grant = min(REFERRAL_REWARD, REFERRAL_CAP - referrer["referral_earned"])
            if grant <= 0:
                return None
            referrer["video_credits"] += grant
            referrer["referral_earned"] += grant
            self._save(referrer)
            return referrer["device"]

    # ---- 视频动图额度（单条 ≈¥0.5，成本大头，按条计数） ----

    def charge_video(self, device: str) -> bool:
        with self._lock:
            rec = self._load(device)
            if rec["video_credits"] <= 0:
                return False
            rec["video_credits"] -= 1
            self._save(rec)
            return True

    def refund_video(self, device: str) -> None:
        """生成失败不烧用户额度。"""
        with self._lock:
            rec = self._load(device)
            rec["video_credits"] += 1
            self._save(rec)

    # ---- 兑换码 ----

    def _load_codes(self) -> dict:
        if self.codes_file.exists():
            try:
                return json.loads(self.codes_file.read_text(encoding="utf-8"))
            except ValueError:
                pass
        return {}

    def _save_codes(self, codes: dict) -> None:
        self.codes_file.parent.mkdir(parents=True, exist_ok=True)
        self.codes_file.write_text(
            json.dumps(codes, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    def create_codes(
        self,
        plan: str,
        n: int,
        *,
        max_uses: int = 1,
        expires_in_days: float = 0,
        video_credits: int | None = None,
    ) -> list[str]:
        """单次码（卖的）和活动码（max_uses>1，限名额限时，沙龙/推广用）同一套。"""
        if plan not in PLAN_VIDEO_CREDITS:
            raise ValueError(f"unknown plan: {plan}")
        with self._lock:
            codes = self._load_codes()
            fresh = []
            while len(fresh) < n:
                code = "MP-" + "".join(
                    secrets.choice(_CODE_ALPHABET) for _ in range(8)
                )
                if code in codes:
                    continue
                entry: dict = {
                    "plan": plan, "created_at": time.time(),
                    "used_by": "", "used_at": 0,
                }
                if max_uses > 1:
                    entry["max_uses"] = max_uses
                    entry["uses"] = 0
                if expires_in_days > 0:
                    entry["expires_at"] = time.time() + expires_in_days * 86400
                if video_credits is not None:
                    entry["video_credits"] = video_credits
                codes[code] = entry
                fresh.append(code)
            self._save_codes(codes)
            return fresh

    def _apply_grant(self, rec: dict, plan: str, video_credits: int, code: str) -> None:
        if _PLAN_RANK[plan] > _PLAN_RANK[rec["plan"]]:
            rec["plan"] = plan  # 只升不降；重复兑换额度照加
        rec["video_credits"] += video_credits
        rec["redeemed"].append(code)
        self._save(rec)

    def redeem(self, code: str, device: str) -> tuple[bool, str]:
        """成功返回 (True, plan)；失败返回 (False, 人话原因)。"""
        with self._lock:
            codes = self._load_codes()
            entry = codes.get(code)
            if entry is None:
                return False, "兑换码不存在，检查一下有没有抄错"
            expires = float(entry.get("expires_at") or 0)
            if expires and time.time() > expires:
                return False, "这个码已经过期啦"
            rec = self._load(device)
            if code in rec["redeemed"]:
                return False, "这个码你已经兑换过啦"
            max_uses = int(entry.get("max_uses", 1))
            uses = int(entry.get("uses", 1 if entry.get("used_by") else 0))
            if uses >= max_uses:
                if max_uses > 1:
                    return False, "名额已经被抢完啦"
                return False, "这个码已经被用过了"
            entry["uses"] = uses + 1
            if max_uses == 1:
                entry["used_by"] = device
            entry["used_at"] = time.time()
            self._save_codes(codes)
            plan = entry["plan"]
            grant = int(entry.get("video_credits", PLAN_VIDEO_CREDITS[plan]))
            self._apply_grant(rec, plan, grant, code)
            return True, plan

    def redeem_order(self, order_no: str, device: str, plan: str) -> tuple[bool, str]:
        """爱发电订单核销：订单号一次性，权益与对应档位兑换码一致。"""
        with self._lock:
            codes = self._load_codes()
            key = f"AFD-{order_no}"
            entry = codes.get(key)
            if entry is not None:
                if entry.get("used_by") == device:
                    return False, "这个订单你已经核销过啦"
                return False, "这个订单已经被核销过了"
            codes[key] = {
                "plan": plan, "source": "afdian", "created_at": time.time(),
                "used_by": device, "used_at": time.time(),
            }
            self._save_codes(codes)
            rec = self._load(device)
            self._apply_grant(rec, plan, PLAN_VIDEO_CREDITS[plan], key)
            return True, plan

    # ---- 后台汇总 ----

    def summary(self) -> dict:
        with self._lock:
            codes = self._load_codes()
            by_plan: dict[str, dict[str, int]] = {}
            event = {"codes": 0, "uses": 0}
            for entry in codes.values():
                if int(entry.get("max_uses", 1)) > 1:
                    # 活动码是白嫖通道，单独记，不进收入口径
                    event["codes"] += 1
                    event["uses"] += int(entry.get("uses", 0))
                    continue
                row = by_plan.setdefault(entry["plan"], {"total": 0, "used": 0})
                row["total"] += 1
                row["used"] += 1 if entry.get("used_by") else 0
            devices = list(self.devices_dir.glob("*.json"))
            paid = 0
            for path in devices:
                try:
                    if json.loads(path.read_text(encoding="utf-8"))["plan"] != "free":
                        paid += 1
                except (ValueError, KeyError):
                    continue
            return {
                "codes": by_plan,
                "event": event,
                "devices": {"total": len(devices), "paid": paid},
            }
