import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt


class Pbkdf2PasswordHasher:
    iterations = 600_000

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, self.iterations)
        return f"pbkdf2_sha256${self.iterations}${salt.hex()}${digest.hex()}"

    def verify(self, password: str, stored: str) -> bool:
        try:
            algorithm, rounds, salt_hex, digest_hex = stored.split("$")
            if algorithm != "pbkdf2_sha256":
                return False
            digest = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
            )
            return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
        except (ValueError, TypeError):
            return False


class JwtTokenCodec:
    def __init__(self, secret: str, lifetime_minutes: int = 60):
        if len(secret) < 32:
            raise ValueError("TOKEN_SECRET must be at least 32 characters")
        self.secret = secret
        self.lifetime_minutes = lifetime_minutes

    def issue(self, user_id: int) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=self.lifetime_minutes)},
            self.secret,
            algorithm="HS256",
        )

    def read_user_id(self, token: str) -> int | None:
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                options={"require": ["sub", "exp", "iat"]},
            )
            user_id = int(payload["sub"])
            return user_id if user_id > 0 else None
        except (jwt.PyJWTError, ValueError, TypeError):
            return None
