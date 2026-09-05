"""
Hashing de mot de passe (bcrypt direct, pas passlib) + émission/vérification de JWT.

Note : on utilise le paquet `bcrypt` directement plutôt que `passlib` — passlib
1.7.4 (dernière version publiée) est incompatible avec bcrypt >= 4.1 (le
test interne de détection de bug de passlib plante avec
"password cannot be longer than 72 bytes"). Appeler bcrypt directement évite
ce problème et évite une dépendance non maintenue.
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import jwt, JWTError

from app.config import settings

# bcrypt tronque au-delà de 72 octets ; on borne explicitement en amont pour
# avoir un comportement prévisible plutôt qu'une troncature silencieuse.
_MAX_PASSWORD_BYTES = 72

# Durée de validité d'un lien de réinitialisation de mot de passe.
RESET_TOKEN_EXPIRE_MINUTES = 60


def hash_password(password: str) -> str:
    pw_bytes = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    pw_bytes = plain.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    try:
        return bcrypt.checkpw(pw_bytes, hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    expire = datetime.utcnow() + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None


def generate_reset_token() -> tuple[str, str, datetime]:
    """Génère un token de réinitialisation à usage unique.

    Retourne (token_brut, hash_du_token, date_d_expiration). Le token brut
    part dans le lien envoyé par e-mail et n'est JAMAIS stocké ; seul son
    hash SHA-256 est persisté en base, comparé bit à bit lors de
    /auth/reset-password — même principe qu'un mot de passe, mais un hash
    rapide (SHA-256) suffit ici : le token est déjà 256 bits d'aléa
    cryptographique, contrairement à un mot de passe choisi par un humain.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    return raw_token, token_hash, expires_at


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
