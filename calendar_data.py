"""
Two data sources for the Calendar tab:
1. daily_pnl_calendar - a GitHub-contributions-style calendar of realized P&L per
   day, built from closed Trade rows (your own data, no API calls needed).
2. economic_events_this_week - a short Perplexity-grounded list of upcoming
   economic events/data releases relevant to Indian markets.
"""
from datetime import date, timedelta
from collections import defaultdict

from models import Trade
from perplexity_client import PerplexityClient

_perplexity = PerplexityClient()


def daily_pnl_calendar(year, month):
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1)

    trades = Trade.query.filter(
        Trade.status == "CLOSED", Trade.exit_time >= start, Trade.exit_time < end
    ).all()

    by_day = defaultdict(lambda: {"pnl": 0.0, "trades": 0})
    for t in trades:
        d = t.exit_time.date().isoformat()
        by_day[d]["pnl"] += t.pnl or 0
        by_day[d]["trades"] += 1

    return {d: {"pnl": round(v["pnl"], 2), "trades": v["trades"]} for d, v in by_day.items()}


def economic_events_this_week():
    system = "You are a concise Indian markets calendar assistant. Use current web search."
    user = (
        "List the key scheduled economic events/data releases for Indian markets "
        "(RBI policy, inflation data, GDP, Fed decisions affecting India, major "
        "earnings) for the next 7 days, as short markdown bullets with dates. "
        "Under 150 words."
    )
    return _perplexity._chat(system, user, max_tokens=400)
