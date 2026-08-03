from datetime import date, datetime

from pydantic import BaseModel


class DocumentCreate(BaseModel):
    nombre: str
    tipo: str
    fecha_publicacion: date | None = None
    fecha_ultima_reforma: date | None = None
    source_url: str | None = None
    area_derecho: str | None = None


class DocumentOut(BaseModel):
    id: int
    nombre: str
    tipo: str
    fecha_publicacion: date | None
    fecha_ultima_reforma: date | None
    source_url: str | None
    area_derecho: str | None
    is_active: bool
    ingested_at: datetime

    class Config:
        from_attributes = True
