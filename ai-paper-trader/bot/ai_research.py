from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx
from openai import OpenAI, OpenAIError

from .config import Settings
from .strategy import Candidate

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResearchDecision:
    symbol: str
    ai_rank: int
    ai_score: float
    thesis: str
    risks: str


class AIResearcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.openai_client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.http_client = httpx.Client(timeout=60.0)

    @property
    def enabled(self) -> bool:
        if not self.settings.ai_research_enabled:
            return False
        if self.settings.ai_provider == "openai":
            return self.openai_client is not None
        if self.settings.ai_provider == "ollama":
            return self.settings.ollama_base_url is not None
        return False

    def rank_candidates(self, candidates: list[Candidate]) -> list[ResearchDecision]:
        if not self.enabled or not candidates:
            return []

        prompt = self._build_prompt(candidates)
        raw_text = self._request_research(prompt)
        if not raw_text:
            return []

        return self._parse_research_response(raw_text)

    def _request_research(self, prompt: str) -> str:
        if self.settings.ai_provider == "ollama":
            return self._request_ollama(prompt)
        return self._request_openai(prompt)

    def _request_openai(self, prompt: str) -> str:
        try:
            response = self.openai_client.responses.create(
                model=self.settings.openai_model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a conservative paper-trading research assistant. "
                            "Return strict JSON only. Rank the strongest long-only swing-trade ideas "
                            "using the provided metrics. Do not recommend shorts, leverage, or margin."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                text={"format": {"type": "json_object"}},
            )
        except OpenAIError as exc:
            LOGGER.warning("AI research request failed; falling back to rule-based ranking: %s", exc)
            return ""

        raw_text = getattr(response, "output_text", "") or ""
        if not raw_text:
            LOGGER.warning("AI research returned no output text; falling back to rule-based ranking.")
            return ""
        return raw_text

    def _request_ollama(self, prompt: str) -> str:
        try:
            response = self.http_client.post(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.settings.ollama_model,
                    "stream": False,
                    "format": "json",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a conservative paper-trading research assistant. "
                                "Return strict JSON only. Rank the strongest long-only swing-trade ideas "
                                "using the provided metrics. Do not recommend shorts, leverage, or margin."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            LOGGER.warning("Ollama research request failed; falling back to rule-based ranking: %s", exc)
            return ""

        payload = response.json()
        raw_text = str(payload.get("message", {}).get("content", "")).strip()
        if not raw_text:
            LOGGER.warning("Ollama research returned no content; falling back to rule-based ranking.")
            return ""
        return raw_text

    def _parse_research_response(self, raw_text: str) -> list[ResearchDecision]:
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            LOGGER.warning("AI research returned invalid JSON; falling back to rule-based ranking.")
            return []

        ideas = payload.get("ideas", [])
        decisions: list[ResearchDecision] = []
        for item in ideas:
            symbol = str(item.get("symbol", "")).upper()
            if not symbol:
                continue
            decisions.append(
                ResearchDecision(
                    symbol=symbol,
                    ai_rank=int(item.get("rank", len(decisions) + 1)),
                    ai_score=float(item.get("score", 0.0)),
                    thesis=str(item.get("thesis", "")).strip(),
                    risks=str(item.get("risks", "")).strip(),
                )
            )
        return decisions

    def _build_prompt(self, candidates: list[Candidate]) -> str:
        candidate_blob = [
            {
                "symbol": candidate.symbol,
                "rule_score": candidate.score,
                "price": round(candidate.price, 4),
                "momentum_5d_pct": round(candidate.momentum_5d * 100.0, 4),
                "momentum_20d_pct": round(candidate.momentum_20d * 100.0, 4),
                "volatility_pct": round(candidate.volatility * 100.0, 4),
                "avg_dollar_volume_20d": round(candidate.avg_dollar_volume_20d, 2),
                "explanation": candidate.explanation,
            }
            for candidate in candidates
        ]
        return (
            "Review these stock candidates and rank the best long-only paper-trading entries for the next session. "
            "Favor liquid names with sustained momentum and manageable volatility. "
            "Return JSON with shape "
            '{"ideas":[{"symbol":"XYZ","rank":1,"score":0-100,"thesis":"...","risks":"..."}]}. '
            "Only include symbols from the provided list.\n\n"
            f"{json.dumps(candidate_blob)}"
        )
