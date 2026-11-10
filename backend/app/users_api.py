"""用户管理：admin 建号、重置密码、改角色、删号。

规则：
  · 不能删自己
  · 不能把最后一个 admin 降级或删掉
  · 管理员重置密码不需要旧密码；本人改密码需要旧密码
"""

from __future__ import annotations

import time

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from . import auth, store


class UserIn(BaseModel):
    name: str
    password: str
    role: str = "viewer"


class PasswordIn(BaseModel):
    password: str


class RoleIn(BaseModel):
    role: str


class SelfPasswordIn(BaseModel):
    old_password: str
    new_password: str


def _public(u: dict) -> dict:
    return {
        "id": u["id"],
        "name": u["name"],
        "role": u["role"],
        "created_at": u.get("created_at"),
    }


def register(app, current_user, require) -> None:
    @app.get("/api/users")
    async def list_users(user: dict = Depends(require("admin"))) -> dict:
        return {"items": [_public(u) for u in auth.load_users()]}

    @app.post("/api/users")
    async def create_user(body: UserIn, user: dict = Depends(require("admin"))) -> dict:
        if body.role not in auth.ROLES:
            raise HTTPException(400, f"角色只能是 {auth.ROLES}")
        if not body.name.strip() or len(body.password) < 4:
            raise HTTPException(400, "用户名不能为空，密码至少 4 位")

        users = auth.load_users()
        if any(u["name"] == body.name for u in users):
            raise HTTPException(400, "用户名已存在")

        item = {
            "id": store.next_id("u", users),
            "name": body.name.strip(),
            "role": body.role,
            "password_hash": auth.hash_password(body.password),
            "created_at": int(time.time()),
        }
        users.append(item)
        await auth.save_users(users)
        return {"ok": True, "item": _public(item)}

    @app.put("/api/users/{user_id}/password")
    async def reset_password(
        user_id: str, body: PasswordIn, user: dict = Depends(require("admin"))
    ) -> dict:
        if len(body.password) < 4:
            raise HTTPException(400, "密码至少 4 位")
        users = auth.load_users()
        target = next((u for u in users if u["id"] == user_id), None)
        if not target:
            raise HTTPException(404, "用户不存在")
        target["password_hash"] = auth.hash_password(body.password)
        await auth.save_users(users)
        return {"ok": True}

    @app.put("/api/users/{user_id}/role")
    async def change_role(user_id: str, body: RoleIn, user: dict = Depends(require("admin"))) -> dict:
        if body.role not in auth.ROLES:
            raise HTTPException(400, f"角色只能是 {auth.ROLES}")

        users = auth.load_users()
        target = next((u for u in users if u["id"] == user_id), None)
        if not target:
            raise HTTPException(404, "用户不存在")

        admins = [u for u in users if u["role"] == "admin"]
        if target["role"] == "admin" and body.role != "admin" and len(admins) <= 1:
            raise HTTPException(400, "至少保留一个管理员")

        target["role"] = body.role
        await auth.save_users(users)
        return {"ok": True}

    @app.delete("/api/users/{user_id}")
    async def delete_user(user_id: str, user: dict = Depends(require("admin"))) -> dict:
        users = auth.load_users()
        target = next((u for u in users if u["id"] == user_id), None)
        if not target:
            raise HTTPException(404, "用户不存在")
        if target["id"] == user["id"]:
            raise HTTPException(400, "不能删除自己")

        admins = [u for u in users if u["role"] == "admin"]
        if target["role"] == "admin" and len(admins) <= 1:
            raise HTTPException(400, "至少保留一个管理员")

        await auth.save_users([u for u in users if u["id"] != user_id])
        return {"ok": True}

    @app.put("/api/me/password")
    async def change_own_password(
        body: SelfPasswordIn, user: dict = Depends(current_user)
    ) -> dict:
        if not auth.verify_password(body.old_password, user["password_hash"]):
            raise HTTPException(400, "旧密码不对")
        if len(body.new_password) < 4:
            raise HTTPException(400, "新密码至少 4 位")

        users = auth.load_users()
        target = next((u for u in users if u["id"] == user["id"]), None)
        target["password_hash"] = auth.hash_password(body.new_password)
        await auth.save_users(users)
        return {"ok": True}
