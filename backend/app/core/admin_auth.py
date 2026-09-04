import secrets

from app.core.errors import (
    AdminAuthenticationError,
    AdminAuthenticationNotConfiguredError,
)


class AdminApiKeyAuthenticator:
    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key

    def authenticate(self, candidate: str | None) -> None:
        if self._api_key is None:
            raise AdminAuthenticationNotConfiguredError
        if candidate is None or not secrets.compare_digest(candidate, self._api_key):
            raise AdminAuthenticationError
