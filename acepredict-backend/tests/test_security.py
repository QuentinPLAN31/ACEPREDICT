"""
Non-regression : passlib 1.7.4 est incompatible avec bcrypt >= 4.1
("password cannot be longer than 72 bytes" leve par le propre self-test de
passlib, meme sur un mot de passe court). app/security.py appelle bcrypt
directement pour l'eviter -- ce test garantit que ca reste vrai si quelqu'un
reintroduit passlib plus tard.
"""
from app.security import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    hashed = hash_password("password123")
    assert hashed != "password123"
    assert verify_password("password123", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_long_password_does_not_crash():
    # bcrypt limite a 72 octets ; on doit tronquer proprement, pas planter.
    long_pw = "a" * 200
    hashed = hash_password(long_pw)
    assert verify_password(long_pw, hashed) is True
