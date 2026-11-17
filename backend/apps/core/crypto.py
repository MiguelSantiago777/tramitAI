"""Cifragem de segredos guardados no banco (ex.: token da Meta por escritório).

MultiFernet: a primeira chave de FIELD_ENCRYPTION_KEYS cifra, todas decifram. Para rotacionar,
coloque a chave nova na frente e rode um re-encrypt (comando futuro) antes de remover a antiga.
Só segredos usam isso; conteúdo de mensagem fica protegido por disco/backup cifrados.
"""

from functools import cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class DecryptionError(RuntimeError):
    pass


@cache
def _fernet(keys: tuple[str, ...]) -> MultiFernet:
    if not keys:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS não configurado.")
    return MultiFernet([Fernet(k.encode()) for k in keys])


def _current() -> MultiFernet:
    return _fernet(tuple(settings.FIELD_ENCRYPTION_KEYS))


def encrypt_secret(plaintext: str) -> str:
    return _current().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _current().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError("Não foi possível decifrar o segredo (chave errada?).") from exc
