from __future__ import annotations

import asyncio
from pathlib import Path

from api_server import _get_policy_pdfs, get_policy_pdf


def test_swiss_avb_is_served_when_available(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    relative = (
        Path("assets") / "pdf" / "prevaiq" / ("prevaiq-ch-avb-kmu-geschaeftsversicherung-2026.pdf")
    )
    relative.parent.mkdir(parents=True)
    relative.write_bytes(b"%PDF-1.7\n")

    catalog = _get_policy_pdfs("PrevaIQ")
    assert catalog["kmu_ch"]["filename"] == relative.relative_to(Path("assets") / "pdf").as_posix()
    response = asyncio.run(get_policy_pdf("kmu_ch"))
    assert Path(response.path) == relative
    assert response.media_type == "application/pdf"


def test_french_aliases_are_preserved_and_absent_swiss_pdf_is_not_offered(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = Path("assets") / "pdf" / "prevaiq"
    folder.mkdir(parents=True)
    for filename in (
        "prevaiq-conditions-generales-habitation.pdf",
        "prevaiq-complementaire-sante.pdf",
    ):
        (folder / filename).write_bytes(b"%PDF-1.7\n")

    catalog = _get_policy_pdfs("PrevaIQ")
    assert set(catalog) == {"habitation", "sante"}
