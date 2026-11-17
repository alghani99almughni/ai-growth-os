"""Isolated persistence boundary for the AEO/GEO visibility module.

Visibility records live in a dedicated database so the existing AI Growth OS
operational database and its schema remain unchanged. Tenant IDs are opaque
identifiers validated by the main application's authentication layer.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


visibility_database_url = settings.visibility_database_url
if settings.environment == "production" and visibility_database_url.startswith("sqlite"):
    raise RuntimeError(
        "VISIBILITY_DATABASE_URL must point to the dedicated PostgreSQL database in production."
    )

if visibility_database_url.startswith("postgres://"):
    visibility_database_url = "postgresql+psycopg://" + visibility_database_url[len("postgres://"):]
elif visibility_database_url.startswith("postgresql://"):
    visibility_database_url = "postgresql+psycopg://" + visibility_database_url[len("postgresql://"):]

if visibility_database_url.startswith("sqlite"):
    engine = create_engine(
        visibility_database_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    engine = create_engine(
        visibility_database_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=1,
        pool_timeout=10,
        pool_recycle=1800,
    )

VisibilitySessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class VisibilityBase(DeclarativeBase):
    """Metadata root for visibility-only tables; never shared with the platform DB."""


def get_visibility_db():
    db = VisibilitySessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_visibility_db():
    # Importing the models registers their tables on VisibilityBase.metadata.
    from . import models_visibility  # noqa: F401
    VisibilityBase.metadata.create_all(bind=engine)
