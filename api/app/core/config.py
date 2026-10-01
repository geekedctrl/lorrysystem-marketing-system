from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "LorrySystem Marketing API"
    app_env: str = "development"

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str


settings = Settings()
