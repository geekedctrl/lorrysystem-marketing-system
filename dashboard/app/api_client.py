from __future__ import annotations

from typing import Any

import httpx

from .config import Settings
from .workspace_context import request_auth


class MarketingAPIError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.payload = payload


class MarketingAPI:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> Any:
        headers = {}
        if authenticated:
            auth = request_auth.get()
            if not auth or not auth.get('token'):
                raise MarketingAPIError(401, 'Sign in required.')
            headers['Authorization'] = 'Bearer ' + auth['token']
            if auth.get('workspace_id'):
                headers['X-Workspace-ID'] = auth['workspace_id']

        try:
            async with httpx.AsyncClient(
                base_url=self.settings.api_base_url,
                timeout=12.0,
                follow_redirects=False,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    headers=headers,
                )
        except httpx.RequestError as exc:
            raise MarketingAPIError(
                503,
                "Marketing API is currently unavailable.",
            ) from exc

        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = None

            raise MarketingAPIError(
                response.status_code,
                self._friendly_error(
                    response.status_code,
                    payload,
                ),
                payload,
            )

        if response.status_code == 204:
            return None

        try:
            return response.json()
        except ValueError:
            return response.text

    @staticmethod
    def _friendly_error(
        status_code: int,
        payload: Any,
    ) -> str:
        detail = None
        if isinstance(payload, dict):
            detail = payload.get("detail")

        if status_code == 401:
            return "Sign in again or check your credentials."
        if status_code == 404:
            return "The requested record was not found."
        if status_code == 409:
            if isinstance(detail, str):
                return detail
            return "This operation conflicts with an existing record or current state."
        if status_code == 422:
            return "Please check the submitted fields and try again."
        if status_code == 503 and detail in (
            "Platform SMTP credential encryption is not configured",
            "Sender credentials are unavailable; reconnect the account",
        ):
            return detail
        if status_code >= 500:
            return "The Marketing API encountered an error."
        if isinstance(detail, str):
            return detail
        return "The request could not be completed."

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self.request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> Any:
        return await self.request("PATCH", path, **kwargs)
