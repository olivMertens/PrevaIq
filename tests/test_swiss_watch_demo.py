from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

import fitz
import pytest

from scripts import generate_swiss_watch_claim as claim
from scripts import generate_luxury_watch_concept as concept
from scripts.generate_swiss_storm_claim import _mail_attachment


def pdf_text(name: str) -> str:
    with fitz.open(claim.SCENARIO_DIR / name) as document:
        return " ".join(
            unicodedata.normalize("NFKC", " ".join(page.get_text() for page in document)).split()
        )


def test_watch_loss_totals_and_coverage_boundaries() -> None:
    assert claim.TOTAL == 14_968_600
    assert claim.DEDUCTIBLE == 50_000
    assert claim.NET == 14_918_600
    assert claim.SUM_INSURED_CONTENTS > claim.INSURABLE_VALUE
    for _, _, amount, _, lines in claim.DAMAGES:
        assert amount == sum(value for _, value in lines)
    assert claim.AVB_PATH.is_file()
    assert len(claim.PHOTOS) == 10
    assert len(claim.EMAIL_1_PHOTOS) == 6
    names = [photo.name for photo in claim.PHOTOS]
    assert len(set(names)) == len(names)
    for index, photo in enumerate(claim.PHOTOS):
        assert datetime.strptime(photo.taken, "%d.%m.%Y %H:%M") > datetime(2026, 8, 28, 10, 30)
        if photo.reference:
            assert photo.reference in names[:index]


def test_watch_manifest_has_complete_hash_verified_assets() -> None:
    manifest = json.loads((claim.SCENARIO_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["synthetic"] is True
    assert manifest["attention_points"] == []
    assert manifest["amounts_chf"]["total"] == claim.TOTAL
    assert manifest["amounts_chf"]["net"] == claim.NET
    assert manifest["photo_evidence_scope"] == {
        "de": list(claim.PHOTO_EVIDENCE_DE),
        "en": list(claim.PHOTO_EVIDENCE_EN),
    }
    assert {item["file"] for item in manifest["photos"]} == {p.name for p in claim.PHOTOS}
    assert {item["file"] for item in manifest["documents"]} == {n for n, _ in claim.DOCUMENTS}
    for item in manifest["photos"] + manifest["documents"]:
        content = (claim.SCENARIO_DIR / item["file"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == item["sha256"]
        if item["kind"] == "photo":
            image = fitz.Pixmap(content)
            assert image.width >= 1024
            assert image.height >= 768
            assert content.startswith(b"\xff\xd8\xff")
        elif item["file"].endswith(".pdf"):
            with fitz.open(stream=content, filetype="pdf") as document:
                assert document.page_count > 0
                assert all(page.get_text().strip() for page in document)


@pytest.mark.parametrize("mail", [claim.EMAIL_1, claim.EMAIL_2])
def test_watch_emails_embed_every_declared_attachment(mail: dict) -> None:
    message = BytesParser(policy=policy.default).parsebytes(
        (claim.SCENARIO_DIR / f"{mail['file']}.eml").read_bytes()
    )
    attachments = list(message.iter_attachments())
    assert [part.get_filename() for part in attachments] == mail["attachments"]
    assert len(attachments) == len(set(mail["attachments"]))
    for part in attachments:
        name = part.get_filename()
        data = part.get_payload(decode=True)
        if name.endswith(".pdf"):
            assert data == (claim.SCENARIO_DIR / name).read_bytes()
        else:
            image = fitz.Pixmap(data)
            assert max(image.width, image.height) <= 1024
            expected = _mail_attachment(name, claim.SCENARIO_DIR)
            assert expected is not None
            assert data == expected[0]
    assert str(message["Subject"]) == mail["subject"]
    assert claim.DOMAIN in str(message["From"])
    printed = pdf_text(f"{mail['file']}.pdf").replace(" ", "")
    assert all(name in printed for name in mail["attachments"])
    body = message.get_body(preferencelist=("plain",))
    assert body is not None
    content = body.get_content()
    assert isinstance(content, str)
    assert content.replace("\r\n", "\n").strip() == mail["body"].strip()
    sent = parsedate_to_datetime(message["Date"])
    photo_times = {
        photo.name: datetime.strptime(photo.taken, "%d.%m.%Y %H:%M").replace(tzinfo=sent.tzinfo)
        for photo in claim.PHOTOS
    }
    assert all(photo_times[name] < sent for name in mail["attachments"] if name in photo_times)


def test_watch_cost_estimate_prints_gross_deductible_and_net() -> None:
    with fitz.open(claim.SCENARIO_DIR / "kostenvoranschlag-schadenbehebung.pdf") as document:
        text = "".join(page.get_text() for page in document).replace("\u00a0", " ")
    for amount in (claim.TOTAL, claim.DEDUCTIBLE, claim.NET):
        assert claim.chf(amount) in text


def test_watch_photo_captions_match_claim_form_and_manifest() -> None:
    manifest = json.loads((claim.SCENARIO_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert {item["file"]: item["caption_de"] for item in manifest["photos"]} == {
        photo.name: photo.caption for photo in claim.PHOTOS
    }
    with fitz.open(claim.SCENARIO_DIR / "schadenmeldung-geschaeftsversicherung.pdf") as document:
        text = " ".join(
            unicodedata.normalize("NFKC", " ".join(page.get_text() for page in document)).split()
        )
    for photo in claim.PHOTOS:
        assert " ".join(photo.caption.split()) in text


@pytest.mark.parametrize(
    "name",
    ["schadenmeldung-geschaeftsversicherung.pdf", "kostenvoranschlag-schadenbehebung.pdf"],
)
def test_pdfs_distinguish_visible_damage_from_claimed_inventory(name: str) -> None:
    text = pdf_text(name)
    for phrase in (
        "Fotografierte Ausschnitte",
        "drei Uhrwerke",
        "vier fertige Uhren",
        "zwei Trocknungsgeräte und ein Luftgebläse",
        "kein Nachweis für Feuchtigkeit im Gehäuse",
        "312 Kaliber, 186 fertige Uhren und 24 Werkplätze",
        "Inventurlisten und technische Prüfberichte",
    ):
        assert phrase in text
    assert "während rund 25 Minuten" not in text
    assert "Restwasser" in text
    assert "Dämmung der opaken Dachfläche" in text


def test_consolidated_email_qualifies_diagnosis_and_prints_estimated_net() -> None:
    text = pdf_text("email-02-loss-estimate-en.pdf")
    for phrase in (
        "three movements",
        "four finished watches",
        "two dehumidifiers and one air mover",
        "do not establish moisture inside sealed cases",
        "inventory lists and technical inspection reports",
        "residual water",
        claim.chf_en(claim.NET),
    ):
        assert phrase in claim.EMAIL_2["body"]
        assert phrase in text
    assert "moisture inside the cases)" not in text


def test_first_notice_does_not_claim_later_work_is_already_completed() -> None:
    text = pdf_text("email-01-schadenmeldung-de.pdf")
    for phrase in ("Ausschnitte", "weiterhin Regen- und Restwasser", "ab 14:30 Uhr"):
        assert phrase in claim.EMAIL_1["body"]
        assert phrase in text
    assert claim.chf_en(claim.TOTAL) not in claim.EMAIL_1["body"]


def test_consolidated_amounts_match_both_pdfs_and_email_print() -> None:
    german_texts = [
        pdf_text("schadenmeldung-geschaeftsversicherung.pdf"),
        pdf_text("kostenvoranschlag-schadenbehebung.pdf"),
    ]
    english_text = pdf_text("email-02-loss-estimate-en.pdf")
    for amount in [*(row[2] for row in claim.DAMAGES), claim.TOTAL, claim.DEDUCTIBLE, claim.NET]:
        for text in german_texts:
            assert claim.chf(amount) in text
        assert claim.chf_en(amount) in english_text
        assert claim.chf_en(amount) in claim.EMAIL_2["body"]


def test_promotional_watch_is_separate_from_claim_evidence() -> None:
    folder = claim.ROOT / "assets" / "design-concepts" / "rheinkaliber"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["synthetic"] is True
    assert manifest["claim_evidence"] is False
    assert manifest["model"] == claim.MAI_MODEL
    content = (folder / manifest["file"]).read_bytes()
    assert manifest["sha256"] == hashlib.sha256(content).hexdigest()
    assert fitz.Pixmap(content).width >= 1024
    assert manifest["file"] not in claim.EMAIL_1["attachments"] + claim.EMAIL_2["attachments"]
    assert not (claim.SCENARIO_DIR / manifest["file"]).exists()
    assert set(manifest["logo_references"]) == {"microsoft", "github"}
    assert manifest["construction"]["central_hands"] == 3
    assert manifest["construction"]["subdials"] == 0
    assert manifest["construction"]["hour_markers"] == 12
    assert manifest["construction"]["crown_clock_position"] == 3


@pytest.mark.parametrize("name", ["unknown.jpg", claim.PHOTOS[0].name])
def test_refinement_rejects_unsupported_names_before_connecting(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    def unexpected_client() -> None:
        pytest.fail("Invalid refinement must not connect to Azure")

    monkeypatch.setattr(claim, "MaiImages", unexpected_client)
    with pytest.raises(ValueError, match="No refinement defined"):
        claim.refine_photos([name])


def test_refinement_rejects_missing_image_before_connecting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(claim, "SCENARIO_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="Photo to refine does not exist"):
        claim.refine_photos([claim.PHOTOS[1].name])


def test_construction_reference_is_read_only_and_optional(tmp_path: Path) -> None:
    def sample(name: str, width: int, height: int) -> Path:
        destination = tmp_path / name
        image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), False)
        image.clear_with(255)
        image.save(destination)
        return destination

    microsoft = sample("microsoft.png", 300, 100)
    github = sample("github.png", 200, 200)
    screenshot = sample("reference.png", 1393, 768)
    original = screenshot.read_bytes()
    simple = fitz.Pixmap(concept.reference_sheet(microsoft, github))
    with_reference = fitz.Pixmap(concept.reference_sheet(microsoft, github, screenshot))
    assert (simple.width, simple.height) == (1024, 1024)
    assert (with_reference.width, with_reference.height) == (1400, 1400)
    assert screenshot.read_bytes() == original


@pytest.mark.parametrize("names", [["follow.jpg"], ["base.jpg", "follow.jpg"], None])
def test_selected_generation_uses_existing_or_fresh_reference(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, names: list[str] | None
) -> None:
    photos = [
        claim.Photo("base.jpg", "", "", "base prompt"),
        claim.Photo("follow.jpg", "", "", "follow prompt", reference="base.jpg"),
    ]
    calls = []
    saved = []

    class Images:
        def generate(self, prompt: str) -> bytes:
            calls.append(("generate", prompt))
            return b"fresh reference"

        def edit(self, prompt: str, reference: bytes) -> bytes:
            calls.append(("edit", prompt, reference))
            return b"follow image"

    monkeypatch.setattr(claim, "PHOTOS", photos)
    monkeypatch.setattr(claim, "SCENARIO_DIR", tmp_path)
    monkeypatch.setattr(claim, "MaiImages", Images)
    monkeypatch.setattr(
        claim, "_save_jpeg", lambda image, name, folder: saved.append((name, image))
    )
    (tmp_path / "base.jpg").write_bytes(b"existing reference")
    claim.generate_photos(names)
    if names == ["follow.jpg"]:
        assert calls == [("edit", "follow prompt", b"existing reference")]
        assert saved == [("follow.jpg", b"follow image")]
    else:
        assert calls == [
            ("generate", "base prompt"),
            ("edit", "follow prompt", b"fresh reference"),
        ]
        assert saved == [("base.jpg", b"fresh reference"), ("follow.jpg", b"follow image")]


def test_image_construction_rules_apply_to_generation_and_every_edit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    photos = [
        claim.Photo(
            "base.jpg",
            "",
            "",
            "base scene",
            refinements=("correct base",),
            system_prompt="base construction rules",
        ),
        claim.Photo(
            "follow.jpg",
            "",
            "",
            "follow scene",
            reference="base.jpg",
            refinements=("correct follow",),
            system_prompt="follow construction rules",
        ),
    ]
    prompts = []

    class Images:
        def generate(self, prompt: str) -> bytes:
            prompts.append(prompt)
            return b"base"

        def edit(self, prompt: str, reference: bytes) -> bytes:
            prompts.append(prompt)
            return reference

    monkeypatch.setattr(claim, "PHOTOS", photos)
    monkeypatch.setattr(claim, "SCENARIO_DIR", tmp_path)
    monkeypatch.setattr(claim, "MaiImages", Images)
    monkeypatch.setattr(claim, "_save_jpeg", lambda *args: None)
    claim.generate_photos()
    assert prompts == [
        "base construction rules\n\nSCENE REQUEST:\nbase scene",
        "base construction rules\n\nSCENE REQUEST:\ncorrect base",
        "follow construction rules\n\nSCENE REQUEST:\nfollow scene",
        "follow construction rules\n\nSCENE REQUEST:\ncorrect follow",
    ]
    prompts.clear()
    (tmp_path / "follow.jpg").write_bytes(b"existing")
    claim.refine_photos(["follow.jpg"])
    assert prompts == ["follow construction rules\n\nSCENE REQUEST:\ncorrect follow"]


def test_selected_generation_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown photos"):
        claim.generate_photos(["unknown.jpg"])


def test_selected_generation_rejects_missing_reference_before_connecting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def unexpected_connection() -> None:
        pytest.fail("An invalid selection must not connect to Azure")

    monkeypatch.setattr(
        claim,
        "PHOTOS",
        [claim.Photo("follow.jpg", "", "", "follow prompt", reference="base.jpg")],
    )
    monkeypatch.setattr(claim, "SCENARIO_DIR", tmp_path)
    monkeypatch.setattr(claim, "MaiImages", unexpected_connection)
    with pytest.raises(FileNotFoundError, match="Reference photo does not exist"):
        claim.generate_photos(["follow.jpg"])
