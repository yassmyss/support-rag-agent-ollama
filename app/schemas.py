from pydantic import BaseModel, Field, field_validator
from typing import Literal
from uuid import UUID


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    logs: str = Field(default="", max_length=12000)
    session_id: UUID | None = None

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value):
        return value.strip() if isinstance(value, str) else value


class Source(BaseModel):
    source: str
    excerpt: str


class AskResponse(BaseModel):
    category: str
    answer: str
    sources: list[Source]
    session_id: str
    trace: list["ToolTrace"]
    escalations: list["Escalation"]
    limit_reached: bool = False


class ToolTrace(BaseModel):
    tool: str
    status: Literal["ok", "error", "skipped"]
    summary: str
    origin: Literal["workflow", "agent"]


class Escalation(BaseModel):
    summary: str
    reason: str
    impact: Literal["unknown", "one_user", "multiple_users", "critical_service"]
    priority: Literal["normal", "high"]
    checks: list[str]
    missing_information: list[str]
    status: Literal["draft"]
