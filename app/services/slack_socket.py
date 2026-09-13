from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from app.config import get_settings
from app.routes.webhooks import _process_slack_decision
from app.services import slack_client

logger = logging.getLogger(__name__)

_client: Any = None
_thread: Optional[threading.Thread] = None


def start_socket_mode() -> bool:
    """
    Connect outbound to Slack via Socket Mode (no public URL needed for buttons).
    Requires SLACK_APP_TOKEN (xapp-…) with connections:write + Socket Mode enabled.
    """
    global _client, _thread
    settings = get_settings()
    app_token = (settings.slack_app_token or "").strip()
    bot_token = (settings.slack_bot_token or "").strip()
    if not app_token or not bot_token:
        logger.info("Socket Mode skipped (set SLACK_APP_TOKEN to enable button clicks locally)")
        return False
    if _client is not None:
        return True

    try:
        from slack_sdk.socket_mode import SocketModeClient
        from slack_sdk.socket_mode.request import SocketModeRequest
        from slack_sdk.socket_mode.response import SocketModeResponse
        from slack_sdk.web import WebClient
    except ImportError as exc:
        logger.error("slack-sdk missing for Socket Mode: %s", exc)
        return False

    client = SocketModeClient(
        app_token=app_token,
        web_client=WebClient(token=bot_token),
    )

    def process(client_: SocketModeClient, req: SocketModeRequest) -> None:
        try:
            # Ack immediately so Slack doesn't show a failure
            client_.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
            if req.type != "interactive":
                return
            payload = req.payload or {}
            parsed = slack_client.parse_interaction(payload)
            if not parsed:
                logger.info("Socket Mode interactive ignored: %s", payload.get("type"))
                return
            logger.info(
                "Socket Mode button decision=%s pending=%s",
                parsed.get("decision"),
                parsed.get("pending_id"),
            )
            _process_slack_decision(parsed)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Socket Mode handler error: %s", exc)

    client.socket_mode_request_listeners.append(process)
    _client = client

    def run() -> None:
        logger.info("Slack Socket Mode connecting…")
        try:
            client.connect()
            logger.info("Slack Socket Mode connected")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Slack Socket Mode connect failed: %s", exc)

    _thread = threading.Thread(target=run, name="slack-socket-mode", daemon=True)
    _thread.start()
    return True


def socket_mode_enabled() -> bool:
    return _client is not None
