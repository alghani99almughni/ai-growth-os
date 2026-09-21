from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "AI Growth OS API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://growth:growth@localhost:5432/growth_os"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
