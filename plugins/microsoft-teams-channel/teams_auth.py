"""Bot Framework authentication helpers for Microsoft Teams channel traffic."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

BOT_CONNECTOR_SCOPE = "https://api.botframework.com/.default"
BOT_CONNECTOR_ISSUER = "https://api.botframework.com"
OPENID_CONFIGURATION_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"
REQUEST_TIMEOUT_SECONDS = 10
JWKS_CACHE_SECONDS = 24 * 60 * 60

try:
    import jwt
except Exception:  # pragma: no cover - exercised by runtime environments without PyJWT.
    jwt = None


class AuthError(Exception):
    """Raised when Teams/Bot Framework authentication fails."""


def fetch_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "Row-Bot-Teams-Channel/0.1"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise AuthError("Bot Framework metadata response was not a JSON object")
    return data


def post_form(url: str, form: dict[str, str]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Row-Bot-Teams-Channel/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        raise AuthError(f"Bot Connector token request failed with HTTP {exc.code}: {body}") from exc
    if not isinstance(data, dict):
        raise AuthError("Bot Connector token response was not a JSON object")
    return data


class BotConnectorTokenProvider:
    """Client-credentials token cache for outbound Bot Connector calls."""

    def __init__(
        self,
        *,
        app_id: Callable[[], str] | str,
        client_secret: Callable[[], str] | str,
        authority_tenant: Callable[[], str] | str = "botframework.com",
        post_form_func: Callable[[str, dict[str, str]], dict[str, Any]] = post_form,
        now_func: Callable[[], float] = time.time,
    ) -> None:
        self._app_id = app_id
        self._client_secret = client_secret
        self._authority_tenant = authority_tenant
        self._post_form = post_form_func
        self._now = now_func
        self._token = ""
        self._expires_at = 0.0

    def get_token(self) -> str:
        now = self._now()
        if self._token and now < self._expires_at - 300:
            return self._token

        app_id = _resolve(self._app_id).strip()
        secret = _resolve(self._client_secret).strip()
        tenant = _resolve(self._authority_tenant).strip() or "botframework.com"
        if not app_id or not secret:
            raise AuthError("Microsoft App ID and bot client secret are required")

        url = f"https://login.microsoftonline.com/{urllib.parse.quote(tenant, safe='')}/oauth2/v2.0/token"
        data = self._post_form(
            url,
            {
                "grant_type": "client_credentials",
                "client_id": app_id,
                "client_secret": secret,
                "scope": BOT_CONNECTOR_SCOPE,
            },
        )
        token = str(data.get("access_token") or "")
        if not token:
            raise AuthError("Bot Connector token response did not include access_token")
        try:
            expires_in = int(data.get("expires_in") or 3600)
        except (TypeError, ValueError):
            expires_in = 3600
        self._token = token
        self._expires_at = now + max(60, expires_in)
        return self._token


class BotFrameworkJWTVerifier:
    """Validate Bot Framework inbound bearer tokens using OpenID metadata/JWKS."""

    def __init__(
        self,
        *,
        fetch_json_func: Callable[[str], dict[str, Any]] = fetch_json,
        now_func: Callable[[], float] = time.time,
    ) -> None:
        self._fetch_json = fetch_json_func
        self._now = now_func
        self._openid: dict[str, Any] = {}
        self._openid_fetched_at = 0.0
        self._jwks: dict[str, Any] = {}
        self._jwks_fetched_at = 0.0

    def verify_authorization_header(
        self,
        authorization: str,
        *,
        bot_app_id: str,
        activity: dict[str, Any],
    ) -> dict[str, Any]:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise AuthError("Missing Bot Framework bearer token")
        if jwt is None:
            raise AuthError("PyJWT with crypto support is required for Bot Framework JWT verification")
        token = authorization.split(None, 1)[1].strip()
        if not token:
            raise AuthError("Missing Bot Framework bearer token")
        if not bot_app_id:
            raise AuthError("Microsoft App ID is required before validating Teams traffic")

        try:
            header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise AuthError("Invalid Bot Framework JWT header") from exc
        if str(header.get("alg") or "") != "RS256":
            raise AuthError("Bot Framework JWT must use RS256")
        kid = str(header.get("kid") or "")
        if not kid:
            raise AuthError("Bot Framework JWT is missing a key id")

        jwk = self._find_jwk(kid)
        if jwk is None:
            self._jwks_fetched_at = 0.0
            jwk = self._find_jwk(kid)
        if jwk is None:
            raise AuthError("Bot Framework signing key was not found")
        endorsements = jwk.get("endorsements")
        if isinstance(endorsements, list) and endorsements and "msteams" not in endorsements:
            raise AuthError("Bot Framework signing key is not endorsed for Microsoft Teams")

        try:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=bot_app_id,
                issuer=BOT_CONNECTOR_ISSUER,
                leeway=300,
            )
        except Exception as exc:
            raise AuthError("Bot Framework JWT validation failed") from exc

        service_claim = str(claims.get("serviceurl") or claims.get("serviceUrl") or "")
        service_url = str(activity.get("serviceUrl") or "")
        if service_claim and service_url and service_claim != service_url:
            raise AuthError("Bot Framework JWT serviceUrl does not match activity")
        return dict(claims)

    def _openid_config(self) -> dict[str, Any]:
        if self._openid and self._now() < self._openid_fetched_at + JWKS_CACHE_SECONDS:
            return self._openid
        self._openid = self._fetch_json(OPENID_CONFIGURATION_URL)
        self._openid_fetched_at = self._now()
        return self._openid

    def _jwks_doc(self) -> dict[str, Any]:
        if self._jwks and self._now() < self._jwks_fetched_at + JWKS_CACHE_SECONDS:
            return self._jwks
        jwks_uri = str(self._openid_config().get("jwks_uri") or "")
        if not jwks_uri:
            raise AuthError("Bot Framework OpenID metadata did not include jwks_uri")
        self._jwks = self._fetch_json(jwks_uri)
        self._jwks_fetched_at = self._now()
        return self._jwks

    def _find_jwk(self, kid: str) -> dict[str, Any] | None:
        keys = self._jwks_doc().get("keys", [])
        if not isinstance(keys, list):
            return None
        for key in keys:
            if isinstance(key, dict) and str(key.get("kid") or "") == kid:
                return dict(key)
        return None


def _resolve(value: Callable[[], str] | str) -> str:
    return str(value() if callable(value) else value or "")
