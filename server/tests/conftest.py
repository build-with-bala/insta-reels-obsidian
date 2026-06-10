import pytest

from server.config import API_KEY_ENV_VAR


@pytest.fixture(autouse=True)
def _clean_api_key_env(monkeypatch):
    """Keep the host machine's env from leaking into config tests.

    Tests that exercise env-var support set API_KEY_ENV_VAR explicitly via
    monkeypatch.setenv.
    """
    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)
