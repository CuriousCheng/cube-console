"""对称加密：数据源密码、AI key 落盘前必须加密。"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import MASTER_KEY


def _fernet() -> Fernet:
    if not MASTER_KEY:
        raise RuntimeError("MASTER_KEY 未设置，无法加解密")
    key = base64.urlsafe_b64encode(hashlib.sha256(MASTER_KEY.encode()).digest())
    return Fernet(key)


def encrypt(plain: str | None) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str | None) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        # MASTER_KEY 换过或数据损坏
        return ""


def mask(plain: str | None) -> str:
    """返回给前端看的样子：只留最后两位。"""
    if not plain:
        return ""
    return "•" * max(0, len(plain) - 2) + plain[-2:]
