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


class NotFoundRate(BaseModel):
    not_found: int
    total: int


class RatingCount(BaseModel):
    rating: str
    count: int


class CitedArticle(BaseModel):
    ley: str | None
    articulo: str | None
    mentions: int


class SimilarityBucket(BaseModel):
    range: str
    count: int


class RewriteGrounding(BaseModel):
    was_rewritten: bool
    grounded: int
    total: int


class QualityMetrics(BaseModel):
    not_found_rate: NotFoundRate
    feedback_ratio: list[RatingCount]
    feedback_ratio_telegram: list[RatingCount]
    top_cited_articles: list[CitedArticle]
    # null si todavia no hay ningun mensaje grounded.
    avg_similarity_grounded: float | None
    # Los buckets sin datos vienen AUSENTES del arreglo (el frontend los trata como 0).
    similarity_histogram: list[SimilarityBucket]
    grounded_by_rewrite: list[RewriteGrounding]
