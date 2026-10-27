from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "SentinelFlow"
    app_env: str = "local"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinel"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    frontend_origins: str = "http://localhost:3000"
    semantic_cache_threshold: float = 0.88
    semantic_cache_ttl_seconds: int = 3600
    max_graph_steps: int = 8
    approval_api_token: str = ""
    auth_jwt_secret: str = ""
    auth_jwt_issuer: str = ""
    auth_jwt_audience: str = ""
    approval_api_actor_id: str = "approval-admin"

    @property
    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.frontend_origins.split(",") if x.strip()]

    def validate_deployment_security(self) -> None:
        """Reject insecure authentication configuration outside local development."""
        if self.app_env.strip().lower() in {"local", "development", "test"}:
            return

        problems: list[str] = []

        if len(self.auth_jwt_secret) < 32:
            problems.append("AUTH_JWT_SECRET must be at least 32 characters")

        if not self.auth_jwt_issuer.strip():
            problems.append("AUTH_JWT_ISSUER must be configured")

        if not self.auth_jwt_audience.strip():
            problems.append("AUTH_JWT_AUDIENCE must be configured")

        if len(self.approval_api_token) < 32:
            problems.append("APPROVAL_API_TOKEN must be at least 32 characters")

        if (
            self.auth_jwt_secret
            and self.approval_api_token
            and self.auth_jwt_secret == self.approval_api_token
        ):
            problems.append("JWT secret and approval token must be different")

        if problems:
            raise ValueError(
                "Insecure deployment configuration: " + "; ".join(problems)
            )


settings = Settings()
