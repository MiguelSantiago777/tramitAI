import pytest

from apps.core.br import is_valid_cnpj, is_valid_cpf, normalize_br_phone, normalize_document


@pytest.mark.parametrize("value", ["529.982.247-25", "52998224725"])
def test_valid_cpf(value):
    assert is_valid_cpf(value)


@pytest.mark.parametrize("value", ["529.982.247-24", "111.111.111-11", "1234", ""])
def test_invalid_cpf(value):
    assert not is_valid_cpf(value)


@pytest.mark.parametrize(
    "value",
    [
        "11.222.333/0001-81",
        "11222333000181",
        "12.ABC.345/01DE-35",  # exemplo oficial do CNPJ alfanumérico (Receita Federal)
        "12abc34501de35",
    ],
)
def test_valid_cnpj(value):
    assert is_valid_cnpj(value)


@pytest.mark.parametrize(
    "value", ["11.222.333/0001-82", "00000000000000", "12.ABC.345/01DE-36", "12ABC34501DEXX"]
)
def test_invalid_cnpj(value):
    assert not is_valid_cnpj(value)


def test_normalize_document_strips_punctuation_and_uppercases():
    assert normalize_document("12.abc.345/01de-35") == "12ABC34501DE35"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(21) 99876-5432", "+5521998765432"),
        ("+55 21 99876-5432", "+5521998765432"),
        ("5521998765432", "+5521998765432"),
        ("21 3456-7890", "+552134567890"),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_br_phone(raw) == expected


@pytest.mark.parametrize(
    "raw", ["99876-5432", "(21) 89876-5432", "(01) 99876-5432", "21 8876-5432"]
)
def test_invalid_phone(raw):
    assert normalize_br_phone(raw) is None
