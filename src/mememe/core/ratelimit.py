"""内存级 IP 日限器——保护开放的 LLM 入口（编剧 chat/draft）不被脚本批量薅额度。

进程内计数、按日 rollover、重启清零：这是和全局并发信号量同源的轻护栏，
不是账本（账本走 entitlements 的文件存储）。Cloudflare 在最前，真实客户端 IP
在 CF-Connecting-IP 头；Tunnel 的 request.client.host 永远是本地回环、不可信，
故只认 CF/XFF 头。本地直连无此头 → 返回空 → 不限流，不挡开发也不挡单测。
"""

import threading
import time


def client_ip(request) -> str:
    """取真实客户端 IP：优先 Cloudflare 头，兜底 X-Forwarded-For 链首。"""
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for", "")
    return xff.split(",")[0].strip()


class DailyIPLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = ""
        self._counts: dict[tuple[str, str], int] = {}

    def allow(self, bucket: str, ip: str, limit: int) -> bool:
        """放行则计数返回 True；当日该 (bucket, ip) 已达 limit 返回 False。

        空 ip（本地直连/无 CF 头）永远放行——宁可不限也不误杀真实用户。
        bucket 区分用途（chat/draft 各自独立计数）。
        """
        if not ip:
            return True
        with self._lock:
            today = time.strftime("%Y-%m-%d")
            if today != self._day:  # 跨天清零，无需后台任务
                self._day = today
                self._counts.clear()
            key = (bucket, ip)
            used = self._counts.get(key, 0)
            if used >= limit:
                return False
            self._counts[key] = used + 1
            return True
