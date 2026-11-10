"""账号体系：pbkdf2 密码哈希 + HMAC 签名 token。

3-4 人用，不引入 JWT 库，一个 HMAC 够。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from . import store
from .config import ADMIN_PASSWORD, ADMIN_USER, MASTER_KEY

ITERATIONS = 200_000
TOKEN_DAYS = 7

ROLES = ("admin", "editor", "viewer")
_RANK = {"viewer": 0, "editor": 1, "admin": 2}


# ── 密码 ────────────────────────────────────────────────


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _scheme, iters, salt, expected = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(dk.hex(), expected)
    except (ValueError, AttributeError):
        return False


# ── token ───────────────────────────────────────────────


def _sign(body: str) -> str:
    return hmac.new(MASTER_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()[:40]


def make_token(user_id: str, role: str) -> str:
    payload = {"u": user_id, "r": role, "exp": int(time.time()) + TOKEN_DAYS * 86400}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return f"{body}.{_sign(body)}"


def parse_token(token: str) -> dict[str, Any] | None:
    try:
        body, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < time.time():
        return None
    return payload


# ── 用户 ────────────────────────────────────────────────


def load_users() -> list[dict]:
    return store.read("users", {"users": []}).get("users", [])


async def save_users(users: list[dict]) -> None:
    await store.write("users", {"users": users})


def find_user(user_id: str) -> dict | None:
    return next((u for u in load_users() if u.get("id") == user_id), None)


def find_by_name(name: str) -> dict | None:
    return next((u for u in load_users() if u.get("name") == name), None)


def can(role: str, need: str) -> bool:
    return _RANK.get(role, -1) >= _RANK.get(need, 99)


async def bootstrap() -> None:
    """首次启动：users.json 不存在就建管理员。"""
    if store.path_of("users").exists():
        return
    if not ADMIN_PASSWORD:
        raise RuntimeError("首次启动需要设置 ADMIN_PASSWORD")
    await save_users(
        [
            {
                "id": "u1",
                "name": ADMIN_USER,
                "role": "admin",
                "password_hash": hash_password(ADMIN_PASSWORD),
                "created_at": int(time.time()),
            }
        ]
    )
