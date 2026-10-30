from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "dev-insecure-key-change-me-0123456789abcdef"
    access_token_minutes: int = 480
    cors_origins: str = "http://localhost"
    admin_email: str | None = None
    admin_password: str | None = None
    wp_url: str | None = None
    wp_username: str | None = None
    wp_app_password: str | None = None
    user_agent: str = "KaziRobot/1.0"

settings = Settings()
