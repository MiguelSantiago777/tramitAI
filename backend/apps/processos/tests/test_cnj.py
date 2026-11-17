import pytest

from apps.processos.cnj import format_cnj, is_valid_cnj, tribunal_alias

from .factories import make_cnj


def test_generated_number_satisfies_mod97():
    digits = make_cnj()
    # Regra da Res. CNJ 65/2008: N+A+J+TR+O+DD módulo 97 == 1.
    assert int(digits[:7] + digits[9:] + digits[7:9]) % 97 == 1
    assert is_valid_cnj(digits)


def test_accepts_formatted_number():
    assert is_valid_cnj(format_cnj(make_cnj()))


def test_rejects_wrong_check_digits():
    digits = make_cnj()
    wrong = digits[:7] + f"{(int(digits[7:9]) + 1) % 100:02d}" + digits[9:]
    assert not is_valid_cnj(wrong)


@pytest.mark.parametrize("value", ["", "123", "0801234-39.2024.8.19.000"])
def test_rejects_wrong_length(value):
    assert not is_valid_cnj(value)


def test_format():
    assert format_cnj("08012343920248190001") == "0801234-39.2024.8.19.0001"


@pytest.mark.parametrize(
    ("segment", "court", "alias"),
    [
        ("8", "19", "tjrj"),
        ("8", "26", "tjsp"),
        ("8", "07", "tjdft"),
        ("5", "01", "trt1"),
        ("4", "02", "trf2"),
        ("6", "19", "tre-rj"),
        ("3", "00", "stj"),
        ("9", "13", "tjmmg"),
        ("1", "00", None),
    ],
)
def test_tribunal_alias(segment, court, alias):
    assert tribunal_alias(make_cnj(segment=segment, court=court)) == alias
