from mememe.core import ratelimit


class FakeRequest:
    def __init__(self, headers: dict):
        self.headers = headers


def test_client_ip_prefers_cf_header():
    req = FakeRequest({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "9.9.9.9"})
    assert ratelimit.client_ip(req) == "1.2.3.4"


def test_client_ip_falls_back_to_xff_chain_head():
    req = FakeRequest({"x-forwarded-for": "5.6.7.8, 10.0.0.1"})
    assert ratelimit.client_ip(req) == "5.6.7.8"


def test_client_ip_empty_when_no_headers():
    # 本地直连/无 CF：返回空 → 限流器放行，不挡开发
    assert ratelimit.client_ip(FakeRequest({})) == ""


def test_allow_counts_up_to_limit_then_blocks():
    lim = ratelimit.DailyIPLimiter()
    assert lim.allow("chat", "1.1.1.1", 2) is True
    assert lim.allow("chat", "1.1.1.1", 2) is True
    assert lim.allow("chat", "1.1.1.1", 2) is False  # 第 3 次超限


def test_empty_ip_always_allowed():
    lim = ratelimit.DailyIPLimiter()
    for _ in range(100):
        assert lim.allow("chat", "", 1) is True


def test_buckets_and_ips_count_independently():
    lim = ratelimit.DailyIPLimiter()
    assert lim.allow("chat", "1.1.1.1", 1) is True
    assert lim.allow("chat", "1.1.1.1", 1) is False
    # 同 IP 不同 bucket、同 bucket 不同 IP 各自独立
    assert lim.allow("draft", "1.1.1.1", 1) is True
    assert lim.allow("chat", "2.2.2.2", 1) is True


def test_rollover_clears_counts_on_new_day(monkeypatch):
    lim = ratelimit.DailyIPLimiter()
    monkeypatch.setattr(ratelimit.time, "strftime", lambda fmt: "2026-06-12")
    assert lim.allow("chat", "1.1.1.1", 1) is True
    assert lim.allow("chat", "1.1.1.1", 1) is False
    monkeypatch.setattr(ratelimit.time, "strftime", lambda fmt: "2026-06-13")
    assert lim.allow("chat", "1.1.1.1", 1) is True  # 跨天清零
