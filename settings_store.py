"""
Runtime-editable settings layer. Falls back to config.py defaults until the
user overrides something from the Settings/Risk Mgmt pages, at which point the
override is persisted in the `settings` table and takes precedence.
"""
from models import db, Setting
import config


def get(key, default=None):
    row = Setting.query.get(key)
    return row.value if row else default


def set(key, value):
    row = Setting.query.get(key)
    if row:
        row.value = value
    else:
        row = Setting(key=key)
        row.value = value
        db.session.add(row)
    db.session.commit()
    return row


def get_risk_limits():
    return get("global_risk_limits", config.GLOBAL_RISK_LIMITS)


def set_risk_limits(limits: dict):
    merged = dict(config.GLOBAL_RISK_LIMITS)
    merged.update(limits)
    return set("global_risk_limits", merged)


def get_api_key_status():
    """Never returns actual key values to the UI - only whether each is configured,
    so Settings can show status without leaking secrets into HTML/logs."""
    return {
        "upstox_api_key": bool(config.UPSTOX_API_KEY),
        "upstox_access_token": bool(config.UPSTOX_ACCESS_TOKEN),
        "perplexity_api_key": bool(config.PERPLEXITY_API_KEY),
        "demo_mode": config.DEMO_MODE,
    }
