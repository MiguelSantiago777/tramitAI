import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from apps.processos.sources import SourceError
from apps.processos.sources.datajud import DataJudSource, parse_datetime, parse_hits

CNJ = "08012345620248190001"


def _doc(grau: str, updated: str, movimentos: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "numeroProcesso": CNJ,
        "grau": grau,
        "dataHoraUltimaAtualizacao": updated,
        "classe": {"codigo": 7, "nome": "Procedimento Comum Cível"},
        "assuntos": [{"codigo": 10433, "nome": "Indenização por Dano Moral"}],
        "orgaoJulgador": {"codigo": 1, "nome": "1ª Vara Cível de Nova Iguaçu"},
        "movimentos": movimentos,
        **extra,
    }


SAMPLE = [
    _doc(
        "G1",
        "2026-11-10T10:00:00.000Z",
        [
            {"codigo": 26, "nome": "Distribuição", "dataHora": "2024-03-04T13:00:00.000Z"},
            {
                "codigo": 581,
                "nome": "Juntada",
                "dataHora": "2026-11-09T15:30:00",
                "complementosTabelados": [
                    {"codigo": 4, "valor": 57, "nome": "Petição", "descricao": "tipo_de_documento"}
                ],
            },
            {"nome": "", "dataHora": "2026-11-09T15:30:00"},  # sem nome: ignorado
            {"codigo": 51, "nome": "Conclusão", "dataHora": "lixo"},  # data inválida: ignorado
        ],
    ),
    _doc(
        "G2",
        "2026-11-12T08:00:00.000Z",
        [{"codigo": 22, "nome": "Baixa Definitiva", "dataHora": "20261111093000"}],
        orgaoJulgador={"nome": "3ª Câmara Cível"},
    ),
    {"numeroProcesso": "99999999999999999999", "movimentos": []},  # outro processo
]


def test_parse_hits_merges_graus_and_normalizes():
    snapshot = parse_hits(CNJ, SAMPLE)
    assert snapshot is not None
    assert snapshot.classe == "Procedimento Comum Cível"
    assert snapshot.assuntos == ("Indenização por Dano Moral",)
    # Órgão do documento atualizado por último (G2).
    assert snapshot.orgao_julgador == "3ª Câmara Cível"
    assert snapshot.source_updated_at == datetime(2026, 11, 12, 8, tzinfo=UTC)
    assert [(m.name, m.grau) for m in snapshot.movements] == [
        ("Distribuição", "G1"),
        ("Juntada", "G1"),
        ("Baixa Definitiva", "G2"),
    ]
    juntada = snapshot.movements[1]
    assert juntada.code == 581
    assert juntada.complements == ("tipo de documento: Petição",)


def test_parse_hits_unknown_number_is_none():
    assert parse_hits(CNJ, []) is None
    assert parse_hits(CNJ, [{"numeroProcesso": "1"}]) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024-03-04T13:00:00.000Z", datetime(2024, 3, 4, 13, tzinfo=UTC)),
        # Sem fuso = horário de Brasília (UTC-3).
        ("2024-03-04T10:00:00", datetime(2024, 3, 4, 13, tzinfo=UTC)),
        ("20240304100000", datetime(2024, 3, 4, 13, tzinfo=UTC)),
        ("", None),
        (None, None),
        ("ontem", None),
    ],
)
def test_parse_datetime(raw, expected):
    assert parse_datetime(raw) == expected


def _source(handler: Any) -> DataJudSource:
    return DataJudSource(client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture
def datajud_settings(settings):
    settings.DATAJUD_API_KEY = "chave-publica-de-teste"
    settings.DATAJUD_URL = "https://datajud.test"
    return settings


def test_fetch_sends_api_key_and_query(datajud_settings):
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"hits": {"hits": [{"_source": d} for d in SAMPLE]}})

    snapshot = _source(handler).fetch(CNJ, "tjrj")
    assert snapshot is not None
    assert len(snapshot.movements) == 3
    assert seen["url"] == "https://datajud.test/api_publica_tjrj/_search"
    assert seen["auth"] == "APIKey chave-publica-de-teste"
    assert seen["body"]["query"] == {"match": {"numeroProcesso": CNJ}}


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (429, "http_429", True),
        (503, "http_503", True),
        (401, "http_401", False),
        (404, "unknown_tribunal", False),
    ],
)
def test_fetch_http_errors(datajud_settings, status, code, retryable):
    source = _source(lambda request: httpx.Response(status, json={}))
    with pytest.raises(SourceError) as exc:
        source.fetch(CNJ, "tjrj")
    assert exc.value.code == code
    assert exc.value.retryable is retryable


def test_fetch_network_error_is_retryable(datajud_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    with pytest.raises(SourceError) as exc:
        _source(handler).fetch(CNJ, "tjrj")
    assert exc.value.retryable is True


def test_fetch_without_key_is_not_configured(settings):
    settings.DATAJUD_API_KEY = ""
    with pytest.raises(SourceError) as exc:
        _source(lambda r: httpx.Response(200)).fetch(CNJ, "tjrj")
    assert exc.value.code == "not_configured"
    assert exc.value.retryable is False
