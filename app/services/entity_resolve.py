from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rapidfuzz import fuzz

from app.config import get_settings
from app.models import NormalizedEvent
from app.services import airtable_client
from app.services.llm import judge_same_entity


@dataclass
class EntityResolution:
    client: Optional[Dict[str, Any]]
    score: float
    band: str  # auto | llm | new
    llm_answer: Optional[str] = None
    llm_reasoning: str = ""
    same_entity: str = "uncertain"  # yes | no | uncertain | new
    who_acts: str = "human"  # agent | human
    confidence: float = 0.0
    created_new: bool = False
    notes: str = ""
    candidates: List[Dict[str, Any]] = field(default_factory=list)


def _best_score(hints: List[str], client: Dict[str, Any]) -> float:
    corpus = " ".join(
        filter(
            None,
            [
                client.get("name") or "",
                client.get("email") or "",
                client.get("aliases") or "",
            ],
        )
    )
    if not hints or not corpus.strip():
        return 0.0
    scores = []
    for h in hints:
        h = (h or "").strip()
        if not h:
            continue
        scores.append(float(fuzz.token_sort_ratio(h.lower(), corpus.lower())))
        # also compare to name alone
        if client.get("name"):
            scores.append(float(fuzz.token_sort_ratio(h.lower(), client["name"].lower())))
        if client.get("email") and "@" in h:
            scores.append(float(fuzz.ratio(h.lower(), client["email"].lower())))
    return max(scores) if scores else 0.0


def resolve_entity(event: NormalizedEvent) -> EntityResolution:
    settings = get_settings()
    clients = airtable_client.list_clients()
    hints = list(event.name_hints or []) + list(event.email_hints or [])
    incoming_name = (event.name_hints or ["Unknown"])[0] if event.name_hints else "Unknown"
    incoming_email = (event.email_hints or [""])[0] if event.email_hints else ""

    if not clients:
        client = airtable_client.create_client(
            name=incoming_name,
            email=incoming_email,
            needs_review=True,
        )
        return EntityResolution(
            client=client,
            score=0.0,
            band="new",
            same_entity="new",
            who_acts="human",
            confidence=0.2,
            created_new=True,
            notes="No existing clients; created needs_review client",
        )

    scored = []
    for c in clients:
        s = _best_score(hints, c)
        scored.append({**c, "score": s})
    scored.sort(key=lambda x: x["score"], reverse=True)
    best = scored[0]
    score = float(best["score"])

    auto_th = settings.entity_auto_match_threshold
    low_th = settings.entity_llm_band_low

    if score >= auto_th:
        return EntityResolution(
            client=best,
            score=score,
            band="auto",
            same_entity="yes",
            who_acts="agent",
            confidence=min(0.99, score / 100.0),
            notes=f"Auto-matched via RapidFuzz score={score:.1f}",
            candidates=scored[:3],
        )

    if score >= low_th:
        judgment = judge_same_entity(
            incoming_name=incoming_name,
            incoming_email=incoming_email,
            candidate_name=best.get("name") or "",
            candidate_email=best.get("email") or "",
            candidate_aliases=best.get("aliases") or "",
            score=score,
        )
        answer = judgment["answer"]
        # Strict policy: middle band never auto-executes ledger mutations
        if answer == "yes":
            return EntityResolution(
                client=best,
                score=score,
                band="llm",
                llm_answer=answer,
                llm_reasoning=judgment.get("reasoning", ""),
                same_entity="yes",
                who_acts="human",
                confidence=float(judgment.get("confidence", 0.6)),
                notes="LLM says yes but score<90 — pending human (strict policy)",
                candidates=scored[:3],
            )
        if answer == "no":
            # treat as new client rather than wrong merge
            client = airtable_client.create_client(
                name=incoming_name,
                email=incoming_email,
                needs_review=True,
            )
            return EntityResolution(
                client=client,
                score=score,
                band="llm",
                llm_answer=answer,
                llm_reasoning=judgment.get("reasoning", ""),
                same_entity="no",
                who_acts="human",
                confidence=float(judgment.get("confidence", 0.6)),
                created_new=True,
                notes="LLM rejected candidate; created needs_review client",
                candidates=scored[:3],
            )
        return EntityResolution(
            client=best,
            score=score,
            band="llm",
            llm_answer="uncertain",
            llm_reasoning=judgment.get("reasoning", ""),
            same_entity="uncertain",
            who_acts="human",
            confidence=float(judgment.get("confidence", 0.4)),
            notes="LLM uncertain — pending human; no silent merge",
            candidates=scored[:3],
        )

    # < low threshold → new client
    client = airtable_client.create_client(
        name=incoming_name,
        email=incoming_email,
        needs_review=True,
    )
    return EntityResolution(
        client=client,
        score=score,
        band="new",
        same_entity="new",
        who_acts="human",
        confidence=0.25,
        created_new=True,
        notes=f"Score {score:.1f} below {low_th}; new needs_review client",
        candidates=scored[:3],
    )
