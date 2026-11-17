"""Validação e normalização de dados brasileiros: CPF, CNPJ (inclusive alfanumérico) e telefone."""

import re

_NON_DIGITS = re.compile(r"\D")
_CNPJ_SEPARATORS = re.compile(r"[\s./-]")
_CNPJ_FORMAT = re.compile(r"^[A-Z0-9]{12}\d{2}$")
_CNPJ_WEIGHTS_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_CNPJ_WEIGHTS_2 = [6, *_CNPJ_WEIGHTS_1]


def only_digits(value: str) -> str:
    return _NON_DIGITS.sub("", value or "")


def normalize_document(value: str) -> str:
    """Remove pontuação e põe em maiúsculas (CNPJ alfanumérico usa letras)."""
    return _CNPJ_SEPARATORS.sub("", value or "").upper()


def is_valid_cpf(value: str) -> bool:
    digits = only_digits(value)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(digits[i]) * (size + 1 - i) for i in range(size))
        if (total * 10) % 11 % 10 != int(digits[size]):
            return False
    return True


def is_valid_cnpj(value: str) -> bool:
    """CNPJ numérico ou alfanumérico (IN RFB 2.229/2024): 12 posições A-Z/0-9 + 2 DVs numéricos.

    No cálculo do DV, cada caractere vale `ord(c) - 48` (dígitos continuam valendo 0-9).
    """
    doc = normalize_document(value)
    if not _CNPJ_FORMAT.match(doc) or doc == doc[0] * 14:
        return False
    values = [ord(c) - 48 for c in doc]
    for weights, position in ((_CNPJ_WEIGHTS_1, 12), (_CNPJ_WEIGHTS_2, 13)):
        remainder = sum(v * w for v, w in zip(values, weights, strict=False)) % 11
        check = 0 if remainder < 2 else 11 - remainder
        if check != values[position]:
            return False
    return True


def normalize_br_phone(value: str) -> str | None:
    """Telefone brasileiro em E.164 (+55DDNNNNNNNN[N]) ou None se inválido.

    Aceita com ou sem +55, com pontuação. Celular precisa ter 9 dígitos começando por 9.
    """
    digits = only_digits(value)
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) not in (10, 11):
        return None
    ddd, number = digits[:2], digits[2:]
    if ddd[0] == "0" or ddd[1] == "0":
        return None
    if len(number) == 9 and number[0] != "9":
        return None
    if len(number) == 8 and number[0] not in "2345":
        # 8 dígitos só é válido para fixo (começa com 2-5).
        return None
    return f"+55{digits}"
