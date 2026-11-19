from functools import cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import CaseSnapshot, Movement, ProcessSource, SourceError
from .djen import PublicationSource
from .fake import FakeProcessSource

__all__ = [
    "CaseSnapshot",
    "FakeProcessSource",
    "Movement",
    "ProcessSource",
    "SourceError",
    "get_process_source",
    "get_publication_source",
]


@cache
def _build(name: str) -> ProcessSource:
    if name == "fake":
        return FakeProcessSource()
    if name == "datajud":
        from .datajud import DataJudSource

        return DataJudSource()
    raise ImproperlyConfigured(f"PROCESS_SOURCE desconhecido: {name}")


def get_process_source() -> ProcessSource:
    return _build(settings.PROCESS_SOURCE)


@cache
def _build_publications(name: str) -> PublicationSource:
    from .djen import DjenSource, FakeDjenSource

    if name == "fake":
        return FakeDjenSource()
    if name == "djen":
        return DjenSource()
    raise ImproperlyConfigured(f"PUBLICATION_SOURCE desconhecido: {name}")


def get_publication_source() -> PublicationSource:
    """Fonte das publicações do Diário (DJEN), por OAB."""
    return _build_publications(settings.PUBLICATION_SOURCE)
