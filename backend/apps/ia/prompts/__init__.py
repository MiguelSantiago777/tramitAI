"""Prompts versionados em arquivo: prompts/<nome>/<versão>.md.

A versão ativa de cada prompt fica em manifest.json. Toda geração registra nome e versão
(AiGeneration), então trocar a versão no manifesto é rastreável. Nunca edite uma versão já
usada em produção: crie v2.md e aponte o manifesto.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str


@cache
def _manifest() -> dict[str, str]:
    data = json.loads((PROMPTS_DIR / "manifest.json").read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data.items()}


@cache
def load_prompt(name: str, version: str | None = None) -> Prompt:
    version = version or _manifest()[name]
    path = PROMPTS_DIR / name / f"{version}.md"
    return Prompt(name=name, version=version, text=path.read_text(encoding="utf-8").strip())
