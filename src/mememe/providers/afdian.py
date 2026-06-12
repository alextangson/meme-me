"""爱发电订单查询 — 买家自助核销（粘订单号 → 查单 → 秒解锁）。

为什么不用 webhook：webhook 只通知我们、没法把兑换码递回买家手里，
人工环节还在。让买家自己粘订单号反查，全自动、零人工。

Open API 文档：https://guide.afdian.com/creator/developer
鉴权：sign = md5("{token}params{params}ts{ts}user_id{user_id}")。
国内域名 ifdian.net 与 afdian.com 同一套 API。
注意 trust_env=False：开发机代理会拦国内端点（运维教训）。
"""

import hashlib
import json
import os
import time

import httpx

BASE = os.environ.get("MEMEME_AFDIAN_BASE", "https://ifdian.net")


def configured() -> bool:
    return bool(os.environ.get("AFDIAN_USER_ID") and os.environ.get("AFDIAN_TOKEN"))


def looks_like_order_no(text: str) -> bool:
    """爱发电订单号是 20 位上下的纯数字串，和 MP- 兑换码形态完全不同。"""
    return text.isdigit() and 12 <= len(text) <= 40


def query_order(out_trade_no: str) -> dict | None:
    """按订单号查单；查到返回订单 dict，查不到返回 None，接口报错抛异常。"""
    user_id = os.environ["AFDIAN_USER_ID"]
    token = os.environ["AFDIAN_TOKEN"]
    params = json.dumps({"out_trade_no": out_trade_no})
    ts = int(time.time())
    sign = hashlib.md5(
        f"{token}params{params}ts{ts}user_id{user_id}".encode()
    ).hexdigest()
    resp = httpx.post(
        f"{BASE}/api/open/query-order",
        json={"user_id": user_id, "params": params, "ts": ts, "sign": sign},
        timeout=15,
        trust_env=False,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("ec") != 200:
        raise RuntimeError(f"afdian ec={data.get('ec')}: {data.get('em')}")
    for order in (data.get("data") or {}).get("list") or []:
        if order.get("out_trade_no") == out_trade_no:
            return order
    return None


def order_amount(order: dict) -> float:
    """订单实付金额；字段在不同档位下叫法不一，按优先级取。"""
    for key in ("show_amount", "total_amount"):
        val = order.get(key)
        if val:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return 0.0
