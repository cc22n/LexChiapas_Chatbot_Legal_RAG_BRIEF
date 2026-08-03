from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)  # ley/reglamento/decreto
    fecha_publicacion: Mapped[date | None] = mapped_column(Date)
    fecha_ultima_reforma: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(500))
    area_derecho: Mapped[str | None] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
