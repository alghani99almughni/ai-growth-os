from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "AI Growth OS API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://growth:growth@localhost:5432/growth_os"
    redis_url: str = "redis://localhost:6379/0"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
