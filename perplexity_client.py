"""
Wrapper around Perplexity's chat completions API (OpenAI-compatible schema),
used for:
- Pre-market research brief (global cues, key news, sector focus)
- Daily/weekly newsletter copy grounded in current web search
"""
import requests
import config

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"


class PerplexityClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or config.PERPLEXITY_API_KEY

    def _chat(self, system_prompt, user_prompt, max_tokens=800):
        if not self.api_key:
            return self._demo_response(user_prompt)

        resp = requests.post(
            PERPLEXITY_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.PERPLEXITY_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def pre_market_brief(self):
        """Called by the pre-market scheduler job. Returns a short markdown brief:
        global cues (SGX Nifty / US markets / Asian markets), key domestic news,
        sectors to watch today, and any major economic data releases."""
        system = (
            "You are a concise Indian equity markets pre-market analyst. "
            "Use current web search. Answer in tight markdown bullets, no fluff."
        )
        user = (
            "Give today's pre-market briefing for Indian markets (NSE/BSE/MCX): "
            "1) Global cues overnight (US close, SGX Nifty/GIFT Nifty, Asian markets) "
            "2) Top 3 domestic news items likely to move markets today "
            "3) Sectors to watch 4) Any scheduled economic data/events today. "
            "Keep it under 200 words."
        )
        return self._chat(system, user)

    def newsletter_content(self, portfolio_summaries, top_movers):
        """Grounded newsletter copy for the daily/weekly mailer - combines your
        own trading data (passed in) with fresh web context from Perplexity."""
        system = (
            "You write a crisp daily markets newsletter for a self-directed Indian trader. "
            "Tone: informative, neutral, no investment advice framing, SEBI-compliant "
            "(clearly informational/educational, not a recommendation)."
        )
        user = (
            f"Today's portfolio performance: {portfolio_summaries}\n"
            f"Top movers/watchlist: {top_movers}\n"
            "Write a short newsletter: 1) One-line market wrap 2) 2-3 stocks to watch "
            "tomorrow with reasoning grounded in current news 3) One-line risk note. "
            "Under 250 words. Add a disclaimer that this is for educational/informational "
            "purposes only, not investment advice."
        )
        return self._chat(system, user)

    @staticmethod
    def _demo_response(prompt):
        return (
            "_(Demo mode - no PERPLEXITY_API_KEY set. This is placeholder text so the UI "
            "can be developed. Set PERPLEXITY_API_KEY as an environment variable to get "
            "real, web-grounded content here.)_\n\n"
            "- Global cues: placeholder\n- Domestic news: placeholder\n- Sectors to watch: placeholder"
        )
