"""Extraction PDF via pdfplumber : texte + tableaux, détection de scan.

Si un PDF ne rend aucun texte (probablement scanné), on NE tente PAS d'OCR :
on le signale pour que l'adaptateur marque les métriques A_VERIFIER.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pdfplumber


@dataclass
class PdfContent:
    text: str
    tables: list[list[list[str | None]]] = field(default_factory=list)

    @property
    def is_probably_scanned(self) -> bool:
        # Peu ou pas de texte extractible => probablement une image scannée.
        return len(self.text.strip()) < 40


def extract_pdf(data: bytes) -> PdfContent:
    text_parts: list[str] = []
    tables: list[list[list[str | None]]] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
            for tbl in page.extract_tables():
                tables.append(tbl)
    return PdfContent(text="\n".join(text_parts), tables=tables)
