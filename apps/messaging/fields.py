import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _get_fernet() -> Fernet:
    key = getattr(settings, "MESSAGING_ENCRYPTION_KEY", None) or settings.SECRET_KEY
    raw = key.encode() if isinstance(key, str) else key
    digest = hashlib.sha256(raw).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class EncryptedTextField(models.TextField):
    """Fernet (AES-128-CBC + HMAC-SHA256) transparent encryption for TextField.

    Ciphertext is stored as a URL-safe base64 string in the DB column.
    """

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except (InvalidToken, Exception):
            return value

    def to_python(self, value):
        return value

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        raw = value.encode() if isinstance(value, str) else value
        return _get_fernet().encrypt(raw).decode()
