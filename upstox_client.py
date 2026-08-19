"""
Thin wrapper around Upstox's REST + WebSocket API.

Covers:
- Access token handling (you still need to complete the OAuth login flow once a day
  and store the resulting token in UPSTOX_ACCESS_TOKEN - Upstox tokens expire daily at 3:30am IST)
- LTP / quote fetch (batched)
- Historical candles
- A token-bucket rate limiter so you never trip Upstox's per-second / per-minute caps
- WebSocket market feed for live ticks

This module NEVER generates fake/simulated market data. If the access token is
missing or a request fails, it raises an explicit error so the system fails
closed instead of inventing prices.
"""
import time
import threading
import collections
import requests

import config

UPSTOX_BASE = "https://api.upstox.com/v2"


class MarketDataConfigError(RuntimeError):
    """Raised when the client is used without valid Upstox credentials."""


class RateLimiter:
    """Simple token bucket. Upstox limits: ~25 req/sec, 250 req/min, 1000 req/30min (varies by endpoint)."""

    def __init__(self, max_per_second=20, max_per_minute=180):
        self.max_per_second = max_per_second
        self.max_per_minute = max_per_minute
        self._sec_bucket = collections.deque()
        self._min_bucket = collections.deque()
        self._lock = threading.Lock()

    def acquire(self):
        with self._lock:
            now = time.time()
            while self._sec_bucket and now - self._sec_bucket[0] > 1:
                self._sec_bucket.popleft()
            while self._min_bucket and now - self._min_bucket[0] > 60:
                self._min_bucket.popleft()

            if len(self._sec_bucket) >= self.max_per_second or len(self._min_bucket) >= self.max_per_minute:
                sleep_for = 0.05
                time.sleep(sleep_for)
                return self.acquire()

            self._sec_bucket.append(now)
            self._min_bucket.append(now)


class UpstoxClient:
    def __init__(self, access_token=None):
        self.access_token = access_token or config.UPSTOX_ACCESS_TOKEN
        self.limiter = RateLimiter()
        self._session = requests.Session()

    def _require_token(self):
        if not self.access_token:
            raise MarketDataConfigError(
                "UPSTOX_ACCESS_TOKEN is not configured. Live market data requires a "
                "valid Upstox access token; refusing to fall back to fake data."
            )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def login_url(self):
        return (
            "https://api.upstox.com/v2/login/authorization/dialog"
            f"?response_type=code&client_id={config.UPSTOX_API_KEY}"
            f"&redirect_uri={config.UPSTOX_REDIRECT_URI}"
        )

    def exchange_code_for_token(self, auth_code):
        resp = self._session.post(
            f"{UPSTOX_BASE}/login/authorization/token",
            data={
                "code": auth_code,
                "client_id": config.UPSTOX_API_KEY,
                "client_secret": config.UPSTOX_API_SECRET,
                "redirect_uri": config.UPSTOX_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            headers={"accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data.get("access_token")
        return self.access_token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    def get_ltp(self, instrument_keys):
        """instrument_keys: list of Upstox instrument keys, e.g. NSE_EQ|INE002A01018
        Returns dict {instrument_key: ltp}
        """
        self._require_token()
        self.limiter.acquire()
        joined = ",".join(instrument_keys)
        resp = self._session.get(
            f"{UPSTOX_BASE}/market-quote/ltp",
            params={"instrument_key": joined},
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return {v["instrument_token"]: v["last_price"] for v in data.values()}

    def get_quote(self, instrument_keys):
        """Batched OHLC quote (includes previous close), e.g. for day-change
        calculations. Returns dict {instrument_key: {last_price, open, high,
        low, prev_close}}."""
        self._require_token()
        self.limiter.acquire()
        joined = ",".join(instrument_keys)
        resp = self._session.get(
            f"{UPSTOX_BASE}/market-quote/ohlc",
            params={"instrument_key": joined},
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        result = {}
        for v in data.values():
            ohlc = v.get("ohlc") or {}
            result[v["instrument_token"]] = {
                "last_price": v.get("last_price"),
                "open": ohlc.get("open"),
                "high": ohlc.get("high"),
                "low": ohlc.get("low"),
                "prev_close": ohlc.get("close"),
            }
        return result

    def get_historical_candles(self, instrument_key, interval, from_date, to_date):
        """interval: '1minute' | '30minute' | 'day' etc (per Upstox v2 historical-candle API)"""
        self._require_token()
        self.limiter.acquire()
        resp = self._session.get(
            f"{UPSTOX_BASE}/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        candles = resp.json().get("data", {}).get("candles", [])
        # Upstox returns [timestamp, open, high, low, close, volume, oi]
        return [
            {"ts": c[0], "open": c[1], "high": c[2], "low": c[3], "close": c[4], "volume": c[5], "oi": c[6]}
            for c in candles
        ]

    def get_instrument_master(self):
        """Downloads and caches the full instrument list (needed to resolve Nifty 500 / MCX symbols
        to Upstox instrument_keys). Upstox publishes this as a gzipped JSON at a public URL - see
        their docs for the current link, since it changes format occasionally."""
        raise NotImplementedError(
            "Wire this to Upstox's instrument master file URL from their developer docs, "
            "then cache it locally (refresh once a day, not per-request)."
        )

    # ------------------------------------------------------------------
    # WebSocket (live feed).
    # Uses Upstox's official `upstox-python-sdk` (pip install upstox-python-sdk),
    # whose MarketDataStreamerV3 handles protobuf decoding internally and
    # exposes a plain event emitter - no need to hand-roll .proto compilation.
    # ------------------------------------------------------------------
    def start_feed(self, instrument_keys, on_tick):
        self._require_token()

        try:
            import upstox_client as upstox_sdk
        except ImportError:
            raise RuntimeError(
                "Install the official SDK for live feeds: pip install upstox-python-sdk"
            )

        configuration = upstox_sdk.Configuration()
        configuration.access_token = self.access_token
        api_client = upstox_sdk.ApiClient(configuration)

        streamer = upstox_sdk.MarketDataStreamerV3(api_client, instrument_keys, mode="ltpc")

        def _on_message(message):
            feeds = message.get("feeds", {}) if isinstance(message, dict) else {}
            for instrument_key, feed in feeds.items():
                ltpc = feed.get("ltpc") or feed.get("fullFeed", {}).get("marketFF", {}).get("ltpc")
                if ltpc and "ltp" in ltpc:
                    on_tick(instrument_key, float(ltpc["ltp"]))

        streamer.on("message", _on_message)
        streamer.on("error", lambda e: None)
        streamer.connect()
        return streamer
