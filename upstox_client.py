"""
Thin wrapper around Upstox's REST + WebSocket API.

Covers:
- Access token handling (you still need to complete the OAuth login flow once a day
  and store the resulting token in UPSTOX_ACCESS_TOKEN - Upstox tokens expire daily at 3:30am IST)
- LTP / quote fetch (batched)
- Historical candles
- A token-bucket rate limiter so you never trip Upstox's per-second / per-minute caps
- WebSocket market feed for live ticks, with an in-memory demo/mock fallback so the
  rest of the app can be developed and tested without live market hours or a live token
"""
import time
import threading
import collections
import random
import requests

import config

UPSTOX_BASE = "https://api.upstox.com/v2"


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
    def __init__(self, access_token=None, demo_mode=None):
        self.access_token = access_token or config.UPSTOX_ACCESS_TOKEN
        self.demo_mode = config.DEMO_MODE if demo_mode is None else demo_mode
        self.limiter = RateLimiter()
        self._session = requests.Session()

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
        if self.demo_mode or not self.access_token:
            return {k: self._demo_price(k) for k in instrument_keys}

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

    def get_historical_candles(self, instrument_key, interval, from_date, to_date):
        """interval: '1minute' | '30minute' | 'day' etc (per Upstox v2 historical-candle API)"""
        if self.demo_mode or not self.access_token:
            return self._demo_candles()

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
        if self.demo_mode or not self.access_token:
            return self._start_demo_feed(instrument_keys, on_tick)

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

    def _start_demo_feed(self, instrument_keys, on_tick):
        stop_event = threading.Event()

        def _loop():
            prices = {k: self._demo_price(k) for k in instrument_keys}
            while not stop_event.is_set():
                for k in instrument_keys:
                    prices[k] *= 1 + random.uniform(-0.003, 0.003)
                    on_tick(k, round(prices[k], 2))
                time.sleep(1)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        return stop_event  # call .set() to stop

    # ------------------------------------------------------------------
    # Demo helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _demo_price(instrument_key):
        random.seed(hash(instrument_key) % (2**16))
        return round(random.uniform(100, 3500), 2)

    @staticmethod
    def _demo_candles(n=60):
        price = random.uniform(100, 3500)
        candles = []
        now = time.time()
        for i in range(n):
            o = price
            c = price * (1 + random.uniform(-0.01, 0.01))
            h = max(o, c) * (1 + random.uniform(0, 0.005))
            l = min(o, c) * (1 - random.uniform(0, 0.005))
            v = random.randint(10_000, 500_000)
            candles.append({
                "ts": now - (n - i) * 1800, "open": o, "high": h, "low": l,
                "close": c, "volume": v, "oi": random.randint(0, 100000),
            })
            price = c
        return candles
