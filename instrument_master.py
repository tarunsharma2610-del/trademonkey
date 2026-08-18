"""
Resolves plain ticker symbols to Upstox instrument_keys.

Key insight for NSE/BSE equities: Upstox's instrument_key format for equity cash
is `{EXCHANGE}_EQ|{ISIN}` (e.g. NSE_EQ|INE002A01018 for Reliance). Since ISIN is
a stable identifier bundled in data/nifty500.json, equities can be resolved
directly with zero API calls or downloads - no need to fetch Upstox's full
instrument master just for equity cash symbols.

MCX (and any F&O) instruments are NOT resolvable this way - those instrument_keys
point at a specific monthly futures contract and change every expiry cycle.
Those must come from Upstox's published instrument master file (a large gzipped
JSON/CSV they update daily) - see `refresh_mcx_master()` below, which is stubbed
with clear TODOs since it requires a live download from Upstox's docs-linked URL.
"""
import json
import os
import gzip
import io
from datetime import datetime

import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
NIFTY500_PATH = os.path.join(DATA_DIR, "nifty500.json")
MCX_PATH = os.path.join(DATA_DIR, "mcx_commodities.json")
MCX_MASTER_CACHE_PATH = os.path.join(DATA_DIR, "mcx_instrument_master.json")

# Upstox publishes complete + segment-wise instrument master files here (subject to
# occasional path changes - check https://upstox.com/developer/api-documentation/instruments
# if this 404s):
UPSTOX_MCX_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/MCX.json.gz"


class InstrumentMaster:
    def __init__(self):
        self._nifty500 = self._load_json(NIFTY500_PATH)
        self._mcx_static = self._load_json(MCX_PATH)
        self._equity_by_symbol = {row["symbol"]: row for row in self._nifty500}
        self._mcx_master_cache = self._load_json(MCX_MASTER_CACHE_PATH) or {}

    @staticmethod
    def _load_json(path):
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    # ------------------------------------------------------------------
    def resolve_equity(self, symbol, exchange="NSE"):
        """Direct resolution via ISIN - no download needed, works offline."""
        row = self._equity_by_symbol.get(symbol.upper())
        if not row:
            return None
        return f"{exchange}_EQ|{row['isin']}"

    def resolve_mcx(self, symbol):
        """MCX futures need the current month's contract instrument_key, which
        must come from the cached instrument master (see refresh_mcx_master).
        Falls back to None if the master hasn't been downloaded yet."""
        entry = self._mcx_master_cache.get(symbol.upper())
        return entry.get("instrument_key") if entry else None

    def resolve(self, symbol, segment="NSE"):
        if segment == "MCX":
            return self.resolve_mcx(symbol)
        return self.resolve_equity(symbol, exchange=segment)

    def nifty500_symbols(self):
        return [row["symbol"] for row in self._nifty500] if self._nifty500 else []

    def nifty500_sector(self, symbol):
        row = self._equity_by_symbol.get(symbol.upper())
        return row["sector"] if row else "Unknown"

    def all_sectors(self):
        if not self._nifty500:
            return []
        return sorted(set(row["sector"] for row in self._nifty500))

    def symbols_in_sector(self, sector):
        return [row["symbol"] for row in self._nifty500 if row["sector"] == sector]

    def mcx_symbols(self):
        return [row["symbol"] for row in self._mcx_static] if self._mcx_static else []

    # ------------------------------------------------------------------
    def refresh_mcx_master(self):
        """Downloads Upstox's MCX instrument master and caches the *current
        month's* contract for each commodity symbol we track. Run this daily
        (e.g. from the pre-market scheduler job) since contracts roll monthly.

        NOTE: requires network access to assets.upstox.com from wherever this
        runs (your Oracle Cloud box, not this sandbox) and does nothing
        destructive if it fails - it just leaves the previous cache in place.
        """
        try:
            resp = requests.get(UPSTOX_MCX_MASTER_URL, timeout=30)
            resp.raise_for_status()
            raw = gzip.decompress(resp.content)
            instruments = json.loads(raw)
        except Exception as e:
            return False, f"Could not refresh MCX master: {e}"

        tracked = {row["symbol"] for row in (self._mcx_static or [])}
        best_by_symbol = {}
        for inst in instruments:
            name = inst.get("trading_symbol", "") or inst.get("name", "")
            base = "".join(ch for ch in name if ch.isalpha()).upper()
            for sym in tracked:
                if base.startswith(sym):
                    expiry = inst.get("expiry")
                    # keep the nearest (soonest) expiry as "the" contract for this symbol
                    if sym not in best_by_symbol or (expiry and expiry < best_by_symbol[sym].get("expiry", "9999")):
                        best_by_symbol[sym] = {
                            "instrument_key": inst.get("instrument_key"),
                            "expiry": expiry,
                            "trading_symbol": name,
                        }

        self._mcx_master_cache = best_by_symbol
        with open(MCX_MASTER_CACHE_PATH, "w") as f:
            json.dump(best_by_symbol, f, indent=1)
        return True, f"Refreshed {len(best_by_symbol)} MCX contracts at {datetime.utcnow().isoformat()}"


# Module-level singleton, mirrors how upstox_client / scanner are used elsewhere
instrument_master = InstrumentMaster()
