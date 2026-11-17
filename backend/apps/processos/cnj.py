"""Número único de processo do CNJ (Resolução CNJ 65/2008): NNNNNNN-DD.AAAA.J.TR.OOOO.

DD é calculado por módulo 97 (ISO 7064): o número completo, lido como inteiro com o DD
no final, deixa resto 1 na divisão por 97.
"""

from apps.core.br import only_digits

# Ordem dos códigos TR da Justiça Estadual (J=8) e Eleitoral (J=6): 01=AC ... 27=TO.
_UFS = [
    "ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms", "mg", "pa",
    "pb", "pr", "pe", "pi", "rj", "rn", "rs", "ro", "rr", "sc", "se", "sp", "to",
]  # fmt: skip
_STATE_MILITARY = {"13": "tjmmg", "21": "tjmrs", "26": "tjmsp"}


def normalize_cnj(value: str) -> str:
    return only_digits(value)


def check_digits(number: str, year: str, segment: str, court: str, origin: str) -> str:
    base = int(f"{number}{year}{segment}{court}{origin}")
    return f"{98 - (base * 100) % 97:02d}"


def is_valid_cnj(value: str) -> bool:
    digits = normalize_cnj(value)
    if len(digits) != 20:
        return False
    return int(digits[:7] + digits[9:] + digits[7:9]) % 97 == 1


def format_cnj(digits: str) -> str:
    if len(digits) != 20:
        return digits
    return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:]}"


def tribunal_alias(digits: str) -> str | None:
    """Alias do tribunal no padrão DataJud ('tjrj', 'trt1', 'tre-rj'). None se desconhecido."""
    if len(digits) != 20:
        return None
    segment, court = digits[13], digits[14:16]
    index = int(court) - 1
    match segment:
        case "3":
            return "stj"
        case "4" if 1 <= int(court) <= 6:
            return f"trf{int(court)}"
        case "5" if 1 <= int(court) <= 24:
            return f"trt{int(court)}"
        case "6" if 0 <= index < len(_UFS):
            return f"tre-{_UFS[index]}"
        case "7":
            return "stm"
        case "8" if 0 <= index < len(_UFS):
            return "tjdft" if _UFS[index] == "df" else f"tj{_UFS[index]}"
        case "9":
            return _STATE_MILITARY.get(court)
    return None
