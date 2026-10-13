from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from .taxonomy import CATEGORIES, Category, Status, Urgency


class Classification(BaseModel):
    category: Category
    urgency: Urgency
    urgency_score: int = Field(ge=1, le=100)
    summary: str = Field(min_length=1, max_length=280)
    rationale: str = Field(min_length=1, max_length=600)
    suggested_owner: str = Field(min_length=1, max_length=80)

    @field_validator("summary", "rationale", "suggested_owner", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class SubmitRequest(BaseModel):
    requester_name: str = Field(min_length=2, max_length=80)
    requester_email: EmailStr
    team: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=4, max_length=140)
    details: str = Field(min_length=12, max_length=4000)
    impact: str = Field(min_length=4, max_length=400)

    @field_validator("requester_name", "team", "title", "details", "impact", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class StatusUpdate(BaseModel):
    status: Status
    note: Optional[str] = Field(default=None, max_length=400)


class RequestRecord(BaseModel):
    id: int
    requester_name: str
    requester_email: str
    team: str
    title: str
    details: str
    impact: str
    status: Status
    category: Optional[str] = None
    urgency: Optional[str] = None
    urgency_score: Optional[int] = None
    summary: Optional[str] = None
    rationale: Optional[str] = None
    suggested_owner: Optional[str] = None
    classification_error: Optional[str] = None
    model: Optional[str] = None
    created_at: str
    updated_at: str
    classified_at: Optional[str] = None
    status_note: Optional[str] = None


class Health(BaseModel):
    ok: bool
    ollama: bool
    model: str
    available_models: list[str]
    org_email_domain: Optional[str]
    categories: list[str] = Field(default_factory=lambda: CATEGORIES)
