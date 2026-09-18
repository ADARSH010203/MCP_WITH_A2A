"""Authentication and network validation for A2A push notifications."""

import asyncio
import hashlib
import ipaddress
import json
import logging
import socket
import threading
import time
import uuid
from urllib.parse import urlparse
from typing import Any

import httpx
import jwt
from jwcrypto import jwk  # type: ignore
from jwt import PyJWK, PyJWKClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config.settings import settings

logger = logging.getLogger(__name__)
AUTH_HEADER_PREFIX = "Bearer "
TOKEN_MAX_AGE_SECONDS = 60 * 5
TOKEN_FUTURE_SKEW_SECONDS = 60


class PushNotificationAuth:
    def _calculate_request_body_sha256(self, data: dict[str, Any]) -> str:
        """Calculate the canonical SHA-256 digest used by sender and receiver."""
        body_str = json.dumps(
            data,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        )
        return hashlib.sha256(body_str.encode()).hexdigest()


class PushNotificationSenderAuth(PushNotificationAuth):
    def __init__(self) -> None:
        self.public_keys: list[dict[str, Any]] = []
        self.private_key_jwk: PyJWK | None = None

    @staticmethod
    async def _is_safe_push_url(url: str) -> bool:
        """Reject callback URLs that can target local/private infrastructure.

        DNS resolution is checked before the request, redirects are disabled on
        the HTTP call, and production defaults require HTTPS. Network egress
        controls are still recommended because DNS can change after validation.
        """
        try:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                return False
            if parsed.username or parsed.password:
                return False
            if settings.push_notification_require_https and parsed.scheme != "https":
                return False

            if settings.push_notification_allow_private_networks:
                return True

            hostname = parsed.hostname
            if hostname in {"localhost", "localhost.localdomain"}:
                return False

            try:
                addresses = {
                    ipaddress.ip_address(hostname),
                }
            except ValueError:
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                infos = await asyncio.to_thread(
                    socket.getaddrinfo,
                    hostname,
                    port,
                    type=socket.SOCK_STREAM,
                )
                addresses = {ipaddress.ip_address(info[4][0]) for info in infos}

            return all(
                not (
                    address.is_private
                    or address.is_loopback
                    or address.is_link_local
                    or address.is_reserved
                    or address.is_unspecified
                )
                for address in addresses
            )
        except (OSError, ValueError):
            return False

    @classmethod
    async def verify_push_notification_url(cls, url: str) -> bool:
        if not await cls._is_safe_push_url(url):
            logger.warning("Rejected unsafe push-notification URL")
            return False

        try:
            validation_token = str(uuid.uuid4())
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.get(
                    url,
                    params={"validationToken": validation_token},
                )
                response.raise_for_status()
                is_verified = response.text == validation_token
                logger.info("Push-notification URL verified: %s => %s", url, is_verified)
                return is_verified
        except httpx.HTTPError as exc:
            logger.warning("Push-notification URL verification failed: %s", exc)
            return False

    def generate_jwk(self) -> None:
        key = jwk.JWK.generate(kty="RSA", size=2048, kid=str(uuid.uuid4()), use="sig")
        self.public_keys.append(key.export_public(as_dict=True))
        self.private_key_jwk = PyJWK.from_json(key.export_private())

    def handle_jwks_endpoint(self, _request: Request) -> JSONResponse:
        """Return the sender public keys used for JWT verification."""
        return JSONResponse({"keys": self.public_keys})

    def _generate_jwt(self, data: dict[str, Any]) -> str:
        if self.private_key_jwk is None:
            raise RuntimeError("Push-notification signing key has not been generated")

        iat = int(time.time())
        return jwt.encode(
            {
                "iat": iat,
                "jti": str(uuid.uuid4()),
                "request_body_sha256": self._calculate_request_body_sha256(data),
            },
            key=self.private_key_jwk,
            headers={"kid": self.private_key_jwk.key_id},
            algorithm="RS256",
        )

    async def send_push_notification(self, url: str, data: dict[str, Any]) -> bool:
        if not await self._is_safe_push_url(url):
            logger.warning("Rejected unsafe push-notification delivery URL")
            return False

        jwt_token = self._generate_jwt(data)
        headers = {"Authorization": f"Bearer {jwt_token}"}

        try:
            async with httpx.AsyncClient(
                timeout=10,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    url,
                    json=data,
                    headers=headers,
                )
                response.raise_for_status()
                logger.info("Push-notification sent successfully")
                return True
        except httpx.HTTPError as exc:
            logger.warning("Push-notification delivery failed: %s", exc)
            return False


class PushNotificationReceiverAuth(PushNotificationAuth):
    def __init__(self) -> None:
        self.jwks_client: PyJWKClient | None = None
        self._used_jti: dict[str, float] = {}
        self._jti_lock = threading.Lock()

    async def load_jwks(self, jwks_url: str) -> None:
        self.jwks_client = PyJWKClient(jwks_url)

    async def verify_push_notification(self, request: Request) -> bool:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith(AUTH_HEADER_PREFIX):
            logger.warning("Invalid push-notification authorization header")
            return False

        if self.jwks_client is None:
            logger.warning("Push-notification JWKS client is not configured")
            return False

        token = auth_header[len(AUTH_HEADER_PREFIX) :].strip()
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            decoded = jwt.decode(
                token,
                signing_key,
                options={"require": ["iat", "jti", "request_body_sha256"]},
                algorithms=["RS256"],
            )
        except (jwt.PyJWTError, ValueError) as exc:
            logger.warning("Invalid push-notification token: %s", exc)
            return False

        now = time.time()
        issued_at = float(decoded["iat"])
        if now - issued_at > TOKEN_MAX_AGE_SECONDS:
            logger.warning("Expired push-notification token")
            return False
        if issued_at - now > TOKEN_FUTURE_SKEW_SECONDS:
            logger.warning("Push-notification token is from the future")
            return False

        jti = str(decoded["jti"])
        with self._jti_lock:
            cutoff = now - TOKEN_MAX_AGE_SECONDS
            self._used_jti = {
                key: expiry for key, expiry in self._used_jti.items() if expiry > cutoff
            }
            if jti in self._used_jti:
                logger.warning("Replay detected for push-notification token")
                return False
            self._used_jti[jti] = now + TOKEN_MAX_AGE_SECONDS

        actual_body_sha256 = self._calculate_request_body_sha256(await request.json())
        if actual_body_sha256 != decoded["request_body_sha256"]:
            logger.warning("Push-notification body digest mismatch")
            return False

        return True
