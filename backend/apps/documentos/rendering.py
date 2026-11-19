"""Minuta em texto (formato simples da Lia) → Word (.docx) e PDF.

Formato do texto (ver prompt legal_draft):
- "# "  título centralizado em negrito
- "## " título de seção em negrito
- "> "  linha centralizada (endereçamento, local e data, assinatura)
- resto: parágrafo justificado com recuo na primeira linha

Marcadores entre colchetes que ficaram sem dado (ex.: [ENDEREÇO DO CLIENTE]) saem
destacados em amarelo no Word para o advogado achar e preencher.
"""

import io
import re
from dataclasses import dataclass
from typing import Literal

from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.shared import Cm, Pt
from fpdf import FPDF

BlockKind = Literal["title", "heading", "center", "paragraph"]
PLACEHOLDER = re.compile(r"\[[A-ZÀ-Ü0-9][A-ZÀ-Ü0-9/ .,'ºª()-]{1,80}\]")


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    text: str


def parse_body(body: str) -> list[Block]:
    """Quebra o texto em blocos. Cada linha com marcador vira um bloco; o resto, parágrafos."""
    blocks: list[Block] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(Block("paragraph", " ".join(paragraph)))
            paragraph.clear()

    for raw in body.replace("\r\n", "\n").split("\n"):
        line = _clean_markdown(raw.strip())
        if not line:
            flush()
            continue
        for prefix, kind in (("## ", "heading"), ("# ", "title"), ("> ", "center")):
            if line.startswith(prefix):
                flush()
                text = line[len(prefix) :].strip()
                if text:
                    blocks.append(Block(kind, text))  # type: ignore[arg-type]
                break
        else:
            paragraph.append(line)
    flush()
    return blocks


def _clean_markdown(line: str) -> str:
    # O modelo às vezes escapa do formato: tira o negrito de markdown. "__" não: é a linha de
    # assinatura ("______").
    return re.sub(r"\*\*(.+?)\*\*", r"\1", line).replace("###", "##")


def remaining_placeholders(blocks: list[Block]) -> list[str]:
    found: list[str] = []
    for block in blocks:
        for match in PLACEHOLDER.findall(block.text):
            if match not in found:
                found.append(match)
    return found


# ------------------------------------------------------------------------------------ Word


def to_docx(blocks: list[Block]) -> bytes:
    doc = DocxDocument()
    section = doc.sections[0]
    section.page_height, section.page_width = Cm(29.7), Cm(21)  # A4
    # Margens no padrão ABNT: 3 cm em cima e à esquerda, 2 cm embaixo e à direita.
    section.top_margin, section.left_margin = Cm(3), Cm(3)
    section.bottom_margin, section.right_margin = Cm(2), Cm(2)

    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(6)

    for block in blocks:
        p = doc.add_paragraph()
        if block.kind == "title":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(12)
        elif block.kind == "heading":
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.keep_with_next = True
        elif block.kind == "center":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        else:
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.first_line_indent = Cm(2.5)
        bold = block.kind in ("title", "heading")
        _add_runs(p, block.text, bold=bold)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _add_runs(paragraph: object, text: str, *, bold: bool) -> None:
    pos = 0
    for match in PLACEHOLDER.finditer(text):
        if match.start() > pos:
            paragraph.add_run(text[pos : match.start()]).bold = bold  # type: ignore[attr-defined]
        run = paragraph.add_run(match.group(0))  # type: ignore[attr-defined]
        run.bold = True
        run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        pos = match.end()
    if pos < len(text):
        paragraph.add_run(text[pos:]).bold = bold  # type: ignore[attr-defined]


# ------------------------------------------------------------------------------------- PDF

# Fontes padrão do PDF são latin-1: troca o que não cabe por equivalente.
# Aspas curvas, travessões e reticências, por código (U+201C, U+201D, U+2018...).
_LATIN1 = str.maketrans(
    {
        chr(0x201C): '"',
        chr(0x201D): '"',
        chr(0x2018): "'",
        chr(0x2019): "'",
        chr(0x2013): "-",
        chr(0x2014): "-",
        chr(0x2026): "...",
    }
)


def _latin1(text: str) -> str:
    return text.translate(_LATIN1).encode("latin-1", "replace").decode("latin-1")


def to_pdf(blocks: list[Block]) -> bytes:
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_margins(left=30, top=30, right=20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    line = 7.5  # ~1,5 de entrelinha em corpo 12
    width = pdf.w - pdf.l_margin - pdf.r_margin
    for block in blocks:
        text = _latin1(block.text)
        if block.kind == "title":
            pdf.set_font("Times", "B", 13)
            pdf.ln(2)
            pdf.multi_cell(width, line, text, align="C", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)
        elif block.kind == "heading":
            pdf.set_font("Times", "B", 12)
            pdf.ln(3)
            pdf.multi_cell(width, line, text, align="L", new_x="LMARGIN", new_y="NEXT")
        elif block.kind == "center":
            pdf.set_font("Times", "", 12)
            pdf.multi_cell(width, line, text, align="C", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Times", "", 12)
            # Sem recuo no PDF (o justificado esticaria espaços); o Word tem o recuo certo.
            pdf.multi_cell(width, line, text, align="J", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
    return bytes(pdf.output())
