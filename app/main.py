from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app import idempotency, pending_actions, users
from app.eval_store import init_eval_db
from app.routes import auth_routes, demo, health, scorecard, tempmail_routes, user_portal, webhooks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title="Ledger Twin",
    description="Payment & identity reconciliation agent — full hackathon build",
    version="0.7.0",
)

app.include_router(health.router)
app.include_router(webhooks.router)
app.include_router(demo.router)
app.include_router(tempmail_routes.router)
app.include_router(scorecard.router)
app.include_router(auth_routes.router)
app.include_router(user_portal.router)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
def on_startup() -> None:
    idempotency.init_idempotency_db()
    pending_actions.init_pending_db()
    init_eval_db()
    users.init_users_db()
    from app.services.slack_socket import start_socket_mode

    start_socket_mode()
