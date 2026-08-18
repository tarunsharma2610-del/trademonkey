"""
Optional OAuth helper for Upstox.

IMPORTANT for this project: since TradeBot AI only ever does PAPER trades, it
never calls Upstox's real order-placement endpoints. That means you do NOT need
the daily OAuth login dance at all - your existing long-lived, read-only
Analytics Token (the one you already generated) is sufficient for LTP, historical
candles, and quotes. Just set it as UPSTOX_ACCESS_TOKEN and skip this file entirely.

This module exists only for the day you want to extend the system to place real
orders (graduating from paper to live trading), which requires the standard OAuth
authorization-code flow below, refreshed daily (Upstox tokens expire ~3:30am IST).
Wire these two Flask routes into app.py if/when that day comes:

    @app.route("/upstox/login")
    def upstox_login():
        return redirect(client.login_url())

    @app.route("/upstox/callback")
    def upstox_callback():
        code = request.args.get("code")
        token = client.exchange_code_for_token(code)
        # persist `token` to your env/secrets store here
        return "Upstox authorized for today."
"""
from upstox_client import UpstoxClient

client = UpstoxClient()
