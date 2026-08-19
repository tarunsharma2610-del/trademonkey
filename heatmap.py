"""
Sector Heatmap: groups the Nifty 500 universe by sector (from instrument_master's
bundled sector data) and computes an average day % change per sector, using the
Upstox OHLC quote endpoint (last_price vs previous close) for real moves.
"""
from statistics import mean
from instrument_master import instrument_master
from upstox_client import UpstoxClient


def compute_heatmap(upstox_client=None, sample_per_sector=6):
    """Returns list of {sector, change_pct, symbol_count, top_movers: [...]}
    sorted by change_pct desc. Sampling a handful of symbols per sector keeps
    this fast; increase sample_per_sector for more accuracy at the cost of more
    API calls in live mode."""
    client = upstox_client or UpstoxClient()
    results = []

    for sector in instrument_master.all_sectors():
        symbols = instrument_master.symbols_in_sector(sector)[:sample_per_sector]
        if not symbols:
            continue
        keys = [instrument_master.resolve_equity(s) for s in symbols]
        keys = [k for k in keys if k]
        if not keys:
            continue

        quotes = client.get_quote(keys)
        changes = []
        for sym, key in zip(symbols, keys):
            quote = quotes.get(key)
            if not quote:
                continue
            ltp = quote.get("last_price")
            prev = quote.get("prev_close")
            if ltp is None or not prev:
                continue
            changes.append({"symbol": sym, "change_pct": round((ltp - prev) / prev * 100, 2)})

        if not changes:
            continue
        avg_change = round(mean(c["change_pct"] for c in changes), 2)
        changes.sort(key=lambda c: c["change_pct"], reverse=True)
        results.append({
            "sector": sector,
            "change_pct": avg_change,
            "symbol_count": len(instrument_master.symbols_in_sector(sector)),
            "top_movers": changes[:3],
        })

    results.sort(key=lambda r: r["change_pct"], reverse=True)
    return results
