from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


def judge_same_entity(
    *,
    incoming_name: str,
    incoming_email: str,
    candidate_name: str,
    candidate_email: str,
    candidate_aliases: str,
    score: float,
) -> Dict[str, Any]:
    """
    Returns {answer: yes|no|uncertain, confidence: float, reasoning: str}
    """
    settings = get_settings()
    if not settings.openai_api_key:
        return {
            "answer": "uncertain",
            "confidence": 0.4,
            "reasoning": "No OPENAI_API_KEY; defaulting to uncertain",
        }

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = {
        "task": "Decide if the incoming payer is the same entity as the candidate client record.",
        "incoming": {"name": incoming_name, "email": incoming_email},
        "candidate": {
            "name": candidate_name,
            "email": candidate_email,
            "aliases": candidate_aliases,
            "fuzzy_score": score,
        },
        "rules": [
            "Answer only yes, no, or uncertain.",
            "Prefer uncertain over a wrong yes.",
            "Nicknames/initials of the same person/company can be yes.",
            "Unrelated similar names should be no.",
        ],
    }
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model or "gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an entity-resolution judge for a payments ledger. "
                        'Return JSON: {"answer":"yes|no|uncertain","confidence":0-1,"reasoning":"..."}'
                    ),
                },
                {"role": "user", "content": json.dumps(prompt)},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        answer = str(data.get("answer", "uncertain")).lower().strip()
        if answer not in {"yes", "no", "uncertain"}:
            answer = "uncertain"
        conf = float(data.get("confidence", 0.5))
        conf = max(0.0, min(1.0, conf))
        return {
            "answer": answer,
            "confidence": conf,
            "reasoning": str(data.get("reasoning", ""))[:500],
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("OpenAI entity judge failed: %s", exc)
        return {
            "answer": "uncertain",
            "confidence": 0.3,
            "reasoning": f"llm_error: {exc}",
        }
