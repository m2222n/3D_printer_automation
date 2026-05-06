"""
사용자 로그인 인증 모듈 (JWT)
=============================
- 사용자명 + bcrypt 해시로 로그인 검증
- JWT 발급/검증
- Sliding refresh: 사용 시마다 만료 갱신, 단 절대 최대 기간 초과 시 재로그인

기존 auth.py(Formlabs OAuth)와 다름. 헷갈리지 않도록 user_auth.py로 분리.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
from jose import jwt, JWTError


# bcrypt 72바이트 제한. 비번을 UTF-8로 인코딩 후 잘라 처리.
_BCRYPT_MAX_BYTES = 72


def _encode_password(plain: str) -> bytes:
    """비번을 bcrypt 입력용 bytes로 정규화 (72바이트 제한 적용)."""
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    """평문 비번을 bcrypt 해시로 변환 (.env에 저장할 값 생성용)"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(_encode_password(plain), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """평문 비번이 해시와 일치하는지 검증"""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(_encode_password(plain), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(
    username: str,
    secret: str,
    algorithm: str,
    expire_days: int,
    issued_at: Optional[datetime] = None,
) -> str:
    """
    JWT 발급.
    - sub: 사용자명
    - iat: 최초 발급 시각 (절대 최대 기간 검증용, 갱신해도 유지)
    - exp: 만료 시각 (sliding refresh 시 갱신됨)
    """
    now = issued_at or datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=expire_days)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str, secret: str, algorithm: str) -> Optional[dict]:
    """JWT 검증 + 디코드. 실패(서명/만료) 시 None."""
    if not token:
        return None
    try:
        return jwt.decode(token, secret, algorithms=[algorithm])
    except JWTError:
        return None


def should_refresh_token(payload: dict, expire_days: int) -> bool:
    """
    Sliding refresh 판단:
    토큰 사용 시점이 만료까지 절반 미만 남았으면 새 토큰 발급.
    예) 7일 만료 → 3.5일 미만 남으면 갱신.
    """
    exp = payload.get("exp")
    if not exp:
        return False
    now = datetime.now(timezone.utc).timestamp()
    remaining = exp - now
    half_lifetime = (expire_days * 86400) / 2
    return remaining < half_lifetime


def is_within_absolute_max(payload: dict, absolute_max_days: int) -> bool:
    """
    절대 최대 기간 내인지 확인.
    iat (최초 발급 시각) 기준으로 absolute_max_days 초과하면 False → 강제 재로그인.
    """
    iat = payload.get("iat")
    if not iat:
        return False
    age_seconds = datetime.now(timezone.utc).timestamp() - iat
    return age_seconds < (absolute_max_days * 86400)
