import hashlib
import hmac


def is_valid_signature(body: bytes, header: str | None, app_secret: str) -> bool:
    """Confere X-Hub-Signature-256 (HMAC-SHA256 do corpo bruto com o App Secret do app Meta)."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def sign(body: bytes, app_secret: str) -> str:
    """Gera o header como a Meta gera. Para testes e para o comando simulate_inbound."""
    return "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
