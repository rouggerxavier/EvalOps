import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


def _runtime_env() -> str:
    return (
        os.getenv("APP_ENV")
        or os.getenv("ENV")
        or os.getenv("PYTHON_ENV")
        or os.getenv("NODE_ENV")
        or "development"
    ).strip().lower()


def _is_dev_like(env: str) -> bool:
    return env in {"dev", "development", "test", "testing", "local"}


_env = _runtime_env()
_jwt_secret_from_env = os.getenv("JWT_SECRET")
if not _jwt_secret_from_env and not _is_dev_like(_env):
    raise RuntimeError("JWT_SECRET is required when running outside development/test environments.")

JWT_SECRET = _jwt_secret_from_env or secrets.token_urlsafe(48)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 15
JWT_SESSION_EXPIRE_MINUTES = int(os.getenv("JWT_SESSION_EXPIRE_MINUTES", "43200"))  # 30 days

_hasher = PasswordHasher(memory_cost=19456, time_cost=2, parallelism=1)
_password_hasher = PasswordHasher(memory_cost=19456, time_cost=2, parallelism=1)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def create_access_token(*, sub: str, email: str, name: str, expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    minutes = expires_minutes if expires_minutes is not None else JWT_EXPIRE_MINUTES
    payload = {
        "sub": sub,
        "email": email,
        "name": name,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_session_token(*, sub: str, email: str, name: str) -> str:
    return create_access_token(sub=sub, email=email, name=name, expires_minutes=JWT_SESSION_EXPIRE_MINUTES)


def hash_password(plain: str) -> str:
    return _password_hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _password_hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001
        return False


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def generate_api_key(environment: str) -> tuple[str, str]:
    raw = secrets.token_urlsafe(30).replace("-", "a").replace("_", "b")
    full = f"evk_{environment}_{raw}"
    prefix = full[:14]
    return full, prefix


def hash_api_key(raw_key: str) -> str:
    return _hasher.hash(raw_key)


def verify_api_key(raw_key: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, raw_key)
    except VerifyMismatchError:
        return False
