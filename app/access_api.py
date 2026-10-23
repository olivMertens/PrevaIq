"""Internal access-request endpoints.

Called only by the Next.js server (API key injected server-side). The browser
catch-all proxy refuses ``/api/internal/*``, and the admin-only routes check the
session role in the frontend before calling the decision endpoints.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal, Optional

from azure.core.exceptions import AzureError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import access_requests
from app.utils import setup_logging

logger = setup_logging()


def storage_errors():
    try:
        yield
    except (AzureError, OSError, TimeoutError, ValueError) as error:
        logger.error("Access request storage unavailable: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="access request storage unavailable") from error


router = APIRouter(
    prefix="/api/internal/access", tags=["access"], dependencies=[Depends(storage_errors)]
)


class AccessRequestBody(BaseModel):
    email: str = Field(max_length=254)
    name: Optional[str] = Field(default=None, max_length=200)


class DecisionBody(BaseModel):
    decision: Literal["approve", "refuse"]
    admin: str = Field(max_length=120)


class AuthorizeBody(BaseModel):
    email: str = Field(max_length=254)
    admin: str = Field(max_length=120)


def _email(value: str) -> str:
    email = access_requests.normalize(value)
    if not access_requests.is_valid_email(email):
        raise HTTPException(status_code=422, detail="invalid email")
    return email


@router.get("/status")
def access_status(email: str) -> dict:
    return {"status": access_requests.status_of(_email(email))}


@router.post("/request")
def access_request(body: AccessRequestBody) -> dict:
    return asdict(access_requests.request(_email(body.email), body.name))


@router.get("")
def access_list() -> dict:
    items = [asdict(entry) for entry in access_requests.list_entries()]
    return {"pending": sum(i["status"] == "pending" for i in items), "items": items}


@router.post("/authorize")
def access_authorize(body: AuthorizeBody) -> dict:
    return asdict(access_requests.authorize(_email(body.email), body.admin))


@router.post("/{entry_id}/decision")
def access_decide(entry_id: str, body: DecisionBody) -> dict:
    try:
        return asdict(access_requests.decide(entry_id, body.decision, body.admin))
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown access request") from None
