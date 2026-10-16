from __future__ import annotations

import pytest

from app.composite_documents import (
    PdfPageProfile,
    classify_page,
    group_adjacent_pages,
    profile_pdf,
)

fitz = pytest.importorskip("fitz")


def _pdf_bytes(*page_texts: str) -> bytes:
    document = fitz.open()
    try:
        for text in page_texts:
            page = document.new_page()
            page.insert_text((72, 72), text, fontsize=11)
        return document.tobytes()
    finally:
        document.close()


def test_profile_pdf_marks_homogeneous_typed_forms():
    pdf = _pdf_bytes(
        "Declaration de sinistre\nNumero de contrat: GRP-123\nAssure: Marie Lefevre",
        "Date du sinistre: 05/06/2026\nGarantie: degat des eaux\nMontant: 1200 EUR",
    )

    profile = profile_pdf(pdf, "claim.pdf")

    assert profile.page_count == 2
    assert profile.homogeneous is True
    assert len(profile.segments) == 1
    assert profile.segments[0].segment_type == "typed_form"
    assert profile.segments[0].pages == [1, 2]


def test_profile_pdf_splits_printed_email_segment():
    pdf = _pdf_bytes(
        "Declaration de sinistre\nNumero de contrat: GRP-123\nAssure: Marie Lefevre",
        "From: client@example.com\nTo: gestionnaire@example.com\nSubject: Sinistre auto\nBonjour",
    )

    profile = profile_pdf(pdf, "mixed.pdf")

    assert profile.homogeneous is False
    assert [segment.segment_type for segment in profile.segments] == [
        "typed_form",
        "email_printout",
    ]
    assert profile.segments[1].recommended_engines == ["llm-markdown-structuring"]


def test_identity_page_requires_review():
    page = PdfPageProfile(
        file="id.pdf",
        page_number=1,
        text_length=120,
        image_count=1,
        image_heavy=True,
        keyword_hits={"identity_document": 3},
        text_sample="carte nationale identite date de naissance",
    )

    classification = classify_page(page)

    assert classification.segment_type == "identity_document"
    assert classification.review_required is True
    assert "mistral-document-ai-25.12" in classification.recommended_engines


def test_group_adjacent_pages_keeps_ordered_segments():
    pages = [
        PdfPageProfile(file="mixed.pdf", page_number=1, text_length=500, image_count=0),
        PdfPageProfile(file="mixed.pdf", page_number=2, text_length=500, image_count=0),
        PdfPageProfile(file="mixed.pdf", page_number=3, text_length=120, image_count=0),
    ]
    classifications = [
        classify_page(
            PdfPageProfile(
                file="mixed.pdf",
                page_number=1,
                text_length=500,
                image_count=0,
                keyword_hits={"typed_form": 2},
            )
        ),
        classify_page(
            PdfPageProfile(
                file="mixed.pdf",
                page_number=2,
                text_length=500,
                image_count=0,
                keyword_hits={"typed_form": 2},
            )
        ),
        classify_page(
            PdfPageProfile(
                file="mixed.pdf",
                page_number=3,
                text_length=120,
                image_count=0,
                keyword_hits={"email_printout": 3},
            )
        ),
    ]

    segments = group_adjacent_pages("mixed.pdf", pages, classifications)

    assert [segment.pages for segment in segments] == [[1, 2], [3]]
    assert [segment.segment_type for segment in segments] == ["typed_form", "email_printout"]
