from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import create_access_token, get_current_user
from app import users as users_db

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupBody(BaseModel):
    email: str
    password: str = Field(min_length=6)
    full_name: str = ""
    company: str = ""


class LoginBody(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    company: Optional[str] = None
    bio: Optional[str] = None
    email: Optional[str] = None


@router.post("/signup")
def signup(body: SignupBody) -> dict:
    try:
        user = users_db.create_user(
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            company=body.company,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token = create_access_token(user["id"])
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.post("/login")
def login(body: LoginBody) -> dict:
    user = users_db.authenticate(body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"])
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return {"user": user}


@router.patch("/me")
def update_me(body: ProfileUpdate, user: dict = Depends(get_current_user)) -> dict:
    try:
        updated = users_db.update_user(
            user["id"],
            full_name=body.full_name,
            company=body.company,
            bio=body.bio,
            email=body.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"user": updated}


@router.delete("/me")
def delete_me(user: dict = Depends(get_current_user)) -> dict:
    try:
        users_db.delete_user(user["id"])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "message": "Account deleted"}
