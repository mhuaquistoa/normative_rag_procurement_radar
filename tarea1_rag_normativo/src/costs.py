"""Cost of every model call, with the price in force at the time of the call, and the call log.

Prices live in config.yaml (`pricing`), each with its source URL and the date it was verified.
DeepSeek charges a peak and an off-peak rate: `price_window()` decides which one applies from the
call's UTC timestamp (weekday + hour ranges from the config). Every call - generation or embedding,
success or failure - is appended to logs/calls.csv: date, model, tokens in/out, latency, cost, ok.
"""
import csv
from datetime import datetime, timezone

from config import cfg, path

FIELDS = ["timestamp_utc", "kind", "model", "tokens_in", "tokens_cached", "tokens_out", "latency_s",
          "price_window", "cost_usd", "ok", "note"]


def price_window(model: str, when: datetime) -> str:
    """'peak' or 'off_peak' for time-of-day pricing, 'flat' otherwise."""
    p = cfg()["pricing"].get(model, {})
    peak = p.get("peak_hours_utc")
    if not peak:
        return "flat"
    w = when.astimezone(timezone.utc)
    in_day = w.weekday() in peak["weekdays"]
    in_hours = any(start <= w.hour < end for start, end in peak["ranges"])
    return "peak" if in_day and in_hours else "off_peak"


def cost_usd(model: str, tokens_in: int, tokens_out: int, tokens_cached: int = 0, when: datetime = None):
    """(cost, window). Unknown model -> cost None, so a missing price is visible, never a silent 0."""
    when = when or datetime.now(timezone.utc)
    p = cfg()["pricing"].get(model)
    if p is None:
        return None, "unknown"
    window = price_window(model, when)
    rate = p[window] if window != "flat" else p["flat"]
    fresh = max(tokens_in - tokens_cached, 0)
    usd = (fresh * rate["input"] + tokens_cached * rate.get("input_cached", rate["input"])
           + tokens_out * rate.get("output", 0)) / 1_000_000
    return round(usd, 8), window


def log_call(kind: str, model: str, tokens_in: int, tokens_out: int, latency_s: float, ok: bool,
             note: str = "", tokens_cached: int = 0, when: datetime = None) -> tuple:
    """Appends the call to logs/calls.csv and returns (cost_usd, price_window) as charged."""
    when = when or datetime.now(timezone.utc)
    usd, window = cost_usd(model, tokens_in, tokens_out, tokens_cached, when) if ok else (0.0, "n/a")
    f = path("logs") / "calls.csv"
    new = not f.exists()
    with open(f, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({"timestamp_utc": when.isoformat(timespec="seconds"), "kind": kind, "model": model,
                    "tokens_in": tokens_in, "tokens_cached": tokens_cached, "tokens_out": tokens_out,
                    "latency_s": round(latency_s, 3), "price_window": window, "cost_usd": usd, "ok": ok, "note": note})
    return usd, window
