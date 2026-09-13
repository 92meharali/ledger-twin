from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

from app.eval_runner import run_eval_suite
from app.services import scorecard

router = APIRouter(tags=["scorecard"])


@router.get("/scorecard")
def get_scorecard() -> dict:
    return scorecard.build_scorecard()


@router.post("/eval/run")
def eval_run() -> dict:
    try:
        return run_eval_suite()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/dashboard")
def dashboard_page():
    path = Path(__file__).resolve().parent.parent / "static" / "dashboard.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="dashboard.html missing")
    return FileResponse(path)


@router.get("/app")
def user_app_page():
    path = Path(__file__).resolve().parent.parent / "static" / "portal.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="portal.html missing")
    return FileResponse(path)


@router.get("/")
def home_redirect():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/app")
