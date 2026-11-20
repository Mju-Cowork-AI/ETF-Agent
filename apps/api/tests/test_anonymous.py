"""로그인 없는 접근: 익명 발급, 대화 분리, 수준, 운영 보호(ADMIN_AUTH=token). 외부 호출은 모두 fake."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import select

from app.auth import build_admin_verifier
from app.db import get_sessionmaker
from app.repositories.models import Message, User
from app.settings import AdminAuth, AppEnv, AuthProvider, Settings
from tests.conftest import login
from tests.sse import parse_sse

ADMIN_TOKEN = "test-only-admin-token-0123456789abcdef"  # noqa: S105 (테스트용 값, 32자 이상)
ADMIN_PATHS = ["/admin/traces", "/admin/feedback", "/admin/documents", "/admin/search?q=ETF"]


def _enable_anon(app: FastAPI) -> None:
    c = app.state.container
    c.settings = c.settings.model_copy(update={"anon_access_enabled": True})


def _token_admin_mode(app: FastAPI) -> None:
    c = app.state.container
    c.settings = c.settings.model_copy(
        update={"admin_auth": AdminAuth.TOKEN, "admin_token": SecretStr(ADMIN_TOKEN)}
    )
    c.admin_verifier = build_admin_verifier(c.settings)


async def _anon(client: AsyncClient) -> tuple[dict[str, str], dict]:
    resp = await client.post("/auth/anonymous")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def _chat(client: AsyncClient, headers: dict, message: str = "ETF가 뭐야?", **body) -> dict:
    resp = await client.post("/chat", json={"message": message, **body}, headers=headers)
    assert resp.status_code == 200, resp.text
    return parse_sse(resp.text)[-1][1]  # done


async def _user_message_level(conversation_id: str) -> str:
    async with get_sessionmaker()() as session:
        msg = await session.scalar(
            select(Message)
            .where(Message.conversation_id == uuid.UUID(conversation_id), Message.role == "user")
            .order_by(Message.created_at.desc())
        )
    assert msg is not None
    return msg.meta["level"]


# ---------- 익명 발급 ----------


async def test_anonymous_is_off_by_default(client: AsyncClient) -> None:
    """기본값(ANON_ACCESS_ENABLED=false)에서는 지금 로컬 동작 그대로: 익명 발급은 없고 dev-login은 된다."""
    assert (await client.post("/auth/anonymous")).status_code == 404
    assert (await client.post("/auth/dev-login", json={"email": "u@local.test"})).status_code == 200


async def test_anonymous_issues_random_user_without_pii(client: AsyncClient, app: FastAPI) -> None:
    _enable_anon(app)
    headers, body = await _anon(client)
    user = body["user"]
    assert user["role"] == "anon" and user["level"] is None
    assert (
        user["email"] == f"anon-{user['id']}@anonymous.invalid"
    )  # 무작위 UUID에서만 만든 자리표시

    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["id"] == user["id"]

    async with get_sessionmaker()() as session:
        row = await session.get(User, uuid.UUID(user["id"]))
    assert row is not None and row.role == "anon"

    _, other = await _anon(client)
    assert other["user"]["id"] != user["id"]  # 부를 때마다 새 사용자(브라우저마다 다름)


async def test_anonymous_token_lasts_30_days(client: AsyncClient, app: FastAPI) -> None:
    _enable_anon(app)
    _, body = await _anon(client)
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    exp = datetime.fromtimestamp(claims["exp"], UTC)
    assert timedelta(days=29, hours=23) < exp - datetime.now(UTC) <= timedelta(days=30)
    assert claims["role"] == "anon"


async def test_anonymous_cannot_be_admin_by_email_list(client: AsyncClient, app: FastAPI) -> None:
    """ADMIN_EMAILS는 dev-login에만 쓰인다. 익명 사용자는 항상 role=anon."""
    c = app.state.container
    c.settings = c.settings.model_copy(
        update={"anon_access_enabled": True, "admin_emails": ["anon-x@anonymous.invalid"]}
    )
    _, body = await _anon(client)
    assert body["user"]["role"] == "anon"


async def test_dev_login_stays_closed_outside_local(client: AsyncClient, app: FastAPI) -> None:
    """공개 배포(APP_ENV=prod)에서는 익명 발급만 열리고 dev-login은 계속 404."""
    c = app.state.container
    c.settings = c.settings.model_copy(update={"app_env": AppEnv.PROD, "anon_access_enabled": True})
    assert (await client.post("/auth/dev-login", json={"email": "u@x.test"})).status_code == 404
    assert (await client.post("/auth/anonymous")).status_code == 200


async def test_anonymous_requires_local_auth_provider(client: AsyncClient, app: FastAPI) -> None:
    c = app.state.container
    c.settings = c.settings.model_copy(
        update={"anon_access_enabled": True, "auth_provider": AuthProvider.SUPABASE}
    )
    assert (await client.post("/auth/anonymous")).status_code == 404


# ---------- 대화 분리 ----------


async def test_anonymous_users_do_not_see_each_other(client: AsyncClient, app: FastAPI) -> None:
    _enable_anon(app)
    a, _ = await _anon(client)
    b, _ = await _anon(client)
    a_done = await _chat(client, a, "괴리율이 뭐야?")
    b_done = await _chat(client, b, "환헤지가 뭐야?")
    a_conv, b_conv = a_done["conversation_id"], b_done["conversation_id"]

    a_list = {x["id"] for x in (await client.get("/history", headers=a)).json()}
    b_list = {x["id"] for x in (await client.get("/history", headers=b)).json()}
    assert a_list == {a_conv} and b_list == {b_conv}

    # 남의 대화는 열 수도, 지울 수도 없다
    assert (await client.get(f"/history/{b_conv}", headers=a)).status_code == 404
    assert (await client.delete(f"/history/{b_conv}", headers=a)).status_code == 404
    assert (await client.get(f"/history/{b_conv}", headers=b)).status_code == 200

    # 남의 대화 id로 질문하면 그 대화에 이어지지 않고 새 대화가 생긴다
    hijack = await _chat(client, a, "이어서 물어볼게", conversation_id=b_conv)
    assert hijack["conversation_id"] not in (b_conv, a_conv)
    b_msgs = (await client.get(f"/history/{b_conv}", headers=b)).json()["messages"]
    assert all("이어서 물어볼게" not in m["content"] for m in b_msgs)

    # 남의 답변에는 피드백을 남길 수 없다
    fb = {"kind": "like", "message_id": b_done["message_id"]}
    assert (await client.post("/feedback", json=fb, headers=a)).status_code == 404
    assert (await client.post("/feedback", json=fb, headers=b)).status_code == 201


async def test_delete_all_only_removes_own_conversations(client: AsyncClient, app: FastAPI) -> None:
    _enable_anon(app)
    a, _ = await _anon(client)
    b, _ = await _anon(client)
    await _chat(client, a)
    b_conv = (await _chat(client, b))["conversation_id"]
    assert (await client.delete("/history", headers=a)).json()["deleted"] == 1
    assert [x["id"] for x in (await client.get("/history", headers=b)).json()] == [b_conv]


# ---------- 수준 ----------


async def test_anonymous_level_defaults_to_beginner(client: AsyncClient, app: FastAPI) -> None:
    _enable_anon(app)
    a, _ = await _anon(client)
    conv = (await _chat(client, a))["conversation_id"]
    assert await _user_message_level(conv) == "beginner"


async def test_anonymous_level_from_request(client: AsyncClient, app: FastAPI) -> None:
    _enable_anon(app)
    a, _ = await _anon(client)
    for level in ("intermediate", "expert", "beginner"):
        conv = (await _chat(client, a, level=level))["conversation_id"]
        assert await _user_message_level(conv) == level
    bad = await client.post("/chat", json={"message": "ETF가 뭐야?", "level": "guru"}, headers=a)
    assert bad.status_code == 422


# ---------- 운영 보호 ----------


async def test_local_admin_mode_rejects_anonymous(client: AsyncClient, app: FastAPI) -> None:
    """ADMIN_AUTH=local(기본): 익명 토큰은 403, 토큰 없음은 401, dev-login 운영자는 그대로 200."""
    _enable_anon(app)
    anon, _ = await _anon(client)
    admin = await login(client, "admin@local.test")
    for path in ADMIN_PATHS:
        assert (await client.get(path, headers=anon)).status_code == 403, path
        assert (await client.get(path)).status_code == 401, path
        assert (await client.get(path, headers=admin)).status_code == 200, path


async def test_token_admin_mode(client: AsyncClient, app: FastAPI) -> None:
    _enable_anon(app)
    _token_admin_mode(app)
    anon, _ = await _anon(client)
    good = {"X-Admin-Token": ADMIN_TOKEN}
    for path in ADMIN_PATHS:
        assert (await client.get(path)).status_code == 401, path
        assert (await client.get(path, headers=anon)).status_code == 401, path
        assert (await client.get(path, headers={"X-Admin-Token": "nope"})).status_code == 401, path
        assert (await client.get(path, headers={"X-Admin-Token": ""})).status_code == 401, path
        assert (await client.get(path, headers=good)).status_code == 200, path
        # 익명 토큰과 운영 토큰을 함께 보내도 된다(웹이 그렇게 보낸다)
        assert (await client.get(path, headers={**anon, **good})).status_code == 200, path


async def test_token_admin_mode_ignores_admin_role_jwt(client: AsyncClient, app: FastAPI) -> None:
    """token 방식에서는 role=admin JWT만으로는 통과하지 못한다(운영 토큰이 있어야 함)."""
    admin = await login(client, "admin@local.test")
    _token_admin_mode(app)
    assert (await client.get("/admin/traces", headers=admin)).status_code == 401


async def test_token_admin_upload_and_search(client: AsyncClient, app: FastAPI) -> None:
    _token_admin_mode(app)
    good = {"X-Admin-Token": ADMIN_TOKEN}
    files = {"file": ("anon-admin.md", b"# [SAMPLE] anon\n\n## a\n\nbody", "text/markdown")}
    up = await client.post("/admin/documents", files=files, headers=good)
    assert up.status_code == 201, up.text
    denied = await client.post("/admin/documents", files=files)
    assert denied.status_code == 401


async def test_cors_allows_admin_token_header(client: AsyncClient) -> None:
    resp = await client.options(
        "/admin/traces",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-admin-token",
        },
    )
    assert resp.status_code == 200
    assert "x-admin-token" in resp.headers["access-control-allow-headers"].lower()


# ---------- 설정 ----------

DB_URL = "postgresql+asyncpg://u:p@localhost:5432/db"


def test_anon_defaults(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DATABASE_URL", DB_URL)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.anon_access_enabled is False
    assert s.anon_jwt_ttl_minutes == 60 * 24 * 30
    assert s.admin_auth is AdminAuth.LOCAL and s.admin_token is None


def test_token_admin_requires_admin_token(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DATABASE_URL", DB_URL)
    clean_env.setenv("ADMIN_AUTH", "token")
    with pytest.raises(ValidationError, match="ADMIN_TOKEN"):
        Settings(_env_file=None)  # type: ignore[call-arg]
    clean_env.setenv("ADMIN_TOKEN", ADMIN_TOKEN)
    assert Settings(_env_file=None).admin_auth is AdminAuth.TOKEN  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "value",
    [
        " " * 40,  # 공백만
        "short-token",  # 짧음
        "a" * 31,  # 32자 미만
        "  " + "a" * 30 + "  ",  # 공백을 빼면 30자
    ],
)
def test_admin_token_must_be_long_enough(clean_env: pytest.MonkeyPatch, value: str) -> None:
    clean_env.setenv("DATABASE_URL", DB_URL)
    clean_env.setenv("ADMIN_AUTH", "token")
    clean_env.setenv("ADMIN_TOKEN", value)
    with pytest.raises(ValidationError, match="ADMIN_TOKEN"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_admin_token_32_chars_ok_and_compared_without_surrounding_spaces(
    clean_env: pytest.MonkeyPatch,
) -> None:
    import asyncio

    clean_env.setenv("DATABASE_URL", DB_URL)
    clean_env.setenv("ADMIN_AUTH", "token")
    clean_env.setenv("ADMIN_TOKEN", " " + "b" * 32 + " ")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    verifier = build_admin_verifier(s)
    assert asyncio.run(verifier.verify(None, {"x-admin-token": "b" * 32}))
    assert not asyncio.run(verifier.verify(None, {"x-admin-token": "b" * 31}))


def test_anon_requires_local_auth_provider_setting(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DATABASE_URL", DB_URL)
    clean_env.setenv("ANON_ACCESS_ENABLED", "true")
    clean_env.setenv("AUTH_PROVIDER", "supabase")
    with pytest.raises(ValidationError, match="ANON_ACCESS_ENABLED"):
        Settings(_env_file=None)  # type: ignore[call-arg]
