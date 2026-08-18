"""
Builds the daily newsletter: your own portfolio performance (from Upstox/trade
data) + fresh market context (from Perplexity web search), saved to the
NewsletterIssue table for the Newsletter tab and optional email/export.
"""
from datetime import date

from models import db, NewsletterIssue, Portfolio
from perplexity_client import PerplexityClient
import reports

_perplexity = PerplexityClient()


def generate_daily_newsletter():
    today = date.today()
    portfolio_summaries = []
    for p in Portfolio.query.all():
        r = reports.report_for_period(p.id, "daily")
        portfolio_summaries.append(f"{p.name}: {r['trades']} trades, win rate {r['win_rate_pct']}%, P&L ₹{r['gross_pnl']:+.2f}")

    top_movers = "See scanner output for today's top-scoring symbols per strategy."

    body = _perplexity.newsletter_content(portfolio_summaries, top_movers)
    subject = f"TradeBot Daily Wrap - {today.strftime('%d %b %Y')}"

    issue = NewsletterIssue(issue_date=today, subject=subject, body_markdown=body)
    db.session.add(issue)
    db.session.commit()
    return issue
