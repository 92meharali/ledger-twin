from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    public_base_url: str = ""
    port: int = 8000
    demo_mode: bool = True

    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""

    airtable_api_key: str = ""
    airtable_base_id: str = ""
    airtable_table_clients: str = "Clients"
    airtable_table_invoices: str = "Invoices"
    airtable_table_payments: str = "Payments"
    airtable_table_event_log: str = "EventLog"

    axiom_token: str = ""
    axiom_dataset: str = "ledger-twin"
    axiom_org_id: str = ""
    axiom_edge: str = "us-east-1.aws.edge.axiom.co"

    temp_mail_api_base: str = "https://api.mail.tm"
    temp_mail_address: str = ""
    temp_mail_password: str = ""
    temp_mail_token: str = ""

    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_channel_id: str = ""
    slack_app_token: str = ""  # xapp-… Socket Mode (connections:write)

    auth_secret: str = "ledger-twin-dev-secret-change-me"
    auth_token_hours: int = 72

    sqlite_path: str = "./data/ledger_twin.db"
    idempotency_db_path: str = "./data/idempotency.db"

    entity_auto_match_threshold: int = 90
    entity_llm_band_low: int = 60
    amount_tolerance_cents: int = 1
    require_exact_amount_for_auto_close: bool = True


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.idempotency_db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    return settings
