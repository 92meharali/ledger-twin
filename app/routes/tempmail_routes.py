from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services import email_ingest, tempmail

router = APIRouter(prefix="/temp-mail", tags=["temp-mail"])


class SetupResponse(BaseModel):
    address: str
    password: str
    token_set: bool
    note: str


def _write_env_temp_mail(address: str, password: str, token: str) -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    text = env_path.read_text()
    replacements = {
        "TEMP_MAIL_ADDRESS=": f"TEMP_MAIL_ADDRESS={address}",
        "TEMP_MAIL_PASSWORD=": f"TEMP_MAIL_PASSWORD={password}",
        "TEMP_MAIL_TOKEN=": f"TEMP_MAIL_TOKEN={token}",
    }
    lines = []
    seen = set()
    for line in text.splitlines():
        replaced = False
        for prefix, full in replacements.items():
            if line.startswith(prefix):
                lines.append(full)
                seen.add(prefix)
                replaced = True
                break
        if not replaced:
            lines.append(line)
    for prefix, full in replacements.items():
        if prefix not in seen:
            lines.append(full)
    env_path.write_text("\n".join(lines) + "\n")
    get_settings.cache_clear()


@router.post("/setup")
def setup_inbox() -> SetupResponse:
    """Create a mail.tm inbox and write credentials into .env."""
    try:
        acct = tempmail.create_account()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _write_env_temp_mail(acct["address"], acct["password"], acct["token"])
    return SetupResponse(
        address=acct["address"],
        password=acct["password"],
        token_set=True,
        note="Inbox created. Send a payment email to this address, then POST /temp-mail/poll",
    )


@router.get("/inbox")
def inbox_info() -> dict:
    s = get_settings()
    return {
        "address": s.temp_mail_address,
        "configured": bool(s.temp_mail_address and (s.temp_mail_token or s.temp_mail_password)),
        "api_base": s.temp_mail_api_base,
    }


@router.get("/messages")
def list_messages() -> dict:
    try:
        msgs = tempmail.list_messages()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"count": len(msgs), "messages": msgs}


@router.post("/poll")
def poll_inbox() -> dict:
    """Fetch inbox messages and ingest payment-like ones into the agent pipeline."""
    try:
        return email_ingest.poll_and_ingest()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class PlantEmailBody(BaseModel):
    subject: str = "Payment confirmation"
    body: str = Field(
        default=(
            "Hi — paid via e-transfer $1000 for invoice.\n"
            "Client: Jose Martinez Studio\n"
            "Thanks"
        )
    )
    from_name: str = "Client Ops"
    from_address: str = "client@example.com"


@router.post("/demo/plant-and-ingest")
def plant_and_ingest(body: PlantEmailBody) -> dict:
    """
    Demo without waiting for a real SMTP delivery: synthesize a mail.tm-shaped
    message and run it through the same ingest path.
    """
    if not get_settings().demo_mode:
        raise HTTPException(status_code=403, detail="DEMO_MODE is off")
    import time
    import uuid

    # Ensure there is an open $1000 invoice so exact e-transfer demos can auto-close
    from app.routes.demo import _ensure_open_invoice_1000

    _ensure_open_invoice_1000()

    fake_id = f"demo_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    msg = {
        "id": fake_id,
        "subject": body.subject,
        "text": body.body,
        "intro": body.body[:120],
        "from": {"name": body.from_name, "address": body.from_address},
    }
    return email_ingest.ingest_tempmail_message(msg)
