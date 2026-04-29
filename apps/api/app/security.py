import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 15

_hasher = PasswordHasher(memory_cost=19456, time_cost=2, parallelism=1)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def create_access_token(*, sub: str, email: str, name: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "email": email,
        "name": name,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


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
