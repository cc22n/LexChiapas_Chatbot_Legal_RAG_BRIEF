"""Esquemas de respuesta de /admin/metrics/*. Un modelo por endpoint; el
frontend (lexchiapas-web/src/lib/adminApi.ts) debe reflejar estos campos."""

from datetime import date

from pydantic import BaseModel


class DayCount(BaseModel):
    day: date
    count: int


class PlatformUsers(BaseModel):
    platform: str
    unique_users: int


class PlatformCount(BaseModel):
    platform: str
    count: int


class LawMentions(BaseModel):
    ley: str | None
    mentions: int


class QuestionCount(BaseModel):
    content: str
    count: int


class UsageMetrics(BaseModel):
    questions_per_day: list[DayCount]
    unique_users_by_platform: list[PlatformUsers]
    top_laws: list[LawMentions]
    top_questions: list[QuestionCount]
    conversations_by_platform: list[PlatformCount]
    questions_per_day_telegram: list[DayCount]
    top_questions_telegram: list[QuestionCount]
