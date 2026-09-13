from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NormalizedEvent(BaseModel):
    source: str
    type: str
    external_id: str
    amount_cents: Optional[int] = None
    currency: Optional[str] = None
    name_hints: List[str] = Field(default_factory=list)
    email_hints: List[str] = Field(default_factory=list)
    timestamp: datetime
    raw: dict = Field(default_factory=dict)

    def event_day(self) -> str:
        return self.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d")


class ProcessResult(BaseModel):
    status: str
    # accepted | blocked_duplicate | auto_closed | pending_* | error
    idempotency_key: str
    event: Optional[NormalizedEvent] = None
    message: str = ""
    airtable_record_id: Optional[str] = None
    axiom_ok: bool = False
    pending_action_id: Optional[str] = None
    client_record_id: Optional[str] = None
    invoice_record_id: Optional[str] = None
    payment_record_id: Optional[str] = None
    entity_score: Optional[float] = None
    triad: Optional[Dict[str, Any]] = None
