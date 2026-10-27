"""
CMS authentication: password hashing (bcrypt) + JWT tokens.

Using bcrypt directly, not passlib — passlib 1.7.4 has a known
incompatibility with bcrypt 4.x (AttributeError on `bcrypt.__about__`).
Direct bcrypt avoids that entirely.
"""
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db.database import AdminUser, get_admin_user

logger = logging.getLogger("auth")

_bearer_scheme = HTTPBearer()


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """Returns the username from a valid token. Raises jwt exceptions if invalid/expired."""
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    return payload["sub"]


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> AdminUser:
    """
    Require an active authenticated CMS account, regardless of its role.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        username = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise unauthorized

    admin = await get_admin_user(username)
    if admin is None or not admin.is_active:
        raise unauthorized
    return admin


async def get_current_admin(
    user: AdminUser = Depends(get_current_user),
) -> AdminUser:
    """Require a manual-team or bootstrap super-admin account."""
    if user.role not in {"manual_team", "super_admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manual-team access required",
        )
    return user
