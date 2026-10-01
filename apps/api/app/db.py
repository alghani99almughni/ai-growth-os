from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

# Render Postgres may provide a generic postgresql:// URL. The API image
# installs psycopg (v3), not the legacy psycopg2 driver, so normalize the
# URL to the installed SQLAlchemy dialect/driver before creating the engine.
database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
elif database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=1,
    pool_timeout=10,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass
