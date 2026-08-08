from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # BUG REAL (auditoria de base de datos, 2026-08-06): sin estos limites
    # explicitos, FastAPI y los workers de Celery (que comparten el mismo
    # Postgres, cada uno con su propio engine/pool) dependen de los
    # defaults de SQLAlchemy (pool_size=5, max_overflow=10) sin timeout --
    # bajo carga concurrente real, una request que no consigue conexion se
    # queda esperando indefinidamente en vez de fallar rapido con un error
    # claro. connect_timeout va en connect_args porque es un parametro de
    # psycopg (nivel conexion TCP), no de SQLAlchemy (nivel pool).
    pool_size=5,
    max_overflow=10,
    pool_timeout=10,
    connect_args={"connect_timeout": 10},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
