"""API Key 加密存储 — Fernet AES-128-CBC"""
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def _get_fernet() -> Fernet:
    secret = os.getenv("ENCRYPTION_KEY", os.getenv("JWT_SECRET", ""))
    if not secret:
        raise RuntimeError("ENCRYPTION_KEY 或 JWT_SECRET 未配置，无法加密 API Key")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"ai_agent_1_salt", iterations=480000)
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return Fernet(key)


def encrypt_value(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    if not ciphertext:
        return ciphertext
    return _get_fernet().decrypt(ciphertext.encode()).decode()
