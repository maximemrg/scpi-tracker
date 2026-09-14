"""Extraction PDF via pdfplumber : texte + tableaux + mots positionnés.

Si un PDF ne rend aucun texte (probablement scanné), on NE tente PAS d'OCR :
on le signale pour que l'adaptateur marque les métriques A_VERIFIER.

Les `words` (mot + coordonnées x0/x1/top + page) servent aux extractions
positionnelles : dans les plaquettes en colonnes, un « gros chiffre » est
au-dessus de son libellé — on les associe par recouvrement horizontal.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import TypedDict

import pdfplumber


class Word(TypedDict):
    text: str
    x0: float
    x1: float
    top: float
    page: int


@dataclass
class PdfContent:
    text: str
    tables: list[list[list[str | None]]] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)

    @property
    def is_probably_scanned(self) -> bool:
        # Peu ou pas de texte extractible => probablement une image scannée.
        return len(self.text.strip()) < 40

    def table_cells(self) -> list[str]:
        """Cellules non vides, aplaties (les cellules Corum sont auto-portantes)."""
        out: list[str] = []
        for tbl in self.tables:
            for row in tbl:
                for cell in row:
                    if cell and cell.strip():
                        out.append(" ".join(cell.split()))
        return out


def extract_pdf(data: bytes) -> PdfContent:
    text_parts: list[str] = []
    tables: list[list[list[str | None]]] = []
    words: list[Word] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pi, page in enumerate(pdf.pages):
            text_parts.append(page.extract_text() or "")
            tables.extend(page.extract_tables())
            for w in page.extract_words():
                words.append(
                    Word(text=w["text"], x0=w["x0"], x1=w["x1"], top=w["top"], page=pi)
                )
    return PdfContent(text="\n".join(text_parts), tables=tables, words=words)
