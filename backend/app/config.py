from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+psycopg://chess:chess@localhost:5432/chess_intelligence"
    cors_origins: list[str] = ["http://localhost:3000"]
    engine_version: str = "0.1.0"
    llm_model: str = "claude-opus-5-5"
    analysis_workers: int = 2  # worker processes for analysis jobs; 0 = run inline in the request
    max_queued_jobs: int = 20  # pending+running jobs before POST /analysis answers 429 (no auth: bound the CPU)
    log_level: str = "INFO"
    json_logs: bool = True


settings = Settings()
