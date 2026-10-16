from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .utils import setup_logging

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    fitz = None

logger = setup_logging()


class CompositeDocumentError(Exception):
    """Raised when a composite document cannot be profiled."""


@dataclass
class PdfPageProfile:
    file: str
    page_number: int
    text_length: int
    image_count: int
    width: float | None = None
    height: float | None = None
    digital_text: bool = False
    image_heavy: bool = False
    blank_or_low_text: bool = False
    possible_scan: bool = False
    keyword_hits: dict[str, int] = field(default_factory=dict)
    text_sample: str = ""


@dataclass
class SegmentClassification:
    segment_type: str
    confidence: float
    reasons: list[str]
    recommended_engines: list[str]
    review_required: bool = False


@dataclass
class CompositeSegment:
    segment_id: str
    file: str
    pages: list[int]
    segment_type: str
    confidence: float
    reasons: list[str]
    recommended_engines: list[str]
    review_required: bool = False

    def to_provenance(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "file": self.file,
            "pages": self.pages,
            "segment_type": self.segment_type,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "recommended_engines": self.recommended_engines,
            "review_required": self.review_required,
        }


@dataclass
class CompositeDocumentProfile:
    file: str
    page_count: int
    homogeneous: bool
    segments: list[CompositeSegment]
    pages: list[PdfPageProfile]
    warnings: list[str] = field(default_factory=list)

    @property
    def review_required(self) -> bool:
        return any(segment.review_required for segment in self.segments)

    def provenance_segments(self) -> list[dict[str, Any]]:
        return [segment.to_provenance() for segment in self.segments]


KEYWORDS: dict[str, tuple[str, ...]] = {
    "email_printout": (
        "from:",
        "to:",
        "subject:",
        "sent:",
        "de:",
        "a:",
        "objet:",
        "envoye:",
        "envoyee:",
    ),
    "identity_document": (
        "carte nationale",
        "identite",
        "passeport",
        "passport",
        "cni",
        "date de naissance",
        "lieu de naissance",
        "nationalite",
        "prenom",
    ),
    "invoice_or_quote": (
        "facture",
        "devis",
        "total",
        "tva",
        "montant",
        "iban",
        "siret",
        "reste a payer",
    ),
    "typed_form": (
        "numero de contrat",
        "numero police",
        "date du sinistre",
        "declaration",
        "assure",
        "sinistre",
        "garantie",
        "souscripteur",
    ),
}


def is_pdf_file(filename: str) -> bool:
    return Path(filename.lower()).suffix == ".pdf"


def profile_pdf(file_bytes: bytes, filename: str) -> CompositeDocumentProfile:
    """Profile and segment a PDF without changing extraction engines."""
    if not is_pdf_file(filename):
        raise CompositeDocumentError(f"{filename} is not a PDF")
    if fitz is None:
        raise CompositeDocumentError("PyMuPDF is required to profile composite PDFs")

    try:
        document = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        raise CompositeDocumentError(f"Could not open PDF {filename}: {exc}") from exc

    try:
        pages = [_profile_page(filename, index + 1, page) for index, page in enumerate(document)]
    finally:
        document.close()

    classifications = [classify_page(page_profile) for page_profile in pages]
    segments = group_adjacent_pages(filename, pages, classifications)
    segment_types = {segment.segment_type for segment in segments}
    homogeneous = len(segment_types) <= 1

    logger.info(
        "Composite PDF profile for %s: pages=%d segments=%d homogeneous=%s types=%s",
        filename,
        len(pages),
        len(segments),
        homogeneous,
        ",".join(sorted(segment_types)),
    )

    return CompositeDocumentProfile(
        file=filename,
        page_count=len(pages),
        homogeneous=homogeneous,
        segments=segments,
        pages=pages,
    )


def classify_page(page: PdfPageProfile) -> SegmentClassification:
    """Classify one PDF page using deterministic, auditable signals."""
    hits = page.keyword_hits
    reasons: list[str] = []

    if hits.get("email_printout", 0) >= 2 and page.text_length >= 80:
        reasons.append("email headers detected in PDF text")
        return SegmentClassification(
            segment_type="email_printout",
            confidence=0.86,
            reasons=reasons,
            recommended_engines=["llm-markdown-structuring"],
        )

    if hits.get("identity_document", 0) >= 2:
        reasons.append("identity-document keywords detected")
        if page.image_count > 0:
            reasons.append("page contains embedded image(s)")
        return SegmentClassification(
            segment_type="identity_document",
            confidence=0.78 if page.image_count else 0.68,
            reasons=reasons,
            recommended_engines=[
                "mistral-document-ai-25.12",
                "content-understanding:prebuilt-layout",
            ],
            review_required=True,
        )

    if hits.get("invoice_or_quote", 0) >= 2:
        reasons.append("invoice or quote keywords detected")
        return SegmentClassification(
            segment_type="invoice_or_quote",
            confidence=0.82,
            reasons=reasons,
            recommended_engines=[
                "content-understanding:prebuilt-layout",
                "llm-markdown-structuring",
            ],
        )

    if page.image_heavy and page.text_length < 40:
        reasons.append("image-heavy page with almost no native text")
        return SegmentClassification(
            segment_type="claim_photo",
            confidence=0.62,
            reasons=reasons,
            recommended_engines=[
                "content-understanding:prebuilt-image",
                "gpt-vision-fallback",
            ],
            review_required=True,
        )

    if page.possible_scan:
        reasons.append("image-heavy page with weak native text")
        return SegmentClassification(
            segment_type="complex_scan",
            confidence=0.66,
            reasons=reasons,
            recommended_engines=[
                "mistral-document-ai-25.12",
                "content-understanding:prebuilt-layout",
            ],
            review_required=True,
        )

    if hits.get("typed_form", 0) >= 1 or page.text_length >= 700:
        reasons.append("dense native text or insurance form keywords")
        return SegmentClassification(
            segment_type="typed_form",
            confidence=0.8 if page.text_length >= 700 else 0.72,
            reasons=reasons,
            recommended_engines=[
                "content-understanding:prebuilt-layout",
                "llm-markdown-structuring",
            ],
        )

    reasons.append("no strong deterministic signal")
    return SegmentClassification(
        segment_type="unknown",
        confidence=0.35,
        reasons=reasons,
        recommended_engines=[
            "content-understanding:prebuilt-layout",
            "mistral-document-ai-25.12",
        ],
        review_required=True,
    )


def group_adjacent_pages(
    filename: str,
    page_profiles: list[PdfPageProfile],
    classifications: list[SegmentClassification],
) -> list[CompositeSegment]:
    """Group adjacent pages with the same class into stable segments."""
    segments: list[CompositeSegment] = []
    current_pages: list[int] = []
    current_classification: SegmentClassification | None = None

    for page, classification in zip(page_profiles, classifications):
        if (
            current_classification
            and classification.segment_type == current_classification.segment_type
        ):
            current_pages.append(page.page_number)
            current_classification = _merge_classifications(current_classification, classification)
            continue

        if current_classification and current_pages:
            segments.append(
                _segment_from_classification(
                    filename,
                    len(segments) + 1,
                    current_pages,
                    current_classification,
                )
            )

        current_pages = [page.page_number]
        current_classification = classification

    if current_classification and current_pages:
        segments.append(
            _segment_from_classification(
                filename,
                len(segments) + 1,
                current_pages,
                current_classification,
            )
        )

    return segments


def render_pdf_page_to_png(
    file_bytes: bytes,
    *,
    page_number: int,
    dpi: int = 144,
    max_pixels: int = 4_000_000,
) -> bytes:
    """Render one PDF page to PNG bytes for future image analyzers."""
    if fitz is None:
        raise CompositeDocumentError("PyMuPDF is required to render PDF pages")
    if page_number < 1:
        raise CompositeDocumentError("page_number must be 1-based")

    document = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        if page_number > len(document):
            raise CompositeDocumentError(
                f"page_number {page_number} exceeds PDF page count {len(document)}"
            )
        page = document[page_number - 1]
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        if pixmap.width * pixmap.height > max_pixels:
            scale = (max_pixels / (pixmap.width * pixmap.height)) ** 0.5
            matrix = fitz.Matrix(zoom * scale, zoom * scale)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return pixmap.tobytes("png")
    finally:
        document.close()


def _profile_page(filename: str, page_number: int, page: Any) -> PdfPageProfile:
    text = page.get_text("text") or ""
    normalized = _normalize_text(text)
    image_count = len(page.get_images(full=False))
    text_length = len(normalized)
    rect = page.rect
    keyword_hits = {
        category: _count_keyword_hits(normalized, values) for category, values in KEYWORDS.items()
    }
    digital_text = text_length >= 80
    image_heavy = image_count > 0 and text_length < 500
    blank_or_low_text = text_length < 80
    possible_scan = image_count > 0 and text_length < 180

    return PdfPageProfile(
        file=filename,
        page_number=page_number,
        text_length=text_length,
        image_count=image_count,
        width=float(rect.width) if rect else None,
        height=float(rect.height) if rect else None,
        digital_text=digital_text,
        image_heavy=image_heavy,
        blank_or_low_text=blank_or_low_text,
        possible_scan=possible_scan,
        keyword_hits=keyword_hits,
        text_sample=normalized[:500],
    )


def _segment_from_classification(
    filename: str,
    index: int,
    pages: list[int],
    classification: SegmentClassification,
) -> CompositeSegment:
    prefix = _safe_segment_prefix(filename)
    return CompositeSegment(
        segment_id=f"{prefix}-segment-{index}",
        file=filename,
        pages=pages,
        segment_type=classification.segment_type,
        confidence=round(classification.confidence, 2),
        reasons=classification.reasons,
        recommended_engines=classification.recommended_engines,
        review_required=classification.review_required,
    )


def _merge_classifications(
    left: SegmentClassification,
    right: SegmentClassification,
) -> SegmentClassification:
    reasons = list(dict.fromkeys(left.reasons + right.reasons))
    recommended_engines = list(dict.fromkeys(left.recommended_engines + right.recommended_engines))
    return SegmentClassification(
        segment_type=left.segment_type,
        confidence=min(left.confidence, right.confidence),
        reasons=reasons,
        recommended_engines=recommended_engines,
        review_required=left.review_required or right.review_required,
    )


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    return re.sub(r"\s+", " ", text).strip()


def _count_keyword_hits(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _safe_segment_prefix(filename: str) -> str:
    stem = Path(filename).stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return stem[:40] or "pdf"
