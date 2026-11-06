from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import replace
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

import fitz
import pytest

from scripts import generate_swiss_storm_claim as chocolate
from scripts import generate_swiss_watch_claim as watch


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def pdf_text(claim, name: str) -> str:
    with fitz.open(claim.SCENARIO_DIR / name) as document:
        furniture = {claim.INSURER, "PrevaIQ"}
        lines = [
            line
            for page in document
            for block in page.get_text("blocks")
            if block[1] < 800
            for line in block[4].splitlines()
            if line.strip() not in furniture and not re.fullmatch(r"\d+/\d+", line.strip())
        ]
        return normalized(" ".join(lines))


@pytest.mark.parametrize("claim", [chocolate, watch], ids=["chocolate", "watch"])
def test_real_demo_anchors_are_disclosed_in_every_document_and_email(claim) -> None:
    manifest = json.loads((claim.SCENARIO_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["map_anchor"] == claim.MAP_ANCHOR
    assert manifest["identity"]["address"] == f"{claim.STREET}, {claim.TOWN}"
    assert manifest["map_anchor"]["verified_result"]["level"] == "building"
    assert "amtliches-gebaeudeadressverzeichnis" in claim.MAP_ANCHOR["official_source"]
    assert claim.LOCATION_EN in manifest["notice"]
    assert "no street" not in manifest["identity_checks"]["street"]
    assert (
        abs(
            claim.MAP_ANCHOR["official_coordinates"]["lat"]
            - claim.MAP_ANCHOR["verified_result"]["lat"]
        )
        < 0.0002
    )
    assert (
        abs(
            claim.MAP_ANCHOR["official_coordinates"]["lon"]
            - claim.MAP_ANCHOR["verified_result"]["lon"]
        )
        < 0.0002
    )
    for path in claim.SCENARIO_DIR.glob("*.pdf"):
        expected = (
            claim.LOCATION_EN
            if path.name == "email-02-loss-estimate-en.pdf"
            else (claim.LOCATION_DE)
        )
        text = pdf_text(claim, path.name)
        assert normalized(expected) in text, path.name
        assert "Kakaogasse" not in text
        assert "Unruhweg" not in text
    for mail in (claim.EMAIL_1, claim.EMAIL_2):
        message = BytesParser(policy=policy.default).parsebytes(
            (claim.SCENARIO_DIR / f"{mail['file']}.eml").read_bytes()
        )
        expected = claim.LOCATION_DE if mail is claim.EMAIL_1 else claim.LOCATION_EN
        assert expected in message.get_body(preferencelist=("plain",)).get_content().replace(
            "\r\n", "\n"
        )


def test_chocolate_manifest_hashes_instructions_and_amounts() -> None:
    manifest = json.loads((chocolate.SCENARIO_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert chocolate.TOTAL == manifest["amounts_chf"]["total"] == 1_697_400
    assert len(manifest["attention_points"]) == 3
    assert len(manifest["photos"]) == 6
    assert len(manifest["documents"]) == 5
    assert manifest["photo_evidence_scope"] == {
        "de": list(chocolate.PHOTO_EVIDENCE_DE),
        "en": list(chocolate.PHOTO_EVIDENCE_EN),
    }
    for entry in manifest["documents"] + manifest["photos"]:
        data = (chocolate.SCENARIO_DIR / entry["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        if entry["kind"] == "photo":
            image = fitz.Pixmap(data)
            assert image.width >= 1024 and image.height >= 768
            photo = next(p for p in chocolate.PHOTOS if p.name == entry["file"])
            assert photo.system_prompt
            assert entry["system_instructions"] == (
                chocolate.IMAGE_SYSTEM_INSTRUCTIONS + photo.system_prompt
            )
            assert entry["prompt"] == photo.prompt
            assert entry["refinement_prompts"] == list(photo.refinements)


@pytest.mark.parametrize("mail", [chocolate.EMAIL_1, chocolate.EMAIL_2])
def test_chocolate_emails_embed_final_evidence_before_their_send_time(mail: dict) -> None:
    message = BytesParser(policy=policy.default).parsebytes(
        (chocolate.SCENARIO_DIR / f"{mail['file']}.eml").read_bytes()
    )
    body = message.get_body(preferencelist=("plain",)).get_content()
    assert body.replace("\r\n", "\n").strip() == mail["body"].strip()
    attachments = list(message.iter_attachments())
    assert [part.get_filename() for part in attachments] == mail["attachments"]
    sent = parsedate_to_datetime(message["Date"])
    times = {
        photo.name: datetime.strptime(photo.taken, "%d.%m.%Y %H:%M").replace(tzinfo=sent.tzinfo)
        for photo in chocolate.PHOTOS
    }
    printed = pdf_text(chocolate, f"{mail['file']}.pdf").replace(" ", "")
    for part in attachments:
        name = part.get_filename()
        expected = chocolate._mail_attachment(name, chocolate.SCENARIO_DIR)
        assert expected is not None
        assert part.get_payload(decode=True) == expected[0]
        assert name in printed
        if name in times:
            assert times[name] < sent


def test_chocolate_documents_qualify_photo_scope_and_preserve_coverage_questions() -> None:
    text = pdf_text(chocolate, "schadenmeldung-geschaeftsversicherung.pdf")
    for phrase in chocolate.PHOTO_EVIDENCE_DE:
        assert normalized(phrase) in text
    for photo in chocolate.PHOTOS:
        assert normalized(photo.caption) in text
    for amount in (chocolate.TOTAL, 184_000, 96_400):
        assert chocolate.chf(amount) in text
    english = pdf_text(chocolate, "email-02-loss-estimate-en.pdf")
    for phrase in chocolate.PHOTO_EVIDENCE_EN:
        assert normalized(phrase) in english
    assert "provisional consolidated loss estimate" in english
    assert "not damage evidence or proof of the complete inventory" in english
    assert "GVZ" in english and "refrigerated goods extension" in english
    assert "not the temperature history" in english
    assert "nicht abgeschlossen" in text


def test_hail_glazing_and_food_protection_have_one_consistent_scenario() -> None:
    photos = {photo.name: photo for photo in chocolate.PHOTOS}
    before = photos["IMG_20260826_183447.jpg"]
    facade = photos["IMG_20260828_104112.jpg"]
    interior = photos["IMG_20260828_105207.jpg"]
    kitchen = photos["IMG_20260828_112604.jpg"]
    for photo in (facade, interior, kitchen):
        instruction = chocolate.image_request_prompt(photo, photo.prompt)
        assert "laminated" in instruction.lower()
        assert "interlayer" in instruction.lower()
        assert "no punched-out" in instruction.lower()
        assert "annealed-glass fragments" not in instruction
        assert "irregular missing glass" not in " ".join(photo.refinements)
    assert "FULLY RETRACTED before the storm" in facade.prompt
    assert "ABSOLUTELY NO HAIL OR ICE" in before.system_prompt
    assert "ENTIRE visible exposed pavement" in facade.prompt
    assert "lower frame/weather seal" in interior.prompt
    assert "NO gift boxes, cartons, chocolates or food" in interior.prompt
    assert "OUT OF VIEW" in interior.prompt
    for equipment in (
        "NORMAL CLOSED fitted",
        "GN food containers with FULLY CLOSED FLAT STAINLESS LIDS",
        "polycarbonate praline moulds",
        "digital scale",
        "stainless wash sink",
    ):
        assert equipment in kitchen.prompt
    assert "ohne offene Glasdurchbrüche" in chocolate.EMAIL_1["body"]
    assert "normalen Lebensmitteldeckel" in chocolate.EMAIL_1["body"]
    assert "no punched-out holes or open glass breaches" in chocolate.EMAIL_2["body"]
    assert "not solid glazing" in chocolate.EMAIL_2["body"]


def test_chocolate_system_instructions_reach_generation_reference_and_refinement(
    monkeypatch, tmp_path
) -> None:
    calls = []

    class Images:
        def generate(self, prompt):
            calls.append(("generate", prompt, None))
            return b"first"

        def edit(self, prompt, reference):
            calls.append(("edit", prompt, reference))
            return b"edited"

    first = replace(chocolate.PHOTOS[0], refinements=("first correction",))
    second = replace(chocolate.PHOTOS[1], refinements=("second correction",))
    monkeypatch.setattr(chocolate, "PHOTOS", [first, second])
    monkeypatch.setattr(chocolate, "MaiImages", Images)
    monkeypatch.setattr(chocolate, "SCENARIO_DIR", tmp_path)
    monkeypatch.setattr(chocolate, "_save_jpeg", lambda *args: None)
    chocolate.generate_photos()
    assert len(calls) == 4
    for index, (_, prompt, _) in enumerate(calls):
        photo = first if index < 2 else second
        assert prompt.startswith(chocolate.IMAGE_SYSTEM_INSTRUCTIONS)
        assert photo.system_prompt in prompt
    assert calls[2][2] == b"edited"
    (tmp_path / first.name).write_bytes(b"existing")
    calls.clear()
    chocolate.generate_photos([second.name])
    assert calls[0][2] == b"existing"
    (tmp_path / second.name).write_bytes(b"current")
    calls.clear()
    chocolate.refine_photos([second.name])
    assert calls[0] == (
        "edit",
        chocolate.image_request_prompt(second, "second correction"),
        b"current",
    )


@pytest.mark.parametrize("operation", ["generate", "refine"])
def test_chocolate_rejects_unknown_selections_before_connecting(monkeypatch, operation) -> None:
    def forbidden():
        pytest.fail("Must validate the selection before connecting to Azure")

    monkeypatch.setattr(chocolate, "MaiImages", forbidden)
    function = chocolate.generate_photos if operation == "generate" else chocolate.refine_photos
    with pytest.raises(ValueError):
        function(["unknown.jpg"])
