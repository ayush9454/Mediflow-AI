"""Authored page content shared by rendering and independent gold transcripts."""

from dataclasses import dataclass

from mediflow.benchmark.models import SourceDocument, SourceRow


@dataclass(frozen=True)
class PageContent:
    heading: str
    subtitle: str
    identity: str
    layout: str
    headers: tuple[str, ...]
    rows: tuple[SourceRow, ...]
    text_lines: tuple[str, ...]
    footer: str
    page_label: str

    def transcript(self) -> str:
        return "\n".join(
            (
                self.heading,
                self.subtitle,
                self.identity,
                self.layout,
                *self.headers,
                *(row.quotation() for row in self.rows),
                *self.text_lines,
                self.footer,
                self.page_label,
            )
        )


def compose_page(document: SourceDocument, number: int, page_count: int) -> PageContent:
    """All text is built from fixture definitions, without reading generated PDFs."""
    french = document.kind == "unsupported_language"
    rows = document.pages[number - 1] if document.pages else ()
    return PageContent(
        heading="LABORATOIRE FICTIF"
        if french
        else {
            "unsupported_category": "SYNTHETIC DOCUMENT",
        }.get(document.kind, "SYNTHETIC LABORATORY"),
        subtitle="Exercice fictif - aucune utilisation clinique"
        if french
        else "Teaching fixture - invented records - no clinical use",
        identity=f"Document: {document.document_id}   Patient: "
        f"{'FICTIF' if french else 'SYNTHETIC'}-{document.document_id}",
        layout=f"Page {number} / {page_count}"
        if french
        else f"Layout: {document.layout}   Source page {number} of {page_count}",
        headers=("Analyte", "Result", "Unit", "Printed interval", "Flag", "Collected")
        if rows
        else (),
        rows=rows,
        text_lines=document.text_lines,
        footer="Tous les noms et résultats sont fictifs."
        if french
        else "All names, identifiers and findings are invented for software evaluation.",
        page_label=f"{number} / {page_count}",
    )
