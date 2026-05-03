from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./logistics.db"
    app_env: str = "development"
    log_level: str = "INFO"
    claude_model: str = "claude-sonnet-4-6"
    # Webhook authentication — leave empty to disable (dev/testing mode)
    webhook_secret: str = ""
    # Cost per token in USD (claude-sonnet-4-6 pricing)
    cost_per_input_token: float = 0.000003    # $3 / 1M input tokens
    cost_per_output_token: float = 0.000015   # $15 / 1M output tokens


settings = Settings()
