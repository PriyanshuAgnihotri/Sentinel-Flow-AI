import pytest

from app.core.config import Settings


def secure_settings(**overrides) -> Settings:
    values = {
        "app_env": "staging",
        "auth_jwt_secret": "j" * 40,
        "auth_jwt_issuer": "sentinelflow-staging",
        "auth_jwt_audience": "sentinelflow-api",
        "approval_api_token": "a" * 40,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_local_environment_does_not_require_deployment_secrets():
    Settings(
        _env_file=None,
        app_env="local",
        auth_jwt_secret="",
        approval_api_token="",
    ).validate_deployment_security()


def test_valid_staging_security_configuration_passes():
    secure_settings().validate_deployment_security()


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("auth_jwt_secret", "", "AUTH_JWT_SECRET"),
        ("auth_jwt_secret", "short", "AUTH_JWT_SECRET"),
        ("auth_jwt_issuer", "", "AUTH_JWT_ISSUER"),
        ("auth_jwt_audience", "", "AUTH_JWT_AUDIENCE"),
        ("approval_api_token", "", "APPROVAL_API_TOKEN"),
        ("approval_api_token", "short", "APPROVAL_API_TOKEN"),
    ],
)
def test_staging_rejects_missing_or_weak_security_settings(
    setting, value, message
):
    with pytest.raises(ValueError, match=message):
        secure_settings(**{setting: value}).validate_deployment_security()


def test_staging_rejects_reused_jwt_and_approval_secrets():
    with pytest.raises(ValueError, match="must be different"):
        secure_settings(
            approval_api_token="j" * 40,
        ).validate_deployment_security()


@pytest.mark.parametrize("environment", ["staging", "production", "prod"])
def test_deployment_environments_require_secure_configuration(environment):
    with pytest.raises(ValueError):
        secure_settings(
            app_env=environment,
            auth_jwt_secret="",
        ).validate_deployment_security()


@pytest.mark.asyncio
async def test_staging_startup_fails_when_security_secrets_are_missing(monkeypatch):
    from app.core.config import settings as app_settings
    from app.main import app, lifespan

    monkeypatch.setattr(app_settings, "app_env", "staging")
    monkeypatch.setattr(app_settings, "auth_jwt_secret", "")
    monkeypatch.setattr(app_settings, "auth_jwt_issuer", "")
    monkeypatch.setattr(app_settings, "auth_jwt_audience", "")
    monkeypatch.setattr(app_settings, "approval_api_token", "")

    with pytest.raises(ValueError, match="Insecure deployment configuration"):
        async with lifespan(app):
            pass
