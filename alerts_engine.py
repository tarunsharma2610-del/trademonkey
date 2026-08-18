"""
Checks active Alert rows against the latest LTPs (and, for SCORE_ABOVE alerts,
the latest scanner scores) and fires an event + marks them triggered.
Called from scheduler.market_hours_job() on every cycle.
"""
from datetime import datetime
from models import db, Alert


def check_alerts(ltp_by_symbol, scan_scores_by_symbol=None, push_event=None):
    scan_scores_by_symbol = scan_scores_by_symbol or {}
    fired = []

    for alert in Alert.query.filter_by(active=True).all():
        triggered = False

        if alert.condition == "ABOVE":
            ltp = ltp_by_symbol.get(alert.symbol)
            triggered = ltp is not None and ltp >= alert.threshold
        elif alert.condition == "BELOW":
            ltp = ltp_by_symbol.get(alert.symbol)
            triggered = ltp is not None and ltp <= alert.threshold
        elif alert.condition == "SCORE_ABOVE":
            score = scan_scores_by_symbol.get(alert.symbol)
            triggered = score is not None and score >= alert.threshold

        if triggered:
            alert.active = False
            alert.triggered_at = datetime.utcnow()
            fired.append(alert)
            if push_event:
                push_event("ALERT_TRIGGERED", {
                    "symbol": alert.symbol, "condition": alert.condition, "threshold": alert.threshold,
                })

    if fired:
        db.session.commit()
    return fired
