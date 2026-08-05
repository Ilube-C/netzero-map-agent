"""Abuse controls for the public deployment.

The demo has no login, so anyone with the URL can spend the deployment's LLM
key. Two limits bound that: a per-IP token bucket for burst protection, and a
global daily ceiling that caps the worst case for the day no matter how many
IPs show up.

State is per-process and in-memory, which is correct for the single-machine Fly
deployment. Running more than one app machine would give each its own counters,
so the effective global cap becomes DAILY_TURN_BUDGET x machines.
"""
import os
import time
from collections import deque

PER_IP_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "8"))
DAILY_TURN_BUDGET = int(os.environ.get("DAILY_TURN_BUDGET", "500"))
MAX_MESSAGE_CHARS = int(os.environ.get("MAX_MESSAGE_CHARS", "500"))

_WINDOW = 60.0
_SWEEP_EVERY = 500  # prune idle IPs periodically so _hits can't grow unbounded

_hits: dict[str, deque] = {}
_checks = 0
_day = -1
_used_today = 0


def client_ip(socket) -> str:
    """Real caller IP. Fly sets Fly-Client-IP on the proxied handshake."""
    headers = socket.headers
    ip = headers.get("fly-client-ip")
    if ip:
        return ip
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return socket.client.host if socket.client else "unknown"


def _sweep(now: float) -> None:
    for ip in [ip for ip, q in _hits.items() if not q or now - q[-1] > _WINDOW]:
        del _hits[ip]


def check(ip: str) -> str | None:
    """Consume one turn's allowance. Returns a refusal message, or None to allow."""
    global _checks, _day, _used_today

    now = time.time()
    _checks += 1
    if _checks % _SWEEP_EVERY == 0:
        _sweep(now)

    today = int(now // 86400)
    if today != _day:
        _day, _used_today = today, 0

    if _used_today >= DAILY_TURN_BUDGET:
        return ("This demo has hit its daily query budget — it runs on a free "
                "model key with a cap so it can stay open to everyone. "
                "Try again tomorrow.")

    q = _hits.setdefault(ip, deque())
    while q and now - q[0] > _WINDOW:
        q.popleft()
    if len(q) >= PER_IP_PER_MINUTE:
        wait = int(_WINDOW - (now - q[0])) + 1
        return f"Slow down a moment — {PER_IP_PER_MINUTE} questions a minute, please. Try again in {wait}s."

    q.append(now)
    _used_today += 1
    return None


def stats() -> dict:
    return {
        "turns_used_today": _used_today,
        "daily_turn_budget": DAILY_TURN_BUDGET,
        "active_ips": len(_hits),
    }
