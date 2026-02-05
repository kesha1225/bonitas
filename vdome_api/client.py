from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests
import json


@dataclass
class Tokens:
    access_token: str
    refresh_token: str


@dataclass
class OAuthConfig:
    """OAuth2 configuration for MTS SSO."""
    authorize_url: str = "https://login.mts.ru/amserver/oauth2/authorize"
    client_id: str = "VDome"
    redirect_uri: str = "https://gateway.vdome.mts.ru/user-service/api/auth/callback"
    scopes: str = "openid profile phone sso ssom address account"


class VdomeApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        errors: Any | None = None,
        response_data: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.errors = errors
        self.response_data = response_data


class VdomeClient:
    def __init__(
        self,
        resident_base_url: str = "https://resident-rest.vdome.mts.ru",
        gateway_base_url: str = "https://gateway.vdome.mts.ru",
        device_type: str = "ANDROID",
        device_token: str | None = None,
        user_agent: str = "okhttp/4.12.0",
        timeout: float = 20.0,
        session: requests.Session | None = None,
    ) -> None:
        self.resident_base_url = resident_base_url.rstrip("/")
        self.gateway_base_url = gateway_base_url.rstrip("/")
        self.device_type = device_type
        self.device_token = device_token
        self.user_agent = user_agent
        self.timeout = timeout
        self.session = session or requests.Session()

    def _base_headers(self, request_id: str | None, access_token: str | None) -> dict[str, str]:
        headers = {
            "X-Device-Type": self.device_type,
            "Request-Id": request_id or str(uuid.uuid4()),
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if self.device_token:
            headers["X-Device-Token"] = self.device_token
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
            headers["X-Auth-Token"] = access_token
        return headers

    def _parse_json(self, response: requests.Response) -> Any | None:
        try:
            return response.json()
        except ValueError:
            return None

    def _unwrap_common_response(self, response: requests.Response, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "result" not in data and "errors" not in data and "message" not in data:
            return data
        errors = data.get("errors")
        if errors:
            raise VdomeApiError(
                data.get("message") or "API error",
                status_code=response.status_code,
                errors=errors,
                response_data=data,
            )
        return data.get("result")

    def _request(
        self,
        method: str,
        url: str,
        *,
        access_token: str | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        req_headers = self._base_headers(
            request_id=(headers or {}).get("Request-Id"),
            access_token=access_token,
        )
        if headers:
            req_headers.update(headers)
        response = self.session.request(
            method,
            url,
            headers=req_headers,
            timeout=self.timeout,
            **kwargs,
        )
        data = self._parse_json(response)
        if not response.ok:
            message = None
            errors = None
            if isinstance(data, dict):
                message = data.get("message") or data.get("error") or data.get("detail")
                errors = data.get("errors")
            raise VdomeApiError(
                message or f"HTTP {response.status_code}",
                status_code=response.status_code,
                errors=errors,
                response_data=data,
            )
        if data is None:
            return response.content
        return self._unwrap_common_response(response, data)

    def auth_init(self, phone: str) -> Any:
        """Initiate auth - sends SMS code to the phone number.

        Args:
            phone: Phone number in format +79XXXXXXXXX

        Returns:
            Response data from the server
        """
        payload = {"phone": phone}
        return self._request(
            "POST",
            f"{self.gateway_base_url}/user-service/api/v2/auth/init",
            json=payload,
        )

    def auth_login(self, phone: str, code: str) -> Tokens:
        """Complete auth with SMS code.

        Args:
            phone: Phone number in format +79XXXXXXXXX
            code: SMS verification code

        Returns:
            Tokens object with access_token and refresh_token
        """
        payload = {"phone": phone, "code": code}
        result = self._request(
            "POST",
            f"{self.gateway_base_url}/user-service/api/v2/auth/login",
            json=payload,
        )
        if not isinstance(result, dict):
            raise VdomeApiError("Unexpected auth response", response_data=result)
        access_token = result.get("accessToken")
        refresh_token = result.get("refreshToken")
        if not access_token or not refresh_token:
            raise VdomeApiError("Missing tokens in auth response", response_data=result)
        return Tokens(access_token=access_token, refresh_token=refresh_token)

    def auth_refresh(self, refresh_token: str) -> str:
        """Refresh access token.

        Args:
            refresh_token: The refresh token

        Returns:
            New access token
        """
        payload = {"refreshToken": refresh_token}
        result = self._request(
            "PUT",
            f"{self.gateway_base_url}/user-service/api/v2/auth/refresh",
            json=payload,
        )
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            access_token = result.get("accessToken") or result.get("token")
            if access_token:
                return access_token
        raise VdomeApiError("Unexpected refresh response", response_data=result)

    def get_cameras(self, access_token: str, limit: int = 1000) -> Any:
        result = self._request(
            "GET",
            f"{self.gateway_base_url}/domofon/api/intercom/v1/cameras",
            access_token=access_token,
            params={"limit": limit},
        )
        if isinstance(result, dict) and "list" in result:
            return result.get("list") or []
        return result

    def get_intercoms(
        self,
        access_token: str,
        *,
        category: str | None = None,
        limit: int = 1000,
    ) -> Any:
        params = {"limit": limit}
        if category:
            params["category"] = category
        result = self._request(
            "GET",
            f"{self.gateway_base_url}/domofon/api/intercom/v2/intercoms",
            access_token=access_token,
            params=params,
        )
        if isinstance(result, dict):
            if "list" in result:
                return result.get("list") or []
            if "intercoms" in result:
                return result.get("intercoms") or []
        return result

    def open_intercom(
        self,
        access_token: str,
        intercom_id: str,
        lock_number: int | None = None,
    ) -> Any:
        payload = {"action": "open"}
        url = f"{self.gateway_base_url}/domofon/api/intercom/v2/intercoms/{intercom_id}/lock"
        if lock_number is not None:
            url = f"{url}/{lock_number}"
        return self._request("POST", url, access_token=access_token, json=payload)

    def get_preview_image(self, watch_token: str, api_host: str, camid: int) -> bytes:
        url = f"https://{api_host}/api/v2/cameras/{camid}/preview/"
        headers = {
            "Authorization": f"Acc {watch_token}",
        }
        response = self.session.get(
            url,
            headers=self._base_headers(request_id=None, access_token=None) | headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.content

    # OAuth2 methods for MTS SSO

    def get_oauth_authorize_url(self, config: OAuthConfig | None = None) -> str:
        """Get the OAuth2 authorization URL for MTS SSO.

        Open this URL in a browser to start the login flow.
        After successful login, MTS will redirect to the callback URL
        with a 'code' parameter that you can exchange for tokens.

        Args:
            config: OAuth configuration, uses defaults if not provided

        Returns:
            Authorization URL to open in browser
        """
        cfg = config or OAuthConfig()
        state = str(uuid.uuid4())
        params = {
            "client_id": cfg.client_id,
            "redirect_uri": cfg.redirect_uri,
            "response_type": "code",
            "scope": cfg.scopes,
            "state": state,
        }
        return f"{cfg.authorize_url}?{urlencode(params)}"

    def exchange_oauth_code(self, callback_url: str) -> Tokens:
        """Exchange OAuth2 authorization code for tokens.

        After MTS SSO redirects to the callback URL with ?code=XXX,
        call this method with the full callback URL to get tokens.

        Args:
            callback_url: The full callback URL including ?code=XXX parameter

        Returns:
            Tokens object with access_token and refresh_token
        """
        original_url = callback_url
        if "\\" in callback_url:
            # Handle shell-escaped URLs like "\?code\=..."
            callback_url = (
                callback_url.replace("\\?", "?")
                .replace("\\&", "&")
                .replace("\\=", "=")
                .replace("\\/", "/")
            )

        parsed = urlparse(callback_url)
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if not code:
            hint = ""
            if "\\" in original_url:
                hint = (
                    " Hint: remove backslashes before ?, &, = (wrap URL in single quotes)."
                )
            raise VdomeApiError(
                f"No 'code' parameter in callback URL: {original_url}{hint}"
            )

        # The callback URL itself returns the tokens when accessed
        response = self.session.get(
            callback_url,
            headers=self._base_headers(request_id=None, access_token=None),
            timeout=self.timeout,
        )
        data = self._parse_json(response)
        if not response.ok:
            raise VdomeApiError(
                f"HTTP {response.status_code}",
                status_code=response.status_code,
                response_data=data,
            )

        # Try to extract tokens from response
        if isinstance(data, str):
            # Response might be the token data as string (HTML or JSON string)
            try:
                import json
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                pass

        if isinstance(data, dict):
            # Unwrap CommonResponse if needed
            result = data.get("result", data)
            if isinstance(result, dict):
                access_token = result.get("accessToken")
                refresh_token = result.get("refreshToken")
                if access_token and refresh_token:
                    return Tokens(access_token=access_token, refresh_token=refresh_token)

        raise VdomeApiError(
            "Could not extract tokens from callback response",
            response_data=data,
        )

    def tokens_from_callback_payload(self, payload: Any) -> Tokens:
        """Parse tokens from the callback JSON payload.

        The callback page can return JSON with a keycloakTokenPair
        containing accessToken/refreshToken.
        """
        data = payload
        if isinstance(payload, str):
            try:
                data = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                raise VdomeApiError("Invalid JSON payload for tokens")

        if not isinstance(data, dict):
            raise VdomeApiError("Unexpected token payload type", response_data=data)

        token_pair = data.get("keycloakTokenPair")
        if isinstance(token_pair, dict):
            access_token = token_pair.get("accessToken") or token_pair.get("access_token")
            refresh_token = token_pair.get("refreshToken") or token_pair.get("refresh_token")
            if access_token and refresh_token:
                return Tokens(access_token=access_token, refresh_token=refresh_token)

        access_token = data.get("accessToken") or data.get("access_token")
        refresh_token = data.get("refreshToken") or data.get("refresh_token")
        if access_token and refresh_token:
            return Tokens(access_token=access_token, refresh_token=refresh_token)

        raise VdomeApiError("Could not extract tokens from payload", response_data=data)
