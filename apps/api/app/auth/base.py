"""인증 인터페이스. # P1-API-01"""

import secrets
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: uuid.UUID
    email: str
    role: str = "user"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class AuthError(Exception):
    """토큰이 없거나 유효하지 않음(401)."""


class AuthBackend(ABC):
    @abstractmethod
    async def authenticate(self, token: str) -> Principal:
        """Bearer 토큰 → Principal. 실패 시 AuthError."""

    def issue(self, principal: Principal, *, ttl: timedelta | None = None) -> str:
        """개발용·익명 토큰 발급(local만 지원). 외부 IdP는 클라이언트가 직접 로그인한다.
        ttl을 주면 기본 유효 시간 대신 쓴다(익명 토큰 30일)."""
        raise NotImplementedError("이 인증 공급자는 서버에서 토큰을 발급하지 않는다")


class AdminVerifier(ABC):
    """운영 화면 접근 검증. local은 role=admin, 배포 시 Cloudflare Access."""

    @abstractmethod
    async def verify(self, principal: Principal | None, headers: Mapping[str, str]) -> bool: ...


class RoleAdminVerifier(AdminVerifier):
    async def verify(self, principal: Principal | None, headers: Mapping[str, str]) -> bool:
        return principal is not None and principal.is_admin


ADMIN_TOKEN_HEADER = "x-admin-token"  # noqa: S105 (헤더 이름)


class TokenAdminVerifier(AdminVerifier):
    """ADMIN_AUTH=token: X-Admin-Token 헤더가 ADMIN_TOKEN과 같으면 운영자. 로그인 여부와 무관하다."""

    def __init__(self, *, token: str) -> None:
        self._token = token.encode()

    async def verify(self, principal: Principal | None, headers: Mapping[str, str]) -> bool:
        given = headers.get(ADMIN_TOKEN_HEADER, "").strip()
        return bool(given) and secrets.compare_digest(given.encode(), self._token)


# 운영 토큰만으로 들어온 요청의 주체. 운영 API는 주체 정보를 쓰지 않는다.
TOKEN_ADMIN = Principal(user_id=uuid.UUID(int=0), email="admin-token", role="admin")
