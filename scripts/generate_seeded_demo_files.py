"""Generate the fictitious demo files referenced by the seeded PrevaIQ cases.

Every ``files[]`` entry of the cases seeded by ``scripts/seed_customer360.py``
(``scripts/seed_data``) points to a repo asset listed in
``assets/demo-prevaiq/seeded/manifest.json``:

* PDFs are rebuilt deterministically from the seed data with PyMuPDF (same bytes on every run);
* photos are generated once with MAI-Image-2.6 (Microsoft Foundry, Entra ID auth) when
  ``--photos`` is given, then kept: existing photos are skipped unless ``--force``;
* files that already exist elsewhere in the repo are referenced (``origin: repo``), not copied.

Usage:
    python scripts/generate_seeded_demo_files.py                      # PDFs + manifest
    python scripts/generate_seeded_demo_files.py --photos             # + missing photos
    python scripts/generate_seeded_demo_files.py --photos --force --only app-hab-005

Restore them in a running environment with ``scripts/restore_demo_files.py``.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import email.utils
import hashlib
import io
import json
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Callable

import fitz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.seed_data.claims import get_claims_apps  # noqa: E402
from scripts.seed_data.mortgage import get_mortgage_apps  # noqa: E402
from scripts.seed_data.underwriting import get_underwriting_apps  # noqa: E402

DEMO_DIR = ROOT / "assets" / "demo-prevaiq"
SEEDED_DIR = DEMO_DIR / "seeded"
MANIFEST_PATH = SEEDED_DIR / "manifest.json"
FOOTER_TEXT = "Document fictif — démonstration PrevaIQ"

# Seeded cases whose files already exist in the repo (referenced, never duplicated).
REPO_FOLDERS = {
    "app-mtg-004": "mortgage-underwriting/primo-accedant/app-mtg-004",
    "app-mtg-005": "mortgage-underwriting/primo-accedant-ptz/app-mtg-005",
    "app-mtg-006": "mortgage-underwriting/rachat-credit/app-mtg-006",
    "app-mtg-007": "mortgage-underwriting/frontalier/app-mtg-007",
    "app-mtg-008": "mortgage-underwriting/incomplet/app-mtg-008",
}
# Demo cases uploaded in production (not seeded) whose file is a repo asset.
EXTRA_REPO_FILES = [
    (
        "b6fc2d4c",
        "thread4-01-client-dentaire.pdf",
        "health-claims/dental/thread4-01-client-dentaire.pdf",
    ),
]

MAI_ENDPOINT = "https://ai-workbenchiq-foundry.services.ai.azure.com"
MAI_DEPLOYMENT = "mai-image-2-6-temp"
MAI_MODEL = "MAI-Image-2.6"
MAI_VERSION = "2026-07-31"
MAI_SCOPE = "https://cognitiveservices.azure.com/.default"
MIN_REQUEST_INTERVAL_S = 20.0  # at most 3 requests per minute (quota shared with other jobs)
MAX_ATTEMPTS = 6
PHOTO_MAX_SIDE = 1600
JPEG_QUALITY = 85


# =============================================================================
# Formatting helpers
# =============================================================================

NBSP = "\u00a0"
CENT = Decimal("0.01")


def q2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def D(value: str | int | float | Decimal) -> Decimal:
    return Decimal(str(value))


def eur(value: Decimal | int | str) -> str:
    """French money format with non-breaking spaces: 1 234,50 €."""
    amount = q2(D(value))
    whole, cents = f"{abs(amount):.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    sign = "-" if amount < 0 else ""
    return f"{sign}{NBSP.join(groups)},{cents}{NBSP}€"


def num(value: Decimal | int | str) -> str:
    """Quantity in French notation without useless decimals (1,5 / 12)."""
    text = f"{D(value).normalize():f}"
    return text.replace(".", ",")


def pct(rate: Decimal) -> str:
    return f"{num(rate * 100)}{NBSP}%"


def parse_money(raw: Any) -> Decimal:
    """Parse seed amounts such as '3 200,00 €', '8500€' or '1900.00'."""
    text = str(raw).replace("€", "").replace(NBSP, "").replace(" ", "").strip()
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    return q2(Decimal(text))


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, char in enumerate(reversed(digits)):
        n = int(char) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def _fake_digits(seed: str, length: int) -> str:
    """Stable digits that never pass the Luhn check, so they cannot be a real identifier."""
    digits = str(int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16))[:length]
    digits = ("7" + digits[1:]) if digits[0] == "0" else digits
    if _luhn_ok(digits):
        digits = digits[:-1] + str((int(digits[-1]) + 1) % 10)
    return digits


def fake_siret(name: str) -> str:
    """Fictitious SIRET (14 digits); neither the SIREN nor the SIRET pass the Luhn check."""
    siren = _fake_digits(f"siren:{name}", 9)
    siret = siren + _fake_digits(f"nic:{name}", 5)
    if _luhn_ok(siret):
        siret = siret[:-1] + str((int(siret[-1]) + 1) % 10)
    return f"{siret[:3]} {siret[3:6]} {siret[6:9]} {siret[9:]}"


def fake_vat(name: str) -> str:
    siren = fake_siret(name).replace(" ", "")[:9]
    key = (12 + 3 * (int(siren) % 97)) % 97
    return f"FR{key:02d} {siren}"


def fake_rpps(name: str) -> str:
    return "10" + _fake_digits(f"rpps:{name}", 9)


def pdf_date(day: str) -> str:
    """DD/MM/YYYY → PDF date string (fixed time keeps the output deterministic)."""
    d, m, y = day.split("/")
    return f"D:{y}{m}{d}120000+01'00'"


# =============================================================================
# Seed access
# =============================================================================


class Case:
    """Read-only view of a seeded case dict (extracted fields, LLM outputs)."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.id: str = data["id"]

    def field(self, *names: str) -> str:
        fields = self.data.get("extracted_fields") or {}
        for name in names:
            value = fields.get(name)
            if isinstance(value, dict):
                value = value.get("value")
            if value not in (None, ""):
                return str(value)
        raise KeyError(f"{self.id}: none of {names} in extracted_fields")

    def money(self, *names: str) -> Decimal:
        return parse_money(self.field(*names))

    def parsed(self, section: str, subsection: str) -> dict[str, Any]:
        return self.data["llm_outputs"][section][subsection]["parsed"]

    def amount(self, section: str, subsection: str, key: str) -> Decimal:
        return q2(D(self.parsed(section, subsection)[key]))

    @property
    def created(self) -> str:
        return dt.date.fromisoformat(self.data["created_at"][:10]).strftime("%d/%m/%Y")


def seeded_cases() -> list[dict[str, Any]]:
    return get_underwriting_apps() + get_claims_apps() + get_mortgage_apps()


def expect(label: str, actual: Decimal, expected: Decimal) -> None:
    """Fail loudly when a generated document drifts from its seed amounts."""
    if q2(actual) != q2(expected):
        raise ValueError(f"{label}: computed {actual} but the seed says {expected}")


# =============================================================================
# Layout engine (TextWriter: full Unicode, no ligatures, so text extracts verbatim)
# =============================================================================

RGB = tuple[float, float, float]
PAGE_W, PAGE_H = fitz.paper_size("a4")
MARGIN = 42.0
CONTENT_W = PAGE_W - 2 * MARGIN
RIGHT = PAGE_W - MARGIN
BODY_BOTTOM = PAGE_H - 44.0
LEADING = 1.3
INK: RGB = (0.12, 0.15, 0.2)
MUTED: RGB = (0.4, 0.44, 0.5)
GRID: RGB = (0.8, 0.83, 0.86)
WHITE: RGB = (1.0, 1.0, 1.0)
PEN: RGB = (0.1, 0.16, 0.45)
AMBER: RGB = (0.8, 0.5, 0.05)
RED: RGB = (0.72, 0.16, 0.16)
GREEN: RGB = (0.13, 0.5, 0.3)
FONTS = {
    "r": fitz.Font("helv"),
    "b": fitz.Font("hebo"),
    "i": fitz.Font("heit"),
    "bi": fitz.Font("hebi"),
}


def rgb(hex_color: str) -> RGB:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def mix(color: RGB, other: RGB, ratio: float) -> RGB:
    return tuple(round(a * (1 - ratio) + b * ratio, 4) for a, b in zip(color, other))  # type: ignore[return-value]


def text_width(text: str, style: str = "r", size: float = 9.0) -> float:
    return FONTS[style].text_length(text, fontsize=size)


def wrap(text: str, width: float, style: str = "r", size: float = 9.0) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            if line and text_width(candidate, style, size) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


def measure(text: str, width: float, style: str = "r", size: float = 9.0) -> float:
    return len(wrap(text, width, style, size)) * size * LEADING


class Canvas:
    """Flowing layout over A4 pages with automatic page breaks."""

    def __init__(self, accent: RGB, running_title: str, tight: bool = False) -> None:
        self.doc = fitz.open()
        self.accent = accent
        self.tint = mix(accent, WHITE, 0.9)
        self.soft = mix(accent, WHITE, 0.55)
        self.running_title = running_title
        self.k = 0.5 if tight else 1.0  # vertical spacing factor (tight avoids orphan pages)
        self.page: fitz.Page | None = None
        self._writers: dict[RGB, fitz.TextWriter] = {}
        self.y = 0.0
        self.new_page()

    def new_page(self) -> None:
        self._flush()
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        self.rect(fitz.Rect(0, 0, PAGE_W, 5), fill=self.accent)
        if self.doc.page_count == 1:
            self.y = 18.0
            return
        self.text(MARGIN, 24, self.running_title, size=7.5, color=MUTED)
        self.hline(30, GRID, 0.6)
        self.y = 42.0

    def _flush(self) -> None:
        if self.page is not None:
            for color, writer in self._writers.items():
                writer.write_text(self.page, color=color)
        self._writers = {}

    def finish(self) -> fitz.Document:
        self._flush()
        return self.doc

    def ensure(self, height: float) -> None:
        if self.y + height > BODY_BOTTOM:
            self.new_page()

    def text(
        self, x: float, y: float, text: str, style: str = "r", size: float = 9.0, color: RGB = INK
    ) -> None:
        if not text:
            return
        writer = self._writers.get(color)
        if writer is None:
            writer = self._writers[color] = fitz.TextWriter(self.page.rect)
        writer.append(fitz.Point(x, y), text, font=FONTS[style], fontsize=size)

    def block(
        self,
        x: float,
        top: float,
        width: float,
        text: str,
        style: str = "r",
        size: float = 9.0,
        color: RGB = INK,
        align: str = "l",
    ) -> float:
        """Draw wrapped text whose first line box starts at ``top``; return the height used."""
        lines = wrap(text, width, style, size)
        for i, line in enumerate(lines):
            offset = {"r": width - text_width(line, style, size)}.get(align, 0.0)
            if align == "c":
                offset = (width - text_width(line, style, size)) / 2
            self.text(x + offset, top + size * 0.95 + i * size * LEADING, line, style, size, color)
        return len(lines) * size * LEADING

    def line(self, x0: float, y0: float, x1: float, y1: float, color: RGB, width: float) -> None:
        self.page.draw_line(fitz.Point(x0, y0), fitz.Point(x1, y1), color=color, width=width)

    def hline(self, y: float, color: RGB, width: float) -> None:
        self.line(MARGIN, y, RIGHT, y, color, width)

    def rect(
        self, r: fitz.Rect, stroke: RGB | None = None, fill: RGB | None = None, width: float = 0.6
    ) -> None:
        self.page.draw_rect(r, color=stroke, fill=fill, width=width if stroke else 0)

    def checkbox(self, x: float, top: float, checked: bool) -> None:
        box = fitz.Rect(x, top, x + 8, top + 8)
        self.rect(box, stroke=INK, width=0.7)
        if checked:
            self.line(box.x0 + 1.6, box.y0 + 1.6, box.x1 - 1.6, box.y1 - 1.6, PEN, 1.3)
            self.line(box.x0 + 1.6, box.y1 - 1.6, box.x1 - 1.6, box.y0 + 1.6, PEN, 1.3)

    def scribble(self, box: fitz.Rect, seed: str) -> None:
        """Deterministic handwritten-looking signature."""
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        count = 7
        points = [
            fitz.Point(
                box.x0 + box.width * k / (count - 1),
                box.y0 + box.height * (0.2 + 0.6 * digest[k] / 255),
            )
            for k in range(count)
        ]
        shape = self.page.new_shape()
        for k in range(count - 1):
            p0, p3 = points[k], points[k + 1]
            step = p3.x - p0.x
            c1 = fitz.Point(p0.x + step * 0.2, p0.y - box.height * (digest[k + 8] / 255 - 0.3))
            c2 = fitz.Point(p0.x + step * 0.8, p3.y + box.height * (digest[k + 16] / 255 - 0.3))
            shape.draw_bezier(p0, c1, c2, p3)
        tail = fitz.Point(box.x0 + box.width * 0.15, box.y1 - 2)
        shape.draw_line(tail, fitz.Point(box.x1 - box.width * 0.1, box.y1 - 4))
        shape.finish(color=PEN, width=0.9, closePath=False)
        shape.commit()

    def arrow(self, start: fitz.Point, end: fitz.Point, color: RGB = INK) -> None:
        self.page.draw_line(start, end, color=color, width=1.2)
        vec = end - start
        length = abs(vec) or 1.0
        ux, uy = vec.x / length, vec.y / length
        left = fitz.Point(end.x - 7 * ux + 3.5 * uy, end.y - 7 * uy - 3.5 * ux)
        right = fitz.Point(end.x - 7 * ux - 3.5 * uy, end.y - 7 * uy + 3.5 * ux)
        self.page.draw_polyline([left, end, right], color=color, fill=color, closePath=True)

    def stamp(self, text: str, center: fitz.Point, color: RGB) -> None:
        width = text_width(text, "b", 12) + 16
        box = fitz.Rect(center.x - width / 2, center.y - 11, center.x + width / 2, center.y + 11)
        morph = (center, fitz.Matrix(-8))
        shape = self.page.new_shape()
        shape.draw_rect(box)
        shape.finish(color=color, width=1.5, morph=morph, stroke_opacity=0.85)
        shape.commit()
        writer = fitz.TextWriter(self.page.rect)
        writer.append(fitz.Point(box.x0 + 8, center.y + 4.3), text, font=FONTS["b"], fontsize=12)
        writer.write_text(self.page, color=color, morph=morph, opacity=0.85)


# --- Blocks -------------------------------------------------------------------


@dataclass
class Section:
    title: str
    keep: float = 48.0  # space to keep with the heading (avoids orphan headings)

    def draw(self, cv: Canvas) -> None:
        cv.ensure(self.keep)
        cv.y += 5 * cv.k
        cv.text(MARGIN, cv.y + 9, self.title.upper(), "b", 8.8, cv.accent)
        cv.y += 13
        cv.hline(cv.y, cv.soft, 0.8)
        cv.y += 6 * cv.k


@dataclass
class Fields:
    rows: list[tuple[str, str]]
    cols: int = 2
    label_ratio: float = 0.38

    def draw(self, cv: Canvas) -> None:
        gap = 14.0
        col_w = (CONTENT_W - gap * (self.cols - 1)) / self.cols
        label_w = col_w * self.label_ratio
        value_w = col_w - label_w - 4
        for start in range(0, len(self.rows), self.cols):
            chunk = self.rows[start : start + self.cols]
            height = 2.5 * cv.k + max(
                max(measure(label, label_w, "r", 7.8), measure(value, value_w, "r", 8.6))
                for label, value in chunk
            )
            cv.ensure(height)
            for j, (label, value) in enumerate(chunk):
                x = MARGIN + j * (col_w + gap)
                cv.block(x, cv.y, label_w, label, size=7.8, color=MUTED)
                cv.block(x + label_w + 4, cv.y, value_w, value, size=8.6)
            cv.y += height
        cv.y += 4 * cv.k


@dataclass
class Para:
    text: str
    size: float = 8.8
    style: str = "r"
    color: RGB = INK

    def draw(self, cv: Canvas) -> None:
        step = self.size * LEADING
        for line in wrap(self.text, CONTENT_W, self.style, self.size):
            cv.ensure(step)
            cv.text(MARGIN, cv.y + self.size * 0.95, line, self.style, self.size, self.color)
            cv.y += step
        cv.y += 4 * cv.k


@dataclass
class Bullets:
    items: list[str]
    size: float = 8.6

    def draw(self, cv: Canvas) -> None:
        for item in self.items:
            height = measure(item, CONTENT_W - 12, "r", self.size)
            cv.ensure(height)
            cv.text(MARGIN + 2, cv.y + self.size * 0.95, "•", "b", self.size, cv.accent)
            cv.block(MARGIN + 12, cv.y, CONTENT_W - 12, item, size=self.size)
            cv.y += height + 1.5 * cv.k
        cv.y += 4 * cv.k


@dataclass
class Col:
    header: str
    width: float
    align: str = "l"


@dataclass
class Table:
    cols: list[Col]
    rows: list[list[str]]
    footer: list[list[str]] = field(default_factory=list)
    size: float = 8.2

    def draw(self, cv: Canvas) -> None:
        total = sum(col.width for col in self.cols)
        widths = [CONTENT_W * col.width / total for col in self.cols]
        pad = 3.5 if cv.k == 1 else 2.6

        def height(cells: list[str], style: str) -> float:
            return 2 * pad + max(
                measure(cell, w - 2 * pad, style, self.size) for cell, w in zip(cells, widths)
            )

        def row(cells: list[str], style: str, fill: RGB | None = None) -> None:
            h = height(cells, style)
            if fill:
                cv.rect(fitz.Rect(MARGIN, cv.y, RIGHT, cv.y + h), fill=fill)
            x = MARGIN
            for cell, w, col in zip(cells, widths, self.cols):
                cv.block(x + pad, cv.y + pad, w - 2 * pad, cell, style, self.size, INK, col.align)
                x += w
            cv.y += h
            cv.hline(cv.y, GRID, 0.5)

        def header() -> None:
            cv.hline(cv.y, cv.accent, 0.9)
            row([col.header for col in self.cols], "b", cv.tint)

        first = self.rows[0] if self.rows else [col.header for col in self.cols]
        cv.ensure(height([c.header for c in self.cols], "b") + height(first, "r"))
        header()
        for cells in self.rows:
            if cv.y + height(cells, "r") > BODY_BOTTOM:
                cv.new_page()
                header()
            row(cells, "r")
        for cells in self.footer:
            cv.ensure(height(cells, "b"))
            row(cells, "b", cv.tint)
        cv.y += 7 * cv.k


@dataclass
class Totals:
    rows: list[tuple[str, str]]
    width: float = 235.0

    def draw(self, cv: Canvas) -> None:
        cv.ensure(len(self.rows) * 15 + 6)
        x0 = RIGHT - self.width
        for i, (label, value) in enumerate(self.rows):
            last = i == len(self.rows) - 1
            style, h = ("b", 17.0) if last else ("r", 14.0)
            if last:
                cv.rect(fitz.Rect(x0, cv.y, RIGHT, cv.y + h), fill=cv.tint)
            base = cv.y + h / 2 + 3.1
            cv.text(x0 + 6, base, label, style, 8.6, INK if last else MUTED)
            cv.text(RIGHT - 6 - text_width(value, style, 8.8), base, value, style, 8.8)
            cv.y += h
            if not last:
                cv.line(x0, cv.y, RIGHT, cv.y, GRID, 0.4)
        cv.y += 8 * cv.k


@dataclass
class Note:
    title: str
    text: str
    tone: str = "info"

    def draw(self, cv: Canvas) -> None:
        color = {"info": cv.accent, "warn": AMBER, "alert": RED, "ok": GREEN}[self.tone]
        inner = CONTENT_W - 20
        height = 12 + (12 if self.title else 0) + measure(self.text, inner, "r", 8.4)
        cv.ensure(height)
        cv.rect(fitz.Rect(MARGIN, cv.y, RIGHT, cv.y + height), fill=mix(color, WHITE, 0.92))
        cv.rect(fitz.Rect(MARGIN, cv.y, MARGIN + 3, cv.y + height), fill=color)
        top = cv.y + 6
        if self.title:
            cv.text(MARGIN + 12, top + 8.4, self.title, "b", 8.6, color)
            top += 12
        cv.block(MARGIN + 12, top, inner, self.text, size=8.4)
        cv.y += height + 8 * cv.k


@dataclass
class Columns:
    """Side-by-side titled boxes of (label, value) rows; an empty label means free text."""

    boxes: list[tuple[str, list[tuple[str, str]]]]
    label_ratio: float = 0.42

    def draw(self, cv: Canvas) -> None:
        gap, pad = 10.0, 6.0
        width = (CONTENT_W - gap * (len(self.boxes) - 1)) / len(self.boxes)
        inner = width - 2 * pad
        label_w = inner * self.label_ratio

        def row_height(label: str, value: str) -> float:
            if not label:
                return measure(value, inner, "r", 8.3) + 1.5
            return (
                max(
                    measure(label, label_w - 4, "r", 7.6), measure(value, inner - label_w, "r", 8.3)
                )
                + 1.5
            )

        box_h = max(22 + pad + sum(row_height(*r) for r in rows) for _, rows in self.boxes)
        cv.ensure(box_h)
        for i, (title, rows) in enumerate(self.boxes):
            x = MARGIN + i * (width + gap)
            cv.rect(fitz.Rect(x, cv.y, x + width, cv.y + 16), fill=cv.tint)
            cv.rect(fitz.Rect(x, cv.y, x + width, cv.y + box_h), stroke=GRID, width=0.6)
            cv.text(x + pad, cv.y + 11.2, title, "b", 8.4, cv.accent)
            top = cv.y + 16 + pad
            for label, value in rows:
                if label:
                    cv.block(x + pad, top, label_w - 4, label, size=7.6, color=MUTED)
                    cv.block(x + pad + label_w, top, inner - label_w, value, size=8.3)
                else:
                    cv.block(x + pad, top, inner, value, size=8.3)
                top += row_height(label, value)
        cv.y += box_h + 8 * cv.k


@dataclass
class Checklist:
    items: list[tuple[bool, str]]
    cols: int = 2

    def draw(self, cv: Canvas) -> None:
        gap = 12.0
        width = (CONTENT_W - gap * (self.cols - 1)) / self.cols
        for start in range(0, len(self.items), self.cols):
            chunk = self.items[start : start + self.cols]
            height = 3 + max(measure(label, width - 16, "r", 8.4) for _, label in chunk)
            cv.ensure(height)
            for j, (checked, label) in enumerate(chunk):
                x = MARGIN + j * (width + gap)
                cv.checkbox(x, cv.y + 1.6, checked)
                cv.block(x + 14, cv.y, width - 16, label, "b" if checked else "r", 8.4)
            cv.y += height
        cv.y += 5 * cv.k


CIRCUMSTANCES = [
    "en stationnement / à l'arrêt",
    "quittait un stationnement / ouvrait une portière",
    "prenait un stationnement",
    "sortait d'un parking, d'un lieu privé, d'un chemin de terre",
    "s'engageait dans un parking, un lieu privé, un chemin de terre",
    "s'engageait sur une place à sens giratoire",
    "roulait sur une place à sens giratoire",
    "heurtait à l'arrière, en roulant dans le même sens et sur une même file",
    "roulait dans le même sens et sur une file différente",
    "changeait de file",
    "doublait",
    "virait à droite",
    "virait à gauche",
    "reculait",
    "empiétait sur une voie réservée à la circulation en sens inverse",
    "venait de droite (dans un carrefour)",
    "n'avait pas observé un signal de priorité ou un feu rouge",
]


@dataclass
class Circumstances:
    """Box 12 of the European accident statement: numbered circumstances for A and B."""

    a: set[int]
    b: set[int]

    def draw(self, cv: Canvas) -> None:
        cv.ensure(len(CIRCUMSTANCES) * 12 + 34)
        cv.rect(fitz.Rect(MARGIN, cv.y, RIGHT, cv.y + 14), fill=cv.tint)
        cv.text(MARGIN + 6, cv.y + 10, "A", "b", 8.6, cv.accent)
        cv.text(RIGHT - 12, cv.y + 10, "B", "b", 8.6, cv.accent)
        cv.block(
            MARGIN + 30,
            cv.y + 2.5,
            CONTENT_W - 60,
            "Mettre une croix dans chacune des cases utiles pour préciser le croquis",
            "b",
            7.8,
            INK,
            "c",
        )
        cv.y += 17
        for n, label in enumerate(CIRCUMSTANCES, start=1):
            cv.checkbox(MARGIN + 4, cv.y + 1.5, n in self.a)
            cv.checkbox(RIGHT - 13, cv.y + 1.5, n in self.b)
            marked = n in self.a or n in self.b
            cv.text(MARGIN + 24, cv.y + 8.6, f"{n}", "b", 7.8, cv.accent)
            cv.text(MARGIN + 40, cv.y + 8.6, label, "b" if marked else "r", 8.0)
            cv.y += 12
        cv.hline(cv.y + 1, GRID, 0.5)
        summary = f"Nombre de cases marquées : A = {len(self.a)} · B = {len(self.b)}"
        cv.text(MARGIN, cv.y + 12, summary, "b", 8.2)
        cv.y += 22


@dataclass
class Signatures:
    items: list[tuple[str, str]]
    place_date: str = ""

    def draw(self, cv: Canvas) -> None:
        height, gap = 58.0, 14.0
        cv.ensure(height + 4)
        count = len(self.items)
        width = (CONTENT_W - gap * (count - 1)) / count if count > 1 else 280.0
        start = MARGIN if count > 1 else RIGHT - width
        for i, (caption, signer) in enumerate(self.items):
            x = start + i * (width + gap)
            cv.rect(fitz.Rect(x, cv.y, x + width, cv.y + height), stroke=GRID, width=0.6)
            cv.text(x + 6, cv.y + 10, caption, size=7.6, color=MUTED)
            if i == 0 and self.place_date:
                place_x = x + width - 6 - text_width(self.place_date, "r", 7.6)
                cv.text(place_x, cv.y + 10, self.place_date, size=7.6)
            if signer:
                box = fitz.Rect(x + 16, cv.y + 15, x + min(width - 16, 150), cv.y + 40)
                cv.scribble(box, signer)
                cv.text(x + 6, cv.y + 52, signer, "i", 7.8)
        cv.y += height + 6


@dataclass
class Stamp:
    text: str
    tone: str = "ok"

    def draw(self, cv: Canvas) -> None:
        color = {"ok": GREEN, "info": cv.accent, "alert": RED}[self.tone]
        cv.ensure(46)
        cv.stamp(self.text, fitz.Point(RIGHT - 80, cv.y + 22), color)
        cv.y += 46


@dataclass
class Sketch:
    """Schematic accident sketch (box 13 of the accident statement)."""

    kind: str
    caption: str = ""

    def draw(self, cv: Canvas) -> None:
        height = 140.0
        cv.ensure(height + 18)
        box = fitz.Rect(MARGIN, cv.y, RIGHT, cv.y + height)
        cv.rect(box, stroke=GRID, width=0.6)
        {
            "rear": _sketch_rear,
            "parking": _sketch_parking,
            "lane": _sketch_lane,
            "obstacle": _sketch_obstacle,
        }[self.kind](cv, box)
        cv.y += height + 3
        if self.caption:
            cv.y += cv.block(MARGIN, cv.y, CONTENT_W, self.caption, "i", 7.6, MUTED)
        cv.y += 8


def _car(cv: Canvas, center: fitz.Point, label: str, vertical: bool = False) -> None:
    w, h = (18, 36) if vertical else (40, 18)
    r = fitz.Rect(center.x - w / 2, center.y - h / 2, center.x + w / 2, center.y + h / 2)
    cv.page.draw_rect(r, color=INK, fill=cv.tint, width=0.9, radius=0.25)
    cv.text(center.x - text_width(label, "b", 10) / 2, center.y + 3.6, label, "b", 10, cv.accent)


def _impact(cv: Canvas, point: fitz.Point) -> None:
    cv.page.draw_circle(point, 4.5, color=RED, fill=mix(RED, WHITE, 0.5), width=1)


def _road(cv: Canvas, box: fitz.Rect, top: float, bottom: float, label: str) -> None:
    cv.line(box.x0 + 8, top, box.x1 - 8, top, MUTED, 1.2)
    cv.line(box.x0 + 8, bottom, box.x1 - 8, bottom, MUTED, 1.2)
    middle = (top + bottom) / 2
    cv.page.draw_line(
        fitz.Point(box.x0 + 8, middle),
        fitz.Point(box.x1 - 8, middle),
        color=GRID,
        width=1,
        dashes="[6 5] 0",
    )
    cv.text(box.x0 + 12, top - 5, label, "i", 7.6, MUTED)


def _sketch_rear(cv: Canvas, box: fitz.Rect) -> None:
    top, bottom = box.y0 + 38, box.y1 - 38
    _road(cv, box, top, bottom, "Avenue Jean Jaurès → rue de Metz")
    stop_x = box.x0 + box.width * 0.72
    cv.line(stop_x, (top + bottom) / 2, stop_x, bottom, INK, 2)
    light = fitz.Rect(stop_x + 6, bottom + 4, stop_x + 14, bottom + 26)
    cv.page.draw_rect(light, color=INK, fill=INK, width=0.5)
    cv.page.draw_circle(fitz.Point(light.x0 + 4, light.y0 + 5), 2.4, color=None, fill=RED)
    lane = (top + bottom) / 2 + (bottom - top) / 4
    a = fitz.Point(stop_x - 30, lane)
    b = fitz.Point(stop_x - 82, lane)
    _car(cv, a, "A")
    _car(cv, b, "B")
    cv.arrow(fitz.Point(b.x - 70, lane), fitz.Point(b.x - 24, lane))
    _impact(cv, fitz.Point(a.x - 21, lane))
    cv.text(stop_x + 18, bottom + 20, "feu rouge", "i", 7.4, MUTED)


def _sketch_parking(cv: Canvas, box: fitz.Rect) -> None:
    row_top = box.y0 + 14
    for k in range(9):
        x = box.x0 + 60 + k * 46
        cv.line(x, row_top, x, row_top + 52, MUTED, 1)
    cv.line(box.x0 + 60, row_top, box.x0 + 60 + 8 * 46, row_top, MUTED, 1)
    cv.text(box.x0 + 12, box.y1 - 8, "Allée de circulation du parking", "i", 7.6, MUTED)
    b = fitz.Point(box.x0 + 60 + 4.5 * 46, row_top + 28)
    a = fitz.Point(b.x - 26, row_top + 58)
    _car(cv, b, "B", vertical=True)
    _car(cv, a, "A", vertical=True)
    cv.arrow(fitz.Point(a.x, a.y + 20), fitz.Point(a.x - 26, a.y + 54))
    _impact(cv, fitz.Point(b.x - 13, row_top + 43))
    cv.text(b.x + 14, row_top + 66, "B : véhicule en stationnement", "i", 7.4, MUTED)


def _sketch_lane(cv: Canvas, box: fitz.Rect) -> None:
    top, bottom = box.y0 + 30, box.y1 - 30
    _road(cv, box, top, bottom, "Promenade des Anglais — sens de circulation →")
    upper = top + (bottom - top) / 4
    lower = bottom - (bottom - top) / 4
    a = fitz.Point(box.x0 + box.width * 0.55, upper)
    b = fitz.Point(box.x0 + box.width * 0.44, lower)
    _car(cv, a, "A")
    _car(cv, b, "B")
    cv.arrow(fitz.Point(a.x - 90, upper), fitz.Point(a.x - 24, upper))
    cv.arrow(fitz.Point(b.x + 22, lower - 3), fitz.Point(a.x - 4, upper + 11))
    _impact(cv, fitz.Point(a.x + 2, upper + 9))


def _sketch_obstacle(cv: Canvas, box: fitz.Rect) -> None:
    top, bottom = box.y0 + 36, box.y1 - 40
    _road(cv, box, top, bottom, "RN57 — sortie sud de Nancy")
    pole = fitz.Point(box.x0 + box.width * 0.7, bottom + 14)
    cv.page.draw_circle(pole, 5, color=INK, fill=MUTED, width=0.8)
    cv.text(pole.x + 9, pole.y + 3, "poteau béton", "i", 7.4, MUTED)
    animal = fitz.Point(box.x0 + box.width * 0.55, top + 12)
    cv.page.draw_oval(
        fitz.Rect(animal.x - 8, animal.y - 4, animal.x + 8, animal.y + 4),
        color=AMBER,
        fill=mix(AMBER, WHITE, 0.4),
        width=0.8,
    )
    cv.text(animal.x + 11, animal.y + 3, "animal (chevreuil)", "i", 7.4, MUTED)
    lane = bottom - (bottom - top) / 4
    a = fitz.Point(box.x0 + box.width * 0.3, lane)
    _car(cv, a, "A")
    cv.arrow(fitz.Point(a.x + 24, lane), fitz.Point(pole.x - 7, pole.y - 5))
    _impact(cv, fitz.Point(pole.x - 4, pole.y - 7))


# --- Documents ---------------------------------------------------------------


@dataclass(frozen=True)
class Party:
    name: str
    activity: str
    lines: tuple[str, ...]
    accent: RGB = rgb("#17395C")


@dataclass
class DocSpec:
    title: str
    issuer: Party
    date: str
    refs: list[tuple[str, str]]
    blocks: list[Any]
    subtitle: str = ""
    scanned: bool = False


def company(
    name: str, activity: str, address: str, phone: str, email: str, accent: str, vat: bool = True
) -> Party:
    ids = f"SIRET {fake_siret(name)}" + (f" · TVA {fake_vat(name)}" if vat else "")
    return Party(name, activity, (address, f"Tél. {phone} · {email}", ids), rgb(accent))


def _draw_header(cv: Canvas, spec: DocSpec) -> None:
    issuer = spec.issuer
    top = cv.y
    cv.text(MARGIN, top + 13, issuer.name, "b", 12.5, issuer.accent)
    y = top + 18
    if issuer.activity:
        y += cv.block(MARGIN, y, 300, issuer.activity, "i", 8, MUTED)
    for line in issuer.lines:
        y += cv.block(MARGIN, y, 300, line, "r", 7.5, MUTED)
    ref_y = top + 3
    for label, value in spec.refs:
        value_w = text_width(value, "b", 8.2)
        cv.text(RIGHT - value_w, ref_y + 9, value, "b", 8.2)
        prefix = f"{label} : "
        cv.text(RIGHT - value_w - text_width(prefix, "r", 8.2), ref_y + 9, prefix, "r", 8.2, MUTED)
        ref_y += 11.5
    y = max(y, ref_y) + 7
    cv.hline(y, issuer.accent, 1.1)
    y += 5
    y += cv.block(MARGIN, y, CONTENT_W, spec.title, "b", 14.5)
    if spec.subtitle:
        y += cv.block(MARGIN, y + 1, CONTENT_W, spec.subtitle, "r", 8.8, MUTED) + 1
    cv.y = y + 9 * cv.k


def _scan(doc: fitz.Document, seed: str) -> fitz.Document:
    """Turn pages into a low-resolution greyish scan (about 100 DPI)."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    scanned = fitz.open()
    for page in doc:
        for k in range(0, 60, 2):  # dust specks
            x = page.rect.width * digest[k % 32] / 255
            y = page.rect.height * digest[(k + 7) % 32] / 255
            page.draw_circle(
                fitz.Point(x, y),
                0.6 + digest[(k + 3) % 32] / 255,
                color=None,
                fill=(0.55, 0.55, 0.55),
            )
        page.draw_rect(fitz.Rect(0, 0, 9, page.rect.height), color=None, fill=(0.82, 0.82, 0.8))
        matrix = fitz.Matrix(100 / 72, 100 / 72).prerotate(0.7)
        pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
        pix.tint_with(0x2A2A2A, 0xEFEDE6)
        target = scanned.new_page(width=page.rect.width, height=page.rect.height)
        target.insert_image(target.rect, stream=pix.tobytes("jpg", jpg_quality=40))
    return scanned


def _add_footers(doc: fitz.Document) -> None:
    for page in doc:
        page.draw_line(
            fitz.Point(MARGIN, PAGE_H - 34), fitz.Point(RIGHT, PAGE_H - 34), color=GRID, width=0.5
        )
        writer = fitz.TextWriter(page.rect)
        writer.append(fitz.Point(MARGIN, PAGE_H - 22), FOOTER_TEXT, font=FONTS["b"], fontsize=7.5)
        label = f"Page {page.number + 1}/{doc.page_count}"
        writer.append(
            fitz.Point(RIGHT - text_width(label, "r", 7.5), PAGE_H - 22),
            label,
            font=FONTS["r"],
            fontsize=7.5,
        )
        writer.write_text(page, color=MUTED)


def _layout(spec: DocSpec, tight: bool) -> tuple[fitz.Document, bool]:
    """Lay out the document; also report whether the last block was pushed alone to a new page."""
    cv = Canvas(spec.issuer.accent, f"{spec.issuer.name} — {spec.title}", tight)
    _draw_header(cv, spec)
    pages_before_last = 1
    for block in spec.blocks:
        pages_before_last = cv.doc.page_count
        block.draw(cv)
    return cv.finish(), cv.doc.page_count > pages_before_last


def render_pdf(spec: DocSpec, key: str) -> bytes:
    doc, orphan = _layout(spec, tight=False)
    if orphan:
        doc, _ = _layout(spec, tight=True)
    if spec.scanned:
        doc = _scan(doc, key)
    if doc.page_count > 2:
        raise ValueError(f"{key}: {doc.page_count} pages (max 2)")
    _add_footers(doc)
    doc.set_metadata(
        {
            "title": spec.title,
            "author": spec.issuer.name,
            "subject": FOOTER_TEXT,
            "keywords": key,
            "creator": "scripts/generate_seeded_demo_files.py",
            "producer": "PyMuPDF",
            "creationDate": pdf_date(spec.date),
            "modDate": pdf_date(spec.date),
        }
    )
    doc.subset_fonts()
    return doc.tobytes(garbage=4, deflate=True, no_new_id=True)


# --- Invoice helpers -----------------------------------------------------------


@dataclass(frozen=True)
class Line:
    label: str
    qty: str
    unit: str
    price: str

    @property
    def amount(self) -> Decimal:
        return q2(D(self.qty) * D(self.price))


def quote_blocks(lines: list[Line], vat: str, expected_ttc: Decimal, label: str) -> list[Any]:
    """Lines table (HT) + totals; fails if the TTC total differs from the seed amount."""
    ht = sum((line.amount for line in lines), Decimal("0"))
    tva = q2(ht * D(vat))
    expect(label, ht + tva, expected_ttc)
    table = Table(
        [
            Col("Désignation", 6.2),
            Col("Qté", 1.0, "r"),
            Col("Unité", 1.0),
            Col("P.U. HT", 1.6, "r"),
            Col("Montant HT", 1.8, "r"),
        ],
        [[ln.label, num(ln.qty), ln.unit, eur(ln.price), eur(ln.amount)] for ln in lines],
    )
    totals = Totals(
        [("Total HT", eur(ht)), (f"TVA {pct(D(vat))}", eur(tva)), ("Total TTC", eur(ht + tva))]
    )
    return [table, totals]


@dataclass(frozen=True)
class Person:
    civ: str
    last: str
    first: str
    born: str
    address: str
    phone: str

    @property
    def full(self) -> str:
        return f"{self.civ} {self.first} {self.last}"

    @property
    def formal(self) -> str:
        return f"{self.last} {self.first}"

    @property
    def born_on(self) -> str:
        return f"{'née' if self.civ == 'Mme' else 'né'} le {self.born}"

    @property
    def email(self) -> str:
        first = self.first.lower().replace("é", "e").replace("è", "e").replace("ï", "i")
        return f"{first}.{self.last.lower().replace(' ', '')}@example.fr"

    def check(self, seed_name: str) -> Person:
        """Guard against seed drift: the seed name must match this person."""
        if not seed_name.upper().startswith(self.last.upper()):
            raise ValueError(f"seed name {seed_name!r} does not match {self.formal!r}")
        return self


PREVAIQ = "PrevaIQ Assurances"
PREVAIQ_ADDRESS = "3 place des Quinconces, 33000 Bordeaux"


def prevaiq(service: str, email_user: str, phone: str = "+33 9 72 12 34 56") -> Party:
    return Party(
        PREVAIQ, service, (PREVAIQ_ADDRESS, f"Tél. {phone} · {email_user}@prevaiq.example.fr")
    )


PRV_HAB = prevaiq("Service Sinistres Habitation", "sinistres.habitation")
PRV_AUTO = prevaiq("Service Sinistres Automobile", "sinistres.auto")
PRV_SANTE = prevaiq("Service Prestations Santé", "sante", "+33 9 72 12 34 57")
PRV_PRO = prevaiq("Service Flottes & Professionnels", "sinistres.auto")
POLICE = rgb("#1F3A68")
MEDICAL = rgb("#1E6F6A")

PDF_BUILDERS: dict[tuple[str, str], Callable[[Case], DocSpec]] = {}


def pdf(
    app_id: str, filename: str
) -> Callable[[Callable[[Case], DocSpec]], Callable[[Case], DocSpec]]:
    def register(builder: Callable[[Case], DocSpec]) -> Callable[[Case], DocSpec]:
        PDF_BUILDERS[(app_id, filename)] = builder
        return builder

    return register


def declaration_blocks(
    p: Person, quality: str, contract: str, formula: str, since: str
) -> list[Any]:
    return [
        Section("Assurée" if p.civ == "Mme" else "Assuré"),
        Fields(
            [
                ("Nom et prénom", p.formal),
                ("Qualité", quality),
                ("Adresse", p.address),
                ("Date de naissance", p.born),
                ("Téléphone", p.phone),
                ("E-mail", p.email),
            ]
        ),
        Section("Contrat"),
        Fields(
            [
                ("N° de contrat", contract),
                ("Formule", formula),
                ("Assuré depuis le", since),
                ("Assureur", PREVAIQ),
            ]
        ),
    ]


def sworn(place: str, day: str, p: Person) -> list[Any]:
    return [
        Para(
            "Je certifie sur l'honneur l'exactitude des renseignements ci-dessus. Toute fausse "
            "déclaration intentionnelle expose à la nullité du contrat (article L.113-8 du Code "
            "des assurances).",
            7.8,
            "i",
            MUTED,
        ),
        Signatures(
            [("Signature de l'assurée" if p.civ == "Mme" else "Signature de l'assuré", p.full)],
            f"Fait à {place}, le {day}",
        ),
    ]


# =============================================================================
# Habitation claims
# =============================================================================

GIRARD = Person(
    "M.",
    "GIRARD",
    "Laurent",
    "04/11/1971",
    "22 chemin de Ronde, 78000 Versailles",
    "+33 6 39 98 12 45",
)


@pdf("app-house-hab-001", "declaration_sinistre.pdf")
def _girard_declaration(c: Case) -> DocSpec:
    p = GIRARD.check(c.field("AssuréNom"))
    day, contract = c.field("DateDeclaration"), c.field("NumeroPolice")
    return DocSpec(
        "Déclaration de sinistre habitation",
        PRV_HAB,
        day,
        [("N° sinistre", "SIN-LG-240215-01"), ("Déclaré le", day), ("Contrat", contract)],
        [
            *declaration_blocks(
                p,
                "Propriétaire occupant",
                contract,
                "Multirisque Habitation — Formule Confort",
                "01/09/2016",
            ),
            Section("Le sinistre"),
            Fields(
                [
                    ("Nature", c.field("NatureSinistre")),
                    ("Date et heure", f"{c.field('DateSinistre')} vers 14h30"),
                    ("Lieu", c.field("LieuSinistre")),
                    ("Bien concerné", "Maison individuelle (1934), 2 niveaux, 145 m²"),
                    ("Première déclaration", "Par téléphone le 13/02/2024 à 09h00"),
                    ("Visite de l'expert", "13/02/2024 à 14h00"),
                ]
            ),
            Section("Circonstances"),
            Para(
                "Le 12/02/2024 vers 14h30, pendant la tempête qui a touché les Yvelines (rafales "
                "supérieures à 100 km/h), une partie de la toiture a été arrachée sur le versant "
                "nord : des tuiles ont été projetées dans le jardin et le faîtage s'est "
                "partiellement descellé. Vers 18h00, de l'eau s'est infiltrée par le plafond du "
                "salon. J'ai posé une bâche en urgence le soir même et déplacé le mobilier du salon."
            ),
            Section("Dommages constatés"),
            Table(
                [Col("Élément", 2.2), Col("Description", 5.6), Col("Étendue", 1.6, "r")],
                [
                    [
                        "Toiture",
                        "Tuiles mécaniques arrachées ou cassées, faîtage descellé",
                        "env. 6 m²",
                    ],
                    ["Écran sous-toiture", "Déchiré au droit de l'arrachement", "env. 8 m²"],
                    [
                        "Plafond du salon",
                        "Auréoles et plâtre détrempé sous l'infiltration",
                        "env. 4 m²",
                    ],
                    ["Peintures du salon", "Coulures et taches sur deux murs", "env. 38 m²"],
                ],
            ),
            Fields(
                [
                    ("Montant estimé", "À chiffrer par l'expert"),
                    ("Tiers impliqué", "Aucun (événement climatique)"),
                ]
            ),
            Section("Mesures conservatoires"),
            Bullets(
                [
                    "Bâchage provisoire de la toiture le 12/02/2024 au soir.",
                    "Mise à l'abri du mobilier du salon, aération et séchage de la pièce.",
                ]
            ),
            Section("Pièces jointes"),
            Bullets(
                [
                    "Certificat d'intempérie du 14/02/2024 (tempête du 12/02/2024).",
                    "Photographies : photo_toiture.jpg, photo_tuiles_endommagees.jpg.",
                ]
            ),
            *sworn("Versailles", day, p),
        ],
        subtitle="Événement climatique — tempête",
    )


@pdf("app-house-hab-001", "attestation_tempete.pdf")
def _girard_weather(c: Case) -> DocSpec:
    GIRARD.check(c.field("AssuréNom"))
    issuer = company(
        "Observatoire Climatique de l'Ouest Francilien",
        "Certificats d'intempéries et données d'observation météorologique",
        "14 avenue de Sceaux, 78000 Versailles",
        "+33 1 99 00 41 27",
        "certificats@ocof.example.fr",
        "#2B6CB0",
    )
    hours = [
        ("12h", 48, 74, "SO", "1,2"),
        ("13h", 55, 88, "SO", "2,4"),
        ("14h", 66, 108, "OSO", "3,8"),
        ("15h", 61, 97, "O", "2,9"),
        ("16h", 57, 91, "O", "1,6"),
        ("17h", 50, 83, "ONO", "1,1"),
        ("18h", 44, 76, "ONO", "0,6"),
        ("19h", 37, 64, "NO", "0,3"),
        ("20h", 31, 55, "NO", "0,1"),
    ]
    return DocSpec(
        "Certificat d'intempérie",
        issuer,
        "14/02/2024",
        [
            ("N° certificat", "CERT-78-2024-0457"),
            ("Délivré le", "14/02/2024"),
            ("Demandeur", GIRARD.full),
        ],
        [
            Section("Objet"),
            Para(
                f"À la demande de {GIRARD.full}, {GIRARD.address}, nous certifions les conditions "
                f"météorologiques observées le {c.field('DateSinistre')} sur la commune de "
                "Versailles (78), d'après les relevés de la station de référence la plus proche "
                "(3,2 km) et l'analyse des champs de vent."
            ),
            Section(f"Relevés horaires du {c.field('DateSinistre')}"),
            Table(
                [
                    Col("Heure", 1.2),
                    Col("Vent moyen (km/h)", 2, "r"),
                    Col("Rafale max. (km/h)", 2, "r"),
                    Col("Direction", 1.5, "c"),
                    Col("Pluie (mm)", 1.6, "r"),
                ],
                [[h, str(m), str(g), d, r] for h, m, g, d, r in hours],
                footer=[["Max. / cumul", "66", "108 (14h20)", "—", "14,0"]],
            ),
            Fields(
                [
                    (
                        "Vigilance",
                        "Orange « vents violents » sur les Yvelines du 12/02/2024 10h00 "
                        "au 13/02/2024 06h00",
                    ),
                    ("Rafale maximale", "108 km/h à 14h20"),
                    ("Rafales > 100 km/h", "De 13h40 à 16h30"),
                    ("Seuil usuel « tempête »", "100 km/h"),
                ]
            ),
            Note(
                "Conclusion",
                "Les rafales relevées le 12/02/2024 ont dépassé 100 km/h entre 13h40 et "
                "16h30, avec un maximum de 108 km/h à 14h20. Ces valeurs caractérisent un épisode "
                "de tempête au sens habituel des contrats d'assurance habitation.",
            ),
            Para(
                "Certificat établi pour servir et valoir ce que de droit. Valeurs issues de mesures "
                "automatiques validées ; elles peuvent différer localement selon l'exposition du "
                "site.",
                7.8,
                "i",
                MUTED,
            ),
            Signatures(
                [("Le responsable des certificats", "Nadia FERRAND")], "Versailles, le 14/02/2024"
            ),
        ],
        subtitle=f"Épisode de vent violent du {c.field('DateSinistre')} — commune de Versailles (78)",
    )


@pdf("app-house-hab-001", "rapport_expert.pdf")
def _girard_expert(c: Case) -> DocSpec:
    GIRARD.check(c.field("AssuréNom"))
    cover = c.parsed("responsibility_evaluation", "coverage_determination")
    deductible = parse_money(cover["franchise"].split("€")[0])
    items = [
        (
            "Couverture",
            "Remplacement d'environ 60 tuiles mécaniques, reprise du faîtage scellé (4 ml)",
            "3450",
        ),
        ("Écran sous-toiture", "Remplacement local de l'écran (8 m²)", "780"),
        ("Mise hors d'eau", "Bâchage d'urgence et sécurisation", "450"),
        ("Plafond du salon", "Dépose et reprise du plâtre (4 m²), traitement", "1520"),
        ("Peintures du salon", "Plafond et murs (38 m²), deux couches", "1600"),
        ("Nettoyage et séchage", "Séchage contrôlé, nettoyage", "700"),
    ]
    total = sum((D(a) for _, _, a in items), Decimal("0"))
    expect(f"{c.id} rapport_expert", total, c.money("MontantEstime"))
    issuer = company(
        "Cabinet Roche Expertise Bâtiment",
        "Expertise IARD — dommages aux biens",
        "9 rue de la Paroisse, 78000 Versailles",
        "+33 1 99 00 58 63",
        "contact@roche-expertise.example.fr",
        "#4B3F72",
    )
    return DocSpec(
        "Rapport d'expertise — sinistre tempête",
        issuer,
        "14/02/2024",
        [
            ("Réf. expert", "RE-2024-0213-78"),
            ("Sinistre", "SIN-LG-240215-01"),
            ("Date du rapport", "14/02/2024"),
        ],
        [
            Section("Mission"),
            Fields(
                [
                    ("Mandant", f"{PREVAIQ} — Service Sinistres Habitation"),
                    ("Contrat", c.field("NumeroPolice")),
                    ("Assuré", GIRARD.full),
                    ("Lieu", c.field("LieuSinistre")),
                    ("Visite", f"{c.field('DateConstat')} à 14h00, en présence de l'assuré"),
                    ("Expert", "Hélène MARCHAND, expert IARD"),
                ]
            ),
            Section("Constatations"),
            Para(
                "Maison individuelle de 1934 couverte en tuiles mécaniques de terre cuite. Sur le "
                "versant nord, environ 60 tuiles sont arrachées, déplacées ou cassées et le faîtage "
                "est descellé sur 4 ml ; l'écran sous-toiture est déchiré sur environ 8 m². Une bâche "
                "provisoire a été posée par l'assuré. Au rez-de-chaussée, le plafond du salon "
                "présente des auréoles et un plâtre détrempé sur environ 4 m², avec coulures sur deux "
                "murs. Aucun défaut d'entretien de la couverture n'a été relevé."
            ),
            Section("Chronologie"),
            Table(
                [Col("Date", 1.9), Col("Événement", 5), Col("Source", 2.4)],
                [
                    [f"{e['date']}", e["event"], e["source"].replace("_", " ")]
                    for e in c.parsed("timeline", "event_sequence")
                ],
            ),
            Section("Cause et garantie"),
            Para(
                f"Les dommages résultent de l'action directe du vent lors de la tempête du "
                f"{c.field('DateSinistre')} (rafales supérieures à 100 km/h, certificat "
                f"d'intempérie joint). Garantie acquise : {cover['applicable_clauses'][0]} "
                f"(clause {cover['policy_id']}) ; {cover['applicable_clauses'][1]}."
            ),
            Section("Évaluation des dommages"),
            Table(
                [Col("Poste", 2.3), Col("Nature des travaux", 5.4), Col("Montant TTC", 1.8, "r")],
                [[p, d, eur(a)] for p, d, a in items],
            ),
            Totals(
                [
                    ("Montant des dommages TTC", eur(total)),
                    ("Vétusté (valeur à neuf)", eur(0)),
                    ("Franchise contractuelle", eur(-deductible)),
                    ("Indemnité proposée", eur(total - deductible)),
                ]
            ),
            Note(
                "Conclusion",
                f"Sinistre garanti. Dommages évalués à {eur(total)} TTC, franchise de "
                f"{eur(deductible)} à déduire. Chiffrage accepté par l'assuré.",
                "ok",
            ),
            Signatures([("L'expert", "Hélène MARCHAND")], "Versailles, le 14/02/2024"),
        ],
    )


LEROY = Person(
    "M.",
    "LEROY",
    "Jean-Marc",
    "22/01/1964",
    "17 rue de la Liberté, 21000 Dijon (3e étage, porte droite)",
    "+33 6 39 98 21 07",
)
MOREL_RENOVATION = company(
    "Entreprise Morel",
    "Rénovation intérieure — sols, plâtrerie, peinture",
    "8 rue des Ateliers, 21000 Dijon",
    "+33 3 53 01 26 48",
    "contact@morel-renovation.example.fr",
    "#5A4632",
)


@pdf("app-hab-002", "declaration_dde.pdf")
def _leroy_declaration(c: Case) -> DocSpec:
    p = LEROY.check(c.field("NomAssure"))
    day, contract = c.field("DateDeclaration"), c.field("NumeroContrat")
    return DocSpec(
        "Déclaration de sinistre — dégât des eaux",
        PRV_HAB,
        day,
        [("N° sinistre", "SIN-JL-250418-01"), ("Déclaré le", day), ("Contrat", contract)],
        [
            *declaration_blocks(
                p,
                "Propriétaire occupant (T3)",
                contract,
                "Multirisque Habitation — Formule Essentielle",
                "12/03/2020",
            ),
            Section("Le sinistre"),
            Fields(
                [
                    ("Nature", c.field("NatureSinistre")),
                    ("Date et heure", f"{c.field('DateSinistre')} vers 19h15"),
                    ("Lieu", c.field("LieuSinistre")),
                    ("Urgence", c.field("NiveauUrgence")),
                ]
            ),
            Section("Circonstances"),
            Para(
                "Le 15/04/2025 vers 19h15, j'ai constaté une fuite au niveau du joint du flexible "
                "d'arrivée d'eau de la machine à laver. L'eau s'est répandue sous le parquet "
                "flottant de la cuisine et a traversé le plancher : le plafond de M. et Mme BERTIN, "
                "voisins du dessous (2e étage), est taché. J'ai coupé l'arrivée d'eau et fait "
                "intervenir un plombier en urgence le soir même. Un constat amiable dégât des eaux "
                "a été signé avec mes voisins le 16/04/2025."
            ),
            Section("Dommages constatés"),
            Table(
                [Col("Local", 3), Col("Dommage", 5), Col("Étendue", 1.5, "r")],
                [
                    ["Cuisine (3e étage)", "Parquet flottant gonflé, lames déformées", "8 m²"],
                    ["Cuisine (3e étage)", "Plinthes décollées, deux caissons bas gonflés", "6 ml"],
                    ["Logement du dessous (2e étage)", "Plafond taché par l'humidité", "3 m²"],
                ],
            ),
            Fields(
                [
                    ("Montant estimé", f"{c.field('MontantEstime')} (devis Entreprise Morel)"),
                    ("Franchise", c.field("FranchiseApplicable")),
                    ("Tiers", c.field("TiersImplique")),
                    ("Constat amiable", "Signé le 16/04/2025 avec M. et Mme BERTIN"),
                ]
            ),
            Section("Mesures conservatoires"),
            Bullets(
                [
                    "Coupure de l'arrivée d'eau le 15/04/2025 à 19h20.",
                    "Intervention d'un plombier en urgence (flexible et joint remplacés).",
                    "Bâchage du parquet et dépose des plinthes décollées pour séchage.",
                ]
            ),
            Section("Pièces jointes"),
            Bullets(
                [
                    "Constat amiable dégât des eaux du 16/04/2025 ; devis_remise_en_etat.pdf.",
                    "Photographies : photo_parquet_gonflé.jpg, photo_plafond_voisin.jpg.",
                ]
            ),
            *sworn("Dijon", day, p),
        ],
    )


@pdf("app-hab-002", "devis_remise_en_etat.pdf")
def _leroy_quote(c: Case) -> DocSpec:
    p = LEROY.check(c.field("NomAssure"))
    lines = [
        Line("Protection des lieux (cuisine, palier, logement du dessous)", "1", "forfait", "85"),
        Line(
            "Dépose du parquet flottant endommagé et des plinthes, évacuation", "8", "m²", "16.50"
        ),
        Line(
            "Contrôle d'humidité de la chape et séchage (déshumidificateur, 5 jours)",
            "1",
            "forfait",
            "210",
        ),
        Line(
            "Fourniture parquet flottant chêne 12 mm et sous-couche (chutes comprises)",
            "9",
            "m²",
            "54.90",
        ),
        Line("Pose du parquet flottant et des barres de seuil", "8", "m²", "32"),
        Line("Fourniture et pose de plinthes MDF peintes", "7", "ml", "19.80"),
        Line("Remplacement de deux caissons bas de cuisine gonflés", "2", "u", "245"),
        Line("Dépose et repose du lave-linge et de l'électroménager", "1", "forfait", "120"),
        Line(
            "Plafond du logement du dessous : lessivage, impression anti-taches, ponçage",
            "14",
            "m²",
            "21.50",
        ),
        Line(
            "Plafond du logement du dessous : peinture acrylique mate, deux couches",
            "14",
            "m²",
            "19",
        ),
        Line("Raccords de peinture des murs adjacents", "6", "m²", "24"),
        Line("Nettoyage de fin de chantier", "1", "forfait", "95"),
        Line("Fournitures diverses (colles, joints, consommables)", "1", "forfait", "177.39"),
    ]
    return DocSpec(
        "Devis n° DV-2025-0417",
        MOREL_RENOVATION,
        "17/04/2025",
        [
            ("Date", "17/04/2025"),
            ("Validité", "3 mois"),
            ("Contrat client", c.field("NumeroContrat")),
        ],
        [
            Columns(
                [
                    ("Client", [("", p.full), ("", p.address), ("", p.phone)]),
                    (
                        "Chantier",
                        [
                            (
                                "",
                                "Cuisine du 3e étage et plafond du logement du dessous "
                                "(M. et Mme BERTIN, 2e étage)",
                            ),
                            ("", "Visite technique du 16/04/2025"),
                        ],
                    ),
                ]
            ),
            Section("Détail des travaux"),
            *quote_blocks(lines, "0.10", c.money("MontantEstime"), f"{c.id} devis"),
            Para(
                "TVA au taux réduit de 10 % : travaux dans un logement achevé depuis plus de deux "
                "ans. Acompte de 30 % à la commande, solde à la réception. Intervention sous deux "
                "semaines après accord.",
                7.8,
                "i",
                MUTED,
            ),
            Signatures(
                [("Bon pour accord — le client", ""), ("L'entreprise", "Pascal MOREL")],
                "Dijon, le 17/04/2025",
            ),
        ],
        subtitle="Remise en état après dégât des eaux — 17 rue de la Liberté, 21000 Dijon",
    )


LAMBERT = Person(
    "M.",
    "LAMBERT",
    "Sébastien",
    "14/03/1989",
    "23 allée des Violettes, 31400 Toulouse (bâtiment B, 1er étage)",
    "+33 6 39 98 33 61",
)
POLICE_TOULOUSE = Party(
    "Police nationale",
    "Commissariat central de Toulouse — accueil des plaintes",
    ("Toulouse (31)", "Tél. +33 5 36 49 17 00"),
    POLICE,
)


def _lambert_items(c: Case) -> list[tuple[str, str, Decimal]]:
    items = [
        ("Téléviseur écran plat 65 pouces", "Facture à fournir", D(1200)),
        ("Ordinateur portable 14 pouces (2024)", "Facture à fournir", D(2500)),
        ("Bijoux (bague, collier, montre)", "Aucun — ni facture ni photo", D(8000)),
        ("Numéraire", "—", D(500)),
    ]
    expect(f"{c.id} objets", sum((v for *_, v in items), Decimal("0")), c.money("MontantEstime"))
    return items


@pdf("app-hab-003", "declaration_vol.pdf")
def _lambert_declaration(c: Case) -> DocSpec:
    p = LAMBERT.check(c.field("NomAssure"))
    day, contract = c.field("DateDeclaration"), c.field("NumeroContrat")
    items = _lambert_items(c)
    total = sum((v for *_, v in items), Decimal("0"))
    return DocSpec(
        "Déclaration de sinistre — vol / cambriolage",
        PRV_HAB,
        day,
        [("N° sinistre", "SIN-SL-250702-01"), ("Déclaré le", day), ("Contrat", contract)],
        [
            *declaration_blocks(
                p,
                "Locataire (appartement T2)",
                contract,
                "Multirisque Habitation — Formule Confort",
                "01/02/2023",
            ),
            Section("Le sinistre"),
            Fields(
                [
                    ("Nature", "Vol / cambriolage"),
                    ("Date", f"{c.field('DateSinistre')}, entre 08h15 et 19h40"),
                    ("Lieu", c.field("LieuSinistre")),
                    ("Mode d'entrée", "Non déterminé"),
                    ("Plainte", "Déposée le 01/07/2025 — commissariat central de Toulouse"),
                    ("Témoins", "Aucun"),
                ]
            ),
            Section("Circonstances (déclaration de l'assuré)"),
            Para(
                "Je suis parti travailler le 30/06/2025 à 08h15 en fermant la porte à clé. À mon "
                "retour vers 19h40, la porte était fermée et ne présentait aucune trace "
                "d'effraction. J'ai constaté la disparition du téléviseur du salon, de mon "
                "ordinateur portable, de bijoux rangés dans la chambre et d'une somme en espèces. "
                "Les fenêtres étaient fermées. Aucun voisin n'a remarqué de passage."
            ),
            Section("Objets déclarés volés"),
            Table(
                [Col("Objet", 4.2), Col("Justificatif", 3.4), Col("Valeur déclarée", 1.9, "r")],
                [[name, proof, eur(value)] for name, proof, value in items],
                footer=[["Total déclaré", "", eur(total)]],
            ),
            Section("Antécédents (24 derniers mois)"),
            Para("Vol déclaré le 15/01/2024 à la même adresse (dossier SIN-SL-240115-01)."),
            Section("Pièces jointes"),
            Bullets(
                [
                    "Récépissé de dépôt de plainte du 01/07/2025 (depot_plainte.pdf).",
                    "Photographie de la serrure de la porte d'entrée (photo_serrure_intacte.jpg).",
                ]
            ),
            *sworn("Toulouse", day, p),
        ],
    )


@pdf("app-hab-003", "depot_plainte.pdf")
def _lambert_complaint(c: Case) -> DocSpec:
    p = LAMBERT.check(c.field("NomAssure"))
    items = _lambert_items(c)
    total = sum((v for *_, v in items), Decimal("0"))
    return DocSpec(
        "Récépissé de dépôt de plainte",
        POLICE_TOULOUSE,
        "01/07/2025",
        [
            ("N° de procédure", "2025/031/004872"),
            ("Date", "01/07/2025 à 10h15"),
            ("Unité", "Accueil — plaintes"),
        ],
        [
            Section("Plaignant"),
            Fields(
                [
                    ("Nom et prénom", p.formal),
                    ("Né le", f"{p.born} à Montauban (82)"),
                    ("Adresse", p.address),
                    ("Téléphone", p.phone),
                ]
            ),
            Section("Faits déclarés"),
            Fields(
                [
                    ("Qualification", "Vol dans un local d'habitation"),
                    ("Date des faits", f"{c.field('DateSinistre')}, entre 08h15 et 19h40"),
                    ("Lieu", f"{c.field('LieuSinistre')} — domicile du plaignant"),
                    (
                        "Mode opératoire",
                        "Non déterminé : aucune trace d'effraction constatée sur "
                        "la porte ni sur les fenêtres selon le plaignant",
                    ),
                ],
                cols=1,
                label_ratio=0.22,
            ),
            Section("Déclaration recueillie"),
            Para(
                "Le plaignant déclare avoir quitté son domicile le 30/06/2025 à 08h15 après avoir "
                "fermé la porte à clé, et avoir constaté à son retour, vers 19h40, la disparition des "
                "biens listés ci-dessous. Il précise que la serrure fonctionnait normalement et n'a "
                "pas été changée. Aucun témoin n'a été identifié à ce stade."
            ),
            Section("Biens déclarés dérobés"),
            Table(
                [Col("Désignation", 6), Col("Valeur déclarée par le plaignant", 3, "r")],
                [[name, eur(value)] for name, _, value in items],
                footer=[["Total", eur(total)]],
            ),
            Note(
                "",
                "Le présent récépissé atteste du dépôt de plainte ; il ne préjuge pas des suites "
                "données à la procédure. Une copie du procès-verbal peut être demandée au service.",
            ),
            Signatures(
                [
                    ("Le plaignant", "Sébastien LAMBERT"),
                    ("L'agent de police judiciaire", "Brigadier-chef T. DELORME"),
                ],
                "Toulouse, le 01/07/2025",
            ),
        ],
        subtitle="Article 15-3 du Code de procédure pénale",
    )


LECOMTE = Person(
    "Mme",
    "LECOMTE",
    "Sandrine",
    "09/07/1978",
    "10 chemin de Falgarde, 81000 Albi",
    "+33 6 39 98 40 18",
)
MONDEAL = company(
    "Cabinet Mondéal",
    "Expertise après sinistres — IARD et automobile",
    "26 allées Jean-Jaurès, 31000 Toulouse",
    "+33 5 36 49 62 15",
    "expertises@mondeal.example.fr",
    "#4B3F72",
)


@pdf("app-hab-004", "declaration_inondation.pdf")
def _lecomte_declaration(c: Case) -> DocSpec:
    p = LECOMTE.check(c.field("NomAssure"))
    day, contract = c.field("DateDeclaration"), c.field("NumeroContrat")
    return DocSpec(
        "Déclaration de sinistre — inondation",
        PRV_HAB,
        day,
        [("N° sinistre", "SIN-SL-251030-01"), ("Déclaré le", day), ("Contrat", contract)],
        [
            *declaration_blocks(
                p,
                "Propriétaire occupante (maison individuelle)",
                contract,
                "Multirisque Habitation — Formule Confort",
                "05/06/2020",
            ),
            Section("Le sinistre"),
            Fields(
                [
                    ("Nature", "Inondation consécutive à de fortes pluies"),
                    ("Date", f"{c.field('DateSinistre')}, montée des eaux vers 22h00"),
                    ("Lieu", c.field("LieuSinistre")),
                    ("Hauteur d'eau", "Environ 60 cm dans la cave"),
                    (
                        "Catastrophe naturelle",
                        "Demande de reconnaissance déposée par la mairie "
                        "d'Albi — arrêté en attente",
                    ),
                    ("Urgence", c.field("NiveauUrgence")),
                ]
            ),
            Section("Circonstances"),
            Para(
                "Le 28/10/2025, à la suite de pluies torrentielles sur l'Albigeois, l'eau a envahi "
                "la cave vers 22h00 et a atteint environ 60 cm. Le mobilier stocké, les vélos et "
                "l'électroménager ont été immergés. Les murs du rez-de-chaussée présentent depuis "
                "des remontées d'humidité jusqu'à environ 1,20 m de hauteur."
            ),
            Section("Dommages constatés"),
            Table(
                [
                    Col("Local", 2),
                    Col("Biens et éléments endommagés", 6.2),
                    Col("Nombre", 1.3, "r"),
                ],
                [
                    [
                        "Cave",
                        "Congélateur, lave-linge, trois vélos, étagères, buffet et chaises, cartons "
                        "d'effets personnels, outillage",
                        "8",
                    ],
                    [
                        "Rez-de-chaussée",
                        "Enduits et peintures des murs (remontées sur 1,20 m), plinthes, "
                        "séchage, nettoyage",
                        "4",
                    ],
                ],
                footer=[
                    [
                        "Total",
                        "Biens et éléments endommagés",
                        c.field("NombreItemsEndommages").split()[0],
                    ]
                ],
            ),
            Fields(
                [
                    (
                        "Estimation provisoire",
                        f"{c.field('MontantEstime')} (à confirmer par l'expert)",
                    ),
                    (
                        "Franchise",
                        "Franchise légale catastrophe naturelle (380,00 €) si l'arrêté est publié",
                    ),
                ]
            ),
            Section("Mesures conservatoires"),
            Bullets(
                [
                    "Pompage de la cave le 29/10/2025.",
                    "Location de deux déshumidificateurs depuis le 29/10/2025.",
                    "Déplacement à l'étage du mobilier non atteint.",
                ]
            ),
            Section("Pièces jointes"),
            Bullets(
                [
                    "Photographies : photo_cave_inondee.jpg, photo_murs_rdc.jpg.",
                    "Liste détaillée des biens endommagés.",
                ]
            ),
            *sworn("Albi", day, p),
        ],
    )


@pdf("app-hab-004", "rapport_expert.pdf")
def _lecomte_expert(c: Case) -> DocSpec:
    p = LECOMTE.check(c.field("NomAssure"))
    overview = c.parsed("claim_summary", "overview")
    items = [
        ("Congélateur coffre 300 L", "Cave", "450"),
        ("Lave-linge", "Cave", "520"),
        ("Deux vélos adultes", "Cave", "900"),
        ("Vélo enfant", "Cave", "180"),
        ("Étagères métalliques de rangement (3)", "Cave", "240"),
        ("Buffet et chaises entreposés", "Cave", "380"),
        ("Cartons d'effets personnels et linge", "Cave", "300"),
        ("Outillage électroportatif", "Cave", "420"),
        ("Pompage, nettoyage et désinfection de la cave", "Cave", "750"),
        ("Séchage des murs (déshumidification 21 jours)", "Rez-de-chaussée", "780"),
        ("Reprise des enduits et peintures (45 m²)", "Rez-de-chaussée", "2250"),
        ("Remplacement des plinthes (22 ml)", "Rez-de-chaussée", "330"),
    ]
    total = sum((D(a) for *_, a in items), Decimal("0"))
    deductible = D(overview["franchise_catnat"])
    expect(f"{c.id} dommages", total, c.money("MontantEstime"))
    expect(f"{c.id} indemnité", total - deductible, D(overview["net_claim"]))
    report = c.field("ExpertNom").split("Rapport ")[-1]
    return DocSpec(
        "Rapport d'expertise — inondation (catastrophe naturelle)",
        MONDEAL,
        "26/11/2025",
        [("Rapport", report), ("Date", "26/11/2025"), ("Contrat", c.field("NumeroContrat"))],
        [
            Section("Mission"),
            Fields(
                [
                    ("Mandant", f"{PREVAIQ} — Service Sinistres Habitation"),
                    ("Assurée", p.full),
                    ("Lieu", c.field("LieuSinistre")),
                    ("Date du sinistre", c.field("DateSinistre")),
                    ("Visite", "05/11/2025, contradictoire"),
                    ("Expert", "Julien CASTAN, expert IARD"),
                ]
            ),
            Section("Constatations"),
            Para(
                "Maison individuelle de plain-pied sur cave. Laisse d'eau relevée à 0,60 m dans la "
                "cave : les biens entreposés ont été immergés (congélateur, lave-linge, vélos, "
                "mobilier, cartons, outillage). Au rez-de-chaussée, remontées capillaires jusqu'à "
                "1,20 m avec cloquage des peintures et plinthes gonflées. Pompage et "
                "déshumidification réalisés par l'assurée dès le 29/10/2025."
            ),
            Section("Cadre de garantie"),
            Para(
                "L'arrêté interministériel du 15/11/2025, publié au Journal officiel, reconnaît "
                "l'état de catastrophe naturelle pour les inondations du 28/10/2025 sur la commune "
                "d'Albi. Garantie catastrophes naturelles acquise (articles L.125-1 et suivants du "
                "Code des assurances) ; franchise légale de 380,00 €."
            ),
            Section("Biens endommagés et chiffrage"),
            Table(
                [
                    Col("N°", 0.6),
                    Col("Bien / poste", 5.4),
                    Col("Localisation", 2.2),
                    Col("Montant retenu", 1.9, "r"),
                ],
                [[str(i), name, where, eur(a)] for i, (name, where, a) in enumerate(items, 1)],
            ),
            Totals(
                [
                    ("Dommages retenus", eur(total)),
                    ("Franchise légale cat-nat", eur(-deductible)),
                    ("Indemnité", eur(total - deductible)),
                ]
            ),
            Note(
                "Conclusion",
                f"Dommages confirmés à hauteur de {eur(total)} pour 12 biens ; "
                f"indemnité nette de {eur(total - deductible)} après franchise légale.",
                "ok",
            ),
            Signatures([("L'expert", "Julien CASTAN")], "Toulouse, le 26/11/2025"),
        ],
    )


SCHMITT = Person(
    "M.", "SCHMITT", "Éric", "30/05/1975", "6 rue du Vignoble, 68000 Colmar", "+33 6 39 98 52 90"
)
HAAS = company(
    "Haas Couverture",
    "Couverture — zinguerie — fenêtres de toit",
    "12 rue des Artisans, 68000 Colmar",
    "+33 3 53 01 74 22",
    "contact@haas-couverture.example.fr",
    "#7A3E1D",
)


@pdf("app-hab-005", "declaration_grele.pdf")
def _schmitt_declaration(c: Case) -> DocSpec:
    p = SCHMITT.check(c.field("NomAssure"))
    day, contract = c.field("DateDeclaration"), c.field("NumeroContrat")
    return DocSpec(
        "Déclaration de sinistre — grêle",
        PRV_HAB,
        day,
        [("N° sinistre", "SIN-ES-250620-01"), ("Déclaré le", day), ("Contrat", contract)],
        [
            *declaration_blocks(
                p,
                "Propriétaire occupant (maison individuelle)",
                contract,
                "Multirisque Habitation — Formule Confort",
                "15/04/2019",
            ),
            Section("Le sinistre"),
            Fields(
                [
                    ("Nature", c.field("NatureSinistre")),
                    ("Date et heure", f"{c.field('DateSinistre')} vers 17h30"),
                    ("Lieu", c.field("LieuSinistre")),
                    (
                        "Conditions météo",
                        "Grêlons de 2 à 3 cm, rafales à 80 km/h (station de Colmar)",
                    ),
                    ("Urgence", c.field("NiveauUrgence")),
                    ("Éléments touchés", c.field("NombreItemsEndommages")),
                ]
            ),
            Section("Circonstances"),
            Para(
                "Le 18/06/2025 vers 17h30, un violent orage de grêle s'est abattu sur Colmar pendant "
                "une vingtaine de minutes. Des tuiles ont été cassées sur le versant sud, la gouttière "
                "en zinc a été enfoncée et la vitre de la fenêtre de toit de la chambre s'est "
                "fissurée : l'eau s'infiltre dans la chambre à chaque averse."
            ),
            Section("Dommages constatés"),
            Table(
                [Col("Élément", 2.4), Col("Dommage", 7)],
                [
                    ["Toiture", "15 tuiles mécaniques en terre cuite cassées"],
                    ["Zinguerie", "Gouttière zinc demi-ronde enfoncée sur 3 ml"],
                    ["Fenêtre de toit (chambre)", "Vitrage fissuré, infiltration d'eau active"],
                ],
            ),
            Fields(
                [
                    ("Montant estimé", f"{c.field('MontantEstime')} (devis Haas Couverture)"),
                    ("Franchise", c.field("FranchiseApplicable")),
                ]
            ),
            Section("Mesures conservatoires"),
            Bullets(
                [
                    "Bâchage provisoire de la toiture le 19/06/2025.",
                    "Seau sous la fenêtre de toit et protection du parquet de la chambre.",
                ]
            ),
            Section("Pièces jointes"),
            Bullets(
                [
                    "Devis Haas Couverture du 19/06/2025 (devis_couvreur.pdf).",
                    "Photographies : photo_toiture_tuiles.jpg, photo_gouttiere.jpg, "
                    "photo_velux_fissure.jpg.",
                ]
            ),
            *sworn("Colmar", day, p),
        ],
    )


@pdf("app-hab-005", "devis_couvreur.pdf")
def _schmitt_quote(c: Case) -> DocSpec:
    p = SCHMITT.check(c.field("NomAssure"))
    # Seed: tuiles 1 800 €, gouttière 1 200 €, fenêtre de toit 1 100 € (TTC).
    groups = [
        (
            "Couverture",
            "1800",
            [
                Line(
                    "Installation de chantier, échelle de toit et protections",
                    "1",
                    "forfait",
                    "180",
                ),
                Line("Dépose de la bâche provisoire", "1", "forfait", "60"),
                Line(
                    "Fourniture de tuiles mécaniques terre cuite (modèle identique)",
                    "18",
                    "u",
                    "6.90",
                ),
                Line("Remplacement des tuiles cassées (main-d'œuvre)", "15", "u", "38"),
                Line("Révision et recalage des tuiles déplacées du versant", "1", "forfait", "420"),
                Line("Nettoyage des noues et évacuation des débris", "1", "forfait", "282.16"),
            ],
        ),
        (
            "Zinguerie",
            "1200",
            [
                Line("Dépose de la gouttière zinc endommagée", "3", "ml", "28"),
                Line("Fourniture et pose de gouttière zinc demi-ronde 25", "3", "ml", "148"),
                Line("Crochets, talon, naissance et soudures", "1", "forfait", "236.91"),
                Line("Location de nacelle (demi-journée)", "1", "forfait", "326"),
            ],
        ),
        (
            "Fenêtre de toit de la chambre",
            "1100",
            [
                Line("Remplacement du vitrage feuilleté (78 × 118 cm)", "1", "u", "780"),
                Line(
                    "Reprise de l'étanchéité du raccord et de l'habillage intérieur",
                    "1",
                    "forfait",
                    "220",
                ),
            ],
        ),
    ]
    blocks: list[Any] = [
        Columns(
            [
                ("Client", [("", p.full), ("", p.address), ("", p.phone)]),
                (
                    "Chantier",
                    [
                        ("", "Toiture, gouttière et fenêtre de toit de la chambre"),
                        ("", f"Contrat {PREVAIQ} {c.field('NumeroContrat')}"),
                    ],
                ),
            ]
        ),
    ]
    recap = []
    for title, ttc, lines in groups:
        ht = sum((line.amount for line in lines), Decimal("0"))
        expect(f"{c.id} {title}", ht + q2(ht * D("0.10")), D(ttc))
        recap.append((title, ht))
        blocks += [
            Section(title),
            Table(
                [
                    Col("Désignation", 6.2),
                    Col("Qté", 1.0, "r"),
                    Col("Unité", 1.0),
                    Col("P.U. HT", 1.6, "r"),
                    Col("Montant HT", 1.8, "r"),
                ],
                [[ln.label, num(ln.qty), ln.unit, eur(ln.price), eur(ln.amount)] for ln in lines],
                footer=[[f"Sous-total HT (soit {eur(ttc)} TTC)", "", "", "", eur(ht)]],
            ),
        ]
    total_ht = sum((ht for _, ht in recap), Decimal("0"))
    vat = q2(total_ht * D("0.10"))
    expect(f"{c.id} devis", total_ht + vat, c.money("MontantEstime"))
    blocks += [
        Totals(
            [
                ("Total HT", eur(total_ht)),
                ("TVA 10 %", eur(vat)),
                ("Total TTC", eur(total_ht + vat)),
            ]
        ),
        Signatures(
            [("Bon pour accord — le client", ""), ("L'entreprise", "Mathieu HAAS")],
            "Colmar, le 19/06/2025",
        ),
    ]
    return DocSpec(
        "Devis n° 2025-0619-HC",
        HAAS,
        "19/06/2025",
        [("Date", "19/06/2025"), ("Validité", "2 mois"), ("Client", p.full)],
        blocks,
        subtitle=f"Réparation des dommages de grêle du {c.field('DateSinistre')} — {p.address}",
    )


MARTIN_C = Person(
    "Mme",
    "MARTIN",
    "Claire",
    "16/12/1984",
    "5 place Bellecour, 69002 Lyon (2e étage)",
    "+33 6 39 98 64 27",
)


@pdf("app-hab-006", "declaration_sinistre.pdf")
def _martin_declaration(c: Case) -> DocSpec:
    p = MARTIN_C.check(c.field("NomAssure"))
    day, contract = c.field("DateDeclaration"), c.field("NumeroContrat")
    return DocSpec(
        "Déclaration de sinistre habitation",
        PRV_HAB,
        day,
        [("N° sinistre", "SIN-CM-260205-01"), ("Déclaré le", day), ("Contrat", contract)],
        [
            *declaration_blocks(
                p,
                "Propriétaire occupante (appartement)",
                contract,
                "Multirisque Habitation — Formule Confort",
                "02/04/2024",
            ),
            Section("Le sinistre"),
            Fields(
                [
                    ("Nature", c.field("NatureSinistre")),
                    ("Constaté le", c.field("DateSinistre")),
                    ("Lieu", c.field("LieuSinistre")),
                    ("Urgence", c.field("NiveauUrgence")),
                ]
            ),
            Section("Circonstances"),
            Para(
                "Des travaux de terrassement ont débuté le 12/01/2026 dans la cour de la propriété "
                "voisine pour la construction d'une piscine (pelle mécanique et brise-roche). De "
                "fines fissures sont apparues dans le salon vers le 20/01/2026 ; le 01/02/2026, j'ai "
                "constaté une fissure nette sur le mur porteur du salon. Elle s'est aggravée au fil "
                "des travaux voisins."
            ),
            Section("Description de la fissure"),
            Fields(
                [
                    ("Longueur", "Environ 2 m"),
                    ("Orientation", "Diagonale, environ 45°"),
                    ("Largeur", "3 à 5 mm"),
                    ("Élément", "Mur porteur du salon"),
                    ("Évolution", "Progressive depuis le début des travaux voisins"),
                    ("Témoins posés", "Deux témoins en plâtre le 02/02/2026"),
                ]
            ),
            Section("Tiers"),
            Fields(
                [
                    ("Tiers impliqué", c.field("TiersImplique")),
                    ("Propriétaire voisin", "M. Gérard VIDAL, 7 place Bellecour, 69002 Lyon"),
                    ("Entreprise de terrassement", "Terrassements Saône-Rhône (chantier piscine)"),
                    ("Montant estimé", "Non estimé — en attente du rapport d'expertise"),
                ]
            ),
            Note(
                "Demande d'expertise structurelle",
                "Le mur fissuré est un mur porteur : je "
                "sollicite une expertise structurelle en urgence et la mise en cause du voisin et "
                "de son entreprise de terrassement si leur responsabilité est établie.",
                "warn",
            ),
            Section("Pièces jointes"),
            Bullets(
                [
                    "Photographie de la fissure (photo_fissure_mur.jpg).",
                    "Photographies datées de l'évolution (20/01/2026 et 01/02/2026).",
                ]
            ),
            *sworn("Lyon", day, p),
        ],
    )


DA_SILVA = Person(
    "M.",
    "DA SILVA",
    "Carlos",
    "03/08/1992",
    "22 rue Jean Moulin, 35000 Rennes (2e étage, porte gauche)",
    "+33 6 39 98 71 55",
)
KEROUAC = Person(
    "Mme",
    "KEROUAC",
    "Annaïg",
    "11/02/1958",
    "22 rue Jean Moulin, 35000 Rennes (3e étage, porte gauche)",
    "+33 6 39 98 76 02",
)
# The seed names a real insurer for the neighbour: keep the contract number, use a fictitious name.
NEIGHBOUR_INSURER = "Mutuelle Armorine des Côtes (MAC)"


@pdf("app-hab-007", "constat_dde.pdf")
def _dasilva_water_report(c: Case) -> DocSpec:
    a = DA_SILVA.check(c.field("NomAssure"))
    b = KEROUAC.check(c.field("TiersImplique").replace("Mme ", ""))
    neighbour_contract = c.field("TiersImplique").split("n° ")[-1]
    day = c.field("DateSinistre")
    return DocSpec(
        "Constat amiable de dégât des eaux",
        PRV_HAB,
        day,
        [("Date du sinistre", day), ("Établi le", day), ("Contrat A", c.field("NumeroContrat"))],
        [
            Section("Lieu du sinistre"),
            Fields(
                [
                    ("Adresse", "22 rue Jean Moulin, 35000 Rennes"),
                    ("Immeuble", "Copropriété de 4 étages, syndic professionnel"),
                    ("Découverte", f"{day} vers 07h30"),
                    ("Nature", c.field("NatureSinistre")),
                ]
            ),
            Columns(
                [
                    (
                        "A — occupant lésé",
                        [
                            ("Nom", a.formal),
                            ("Qualité", "Locataire"),
                            ("Logement", "2e étage, porte gauche"),
                            ("Téléphone", a.phone),
                            ("Assureur", PREVAIQ),
                            ("Contrat", c.field("NumeroContrat")),
                            ("Bailleur", "SCI Les Lices, 4 place des Lices, 35000 Rennes"),
                        ],
                    ),
                    (
                        "B — occupant à l'origine",
                        [
                            ("Nom", b.formal),
                            ("Qualité", "Propriétaire occupante"),
                            ("Logement", "3e étage, porte gauche"),
                            ("Téléphone", b.phone),
                            ("Assureur", NEIGHBOUR_INSURER),
                            ("Contrat", neighbour_contract),
                        ],
                    ),
                ]
            ),
            Section("Origine de la fuite"),
            Checklist(
                [
                    (False, "Conduite ou canalisation"),
                    (False, "Joint ou robinetterie"),
                    (True, "Appareil à effet d'eau (chauffe-eau, ballon)"),
                    (False, "Débordement"),
                    (False, "Infiltration toiture / façade"),
                    (False, "Origine inconnue"),
                ],
                cols=3,
            ),
            Fields(
                [
                    ("Siège de la fuite", "Ballon d'eau chaude de l'appartement B (3e étage)"),
                    ("Fuite arrêtée", f"Oui — eau coupée chez B le {day}"),
                    (
                        "Recherche de fuite",
                        "Demandée à Plomberie Duval (intervention le 09/09/2025)",
                    ),
                    ("Mesures", c.field("MesuresConservatoires")),
                ]
            ),
            Section("Dommages"),
            Table(
                [Col("Occupant", 1.3), Col("Pièce", 1.6), Col("Nature des dommages", 6.6)],
                [
                    [
                        "A",
                        "Chambre",
                        "Peinture du plafond cloquée sur environ 6 m², tache d'humidité sur "
                        "un mur (environ 2 m²)",
                    ],
                    ["B", "Salle d'eau", "Aucun dommage apparent (sol carrelé)"],
                ],
            ),
            Para(
                "Le présent constat ne constitue pas une reconnaissance de responsabilité. Chaque "
                "occupant le transmet à son assureur dans les 5 jours ouvrés.",
                7.8,
                "i",
                MUTED,
            ),
            Signatures([("Occupant A", a.full), ("Occupant B", b.full)], f"Rennes, le {day}"),
        ],
        subtitle="Convention IRSI — à remplir par les occupants concernés",
    )


@pdf("app-hab-007", "facture_plombier.pdf")
def _dasilva_plumber(c: Case) -> DocSpec:
    p = DA_SILVA.check(c.field("NomAssure"))
    issuer = company(
        "Plomberie Duval",
        "Plomberie — chauffage — recherche de fuite",
        "31 rue de Lorient, 35000 Rennes",
        "+33 2 61 91 38 70",
        "contact@plomberie-duval.example.fr",
        "#2F5F8A",
    )
    lines = [
        Line("Déplacement (zone Rennes)", "1", "forfait", "30"),
        Line(
            "Recherche de fuite non destructive (humidimètre, caméra thermique) dans les "
            "logements du 2e et du 3e étage",
            "1.5",
            "h",
            "68",
        ),
        Line(
            "Fermeture et sécurisation de l'alimentation du ballon (logement du 3e)",
            "1",
            "forfait",
            "18",
        ),
        Line("Rapport de recherche de fuite pour l'assureur", "1", "forfait", "13.64"),
    ]
    # Seed: plumber 180 € + painter 950 € = MontantEstime.
    expect(f"{c.id} total", D(180) + D(950), c.money("MontantEstime"))
    return DocSpec(
        "Facture n° F-2025-0909-12",
        issuer,
        "09/09/2025",
        [("Date", "09/09/2025"), ("Intervention", "09/09/2025"), ("Client", p.full)],
        [
            Columns(
                [
                    ("Client", [("", p.full), ("", p.address), ("", p.phone)]),
                    (
                        "Intervention",
                        [
                            ("", "Recherche de fuite — dégât des eaux du 08/09/2025"),
                            ("", "22 rue Jean Moulin, 35000 Rennes, 2e et 3e étages"),
                        ],
                    ),
                ]
            ),
            Section("Prestations"),
            *quote_blocks(lines, "0.10", D(180), f"{c.id} plombier"),
            Section("Constat"),
            Para(
                "Fuite localisée sur la soupape de sécurité et le raccord du ballon d'eau chaude de "
                "l'appartement du 3e étage (Mme KEROUAC). Humidité relevée dans le plafond de la "
                "chambre du logement du 2e étage (38 %). Aucun réseau commun en cause."
            ),
            Stamp("ACQUITTÉE — 09/09/2025"),
            Para(
                "Facture acquittée par carte bancaire le 09/09/2025. TVA au taux réduit de 10 % "
                "(logement achevé depuis plus de deux ans).",
                7.8,
                "i",
                MUTED,
            ),
        ],
    )


@pdf("app-hab-007", "devis_peintre.pdf")
def _dasilva_painter(c: Case) -> DocSpec:
    p = DA_SILVA.check(c.field("NomAssure"))
    issuer = company(
        "Ateliers Bretons",
        "Peinture — revêtements muraux — décoration",
        "9 rue de Nantes, 35000 Rennes",
        "+33 2 61 91 52 34",
        "devis@ateliers-bretons.example.fr",
        "#5A4632",
    )
    lines = [
        Line("Protection des sols et du mobilier", "1", "forfait", "45"),
        Line("Grattage des peintures cloquées, rebouchage et ponçage du plafond", "11", "m²", "14"),
        Line("Impression fixante anti-taches (plafond et mur)", "13", "m²", "8.50"),
        Line("Peinture acrylique mate du plafond, deux couches", "11", "m²", "18"),
        Line("Peinture velours du mur taché (pan complet), deux couches", "9", "m²", "17"),
        Line("Nettoyage et évacuation des déchets", "1", "forfait", "60"),
        Line("Fournitures (enduits, peintures, consommables)", "1", "forfait", "143.14"),
    ]
    return DocSpec(
        "Devis n° D-2025-0910-AB",
        issuer,
        "10/09/2025",
        [("Date", "10/09/2025"), ("Validité", "3 mois"), ("Client", p.full)],
        [
            Columns(
                [
                    ("Client", [("", p.full), ("", p.address), ("", p.phone)]),
                    (
                        "Chantier",
                        [
                            (
                                "",
                                "Chambre : plafond cloqué (6 m²) et tache d'humidité sur "
                                "un mur (2 m²)",
                            ),
                            ("", "Dégât des eaux du 08/09/2025"),
                        ],
                    ),
                ]
            ),
            Section("Détail des travaux"),
            *quote_blocks(lines, "0.10", D(950), f"{c.id} peintre"),
            Para(
                "Travaux réalisables après séchage complet du support (contrôle d'humidité inférieur "
                "à 5 %). TVA au taux réduit de 10 %.",
                7.8,
                "i",
                MUTED,
            ),
            Signatures(
                [("Bon pour accord — le client", ""), ("L'entreprise", "Loïc LE GUEN")],
                "Rennes, le 10/09/2025",
            ),
        ],
        subtitle="Remise en peinture après dégât des eaux — 22 rue Jean Moulin, 35000 Rennes",
    )


# =============================================================================
# Health claims
# =============================================================================

AM_COLOR = rgb("#2C5F8D")


def practitioner(name: str, activity: str, address: str, phone: str) -> Party:
    return Party(name, activity, (address, f"Tél. {phone} · RPPS {fake_rpps(name)}"), MEDICAL)


def establishment(name: str, activity: str, city: str, phone: str) -> Party:
    return Party(
        name,
        activity,
        (city, f"Tél. {phone} · FINESS {_fake_digits('finess:' + name, 9)}"),
        MEDICAL,
    )


def assurance_maladie(caisse: str, city: str) -> Party:
    return Party(
        "Assurance Maladie",
        f"Caisse primaire d'assurance maladie {caisse}",
        (city, "Relevé de remboursements — régime général"),
        AM_COLOR,
    )


def nir(p: Person, dept: str) -> str:
    """Social security number with the personal part masked."""
    sex = "1" if p.civ == "M." else "2"
    _, month, year = p.born.split("/")
    return f"{sex} {year[2:]} {month} {dept} XXX XXX XX"


ROUSSEAU = Person(
    "M.",
    "ROUSSEAU",
    "Marc",
    "12/09/1957",
    "8 allée des Platanes, 37300 Joué-lès-Tours",
    "+33 6 39 98 17 83",
)
CHU_TOURS = establishment(
    "CHU de Tours",
    "Service de chirurgie orthopédique et traumatologique",
    "Centre hospitalier universitaire — Tours (37)",
    "+33 2 61 91 20 45",
)
ROUSSEAU_DATES = {
    "C2+MPC": "15/05/2024",
    "ZZQM006": "22/05/2024",
    "NFKA007": "03/06/2024",
    "3682": "03/06 → 08/06/2024",
    "NZRB001": "dès le 10/06/2024",
}


def _rousseau_lines(c: Case) -> list[dict[str, Any]]:
    lines = [
        dict(line) for line in c.parsed("claim_line_evaluation", "line_item_review")["claim_lines"]
    ]
    for line in lines:
        line["when"] = ROUSSEAU_DATES[line["code"].split()[-1]]
        for key in ("billed", "allowed", "plan_pays"):
            line[key] = parse_money(line[key])
    return lines


@pdf("app-mw-hc-001", "declaration_sinistre_sante.pdf")
def _rousseau_declaration(c: Case) -> DocSpec:
    p = ROUSSEAU.check(c.field("declaration:NomAdherent"))
    day = c.field("DateDeclaration")
    coverage = c.parsed("benefits_policy", "eligibility_verification")["coverage_dates"]
    since = dt.date.fromisoformat(coverage["effective_date"]).strftime("%d/%m/%Y")
    billed, secu = c.money("facture:MontantTotal"), c.money("decompte:PartSecu")
    plan, rest = c.money("decompte:PartMutuelle"), c.money("decompte:ResteACharge")
    allowed = D(c.parsed("claim_line_evaluation", "line_item_review")["total_allowed"])
    expect(f"{c.id} décompte", secu + plan + rest, allowed)
    return DocSpec(
        "Demande de remboursement — hospitalisation",
        PRV_SANTE,
        day,
        [
            ("N° sinistre", c.field("declaration:NumeroSinistre")),
            ("Date", day),
            ("Adhérent", c.field("declaration:NumeroAdherent")),
        ],
        [
            Section("Adhérent"),
            Fields(
                [
                    ("Nom et prénom", p.formal),
                    ("N° adhérent", c.field("declaration:NumeroAdherent")),
                    ("Date de naissance", p.born),
                    ("N° de sécurité sociale", nir(p, "37")),
                    ("Adresse", p.address),
                    ("Téléphone", p.phone),
                ]
            ),
            Section("Contrat"),
            Fields(
                [
                    ("Garantie", c.field("declaration:NomContrat")),
                    ("Type", "Complémentaire santé — contrat collectif"),
                    ("N° de groupe", c.field("declaration:NumeroGroupe")),
                    ("Adhésion depuis", since),
                ]
            ),
            Section("Soins concernés"),
            Fields(
                [
                    (
                        "Nature",
                        "Hospitalisation chirurgicale programmée — prothèse totale du genou droit",
                    ),
                    ("Établissement", c.field("facture:NomEtablissement")),
                    ("Chirurgien", c.field("compte_rendu:Chirurgien")),
                    (
                        "Séjour",
                        f"du {c.field('facture:DateDebut')} au {c.field('facture:DateFin')}",
                    ),
                    (
                        "Diagnostic",
                        f"{c.field('compte_rendu:CodeDiagnostic')} — "
                        f"{c.field('compte_rendu:DescriptionDiagnostic')}",
                    ),
                    ("Rééducation", "20 séances en centre SSR (Touraine)"),
                ]
            ),
            Section("Montants"),
            Table(
                [Col("Poste", 6), Col("Montant", 2, "r")],
                [
                    ["Total facturé par l'établissement", eur(billed)],
                    ["Base de remboursement (tarifs conventionnels)", eur(allowed)],
                    ["Remboursement Sécurité sociale (70 %)", eur(secu)],
                    ["Part complémentaire demandée", eur(plan)],
                ],
                footer=[["Reste à charge de l'adhérent", eur(rest)]],
            ),
            Section("Mode de règlement"),
            Para("Tiers payant : versement de la part complémentaire directement au CHU de Tours."),
            Section("Pièces jointes"),
            Bullets(
                [
                    "Relevé de remboursements de l'Assurance Maladie (decompte_securite_sociale.pdf).",
                    "Compte rendu opératoire (compte_rendu_chirurgical.pdf).",
                    "Facture d'hospitalisation (facture_hospitalisation.pdf).",
                ]
            ),
            *sworn("Joué-lès-Tours", day, p),
        ],
        subtitle="Déclaration de sinistre santé",
    )


@pdf("app-mw-hc-001", "decompte_securite_sociale.pdf")
def _rousseau_statement(c: Case) -> DocSpec:
    p = ROUSSEAU.check(c.field("declaration:NomAdherent"))
    lines = _rousseau_lines(c)
    allowed = sum((line["allowed"] for line in lines), Decimal("0"))
    paid = [q2(line["allowed"] * D("0.70")) for line in lines]
    plan = sum((line["plan_pays"] for line in lines), Decimal("0"))
    expect(f"{c.id} part Sécu", sum(paid, Decimal("0")), c.money("decompte:PartSecu"))
    expect(f"{c.id} part mutuelle", plan, c.money("decompte:PartMutuelle"))
    return DocSpec(
        "Relevé de remboursements",
        assurance_maladie("d'Indre-et-Loire", "Tours (37)"),
        "09/07/2024",
        [
            ("Date du relevé", "09/07/2024"),
            ("N° de décompte", "37-2024-0709-118842"),
            ("Assuré", p.formal),
        ],
        [
            Fields(
                [
                    ("Assuré", p.formal),
                    ("N° de sécurité sociale", nir(p, "37")),
                    ("Bénéficiaire des soins", "L'assuré"),
                    ("Complémentaire", f"{PREVAIQ} — télétransmission Noémie"),
                ]
            ),
            Section("Détail des prestations"),
            Table(
                [
                    Col("Date", 1.8),
                    Col("Prestation", 3.6),
                    Col("Code", 1.5),
                    Col("Base de remb.", 1.6, "r"),
                    Col("Taux", 0.9, "r"),
                    Col("Remboursé", 1.6, "r"),
                    Col("Part compl.", 1.6, "r"),
                ],
                [
                    [
                        line["when"],
                        line["description"],
                        line["code"].replace("CCAM ", ""),
                        eur(line["allowed"]),
                        "70 %",
                        eur(amount),
                        eur(line["plan_pays"]),
                    ]
                    for line, amount in zip(lines, paid)
                ],
                footer=[
                    ["Total", "", "", eur(allowed), "", eur(sum(paid, Decimal("0"))), eur(plan)]
                ],
                size=7.8,
            ),
            Totals(
                [
                    ("Base de remboursement", eur(allowed)),
                    ("Remboursé par l'Assurance Maladie", eur(sum(paid, Decimal("0")))),
                    ("Part transmise à la complémentaire", eur(plan)),
                    ("Reste à charge de l'assuré", eur(c.money("decompte:ResteACharge"))),
                ]
            ),
            Para(
                "Paiement : versement direct à l'établissement (tiers payant). Les informations de "
                f"ce relevé ont été transmises à votre organisme complémentaire ({PREVAIQ})."
            ),
        ],
        subtitle="Décompte de prestations — hospitalisation et soins associés",
    )


@pdf("app-mw-hc-001", "compte_rendu_chirurgical.pdf")
def _rousseau_operation(c: Case) -> DocSpec:
    p = ROUSSEAU.check(c.field("declaration:NomAdherent"))
    surgeon = c.field("compte_rendu:Chirurgien").split(",")[0]
    procedures = [
        (
            item["valueObject"]["code"]["valueString"].replace("CCAM ", ""),
            item["valueObject"]["description"]["valueString"],
        )
        for item in c.data["extracted_fields"]["compte_rendu:ProcedureCodes"]["value"]
    ]
    when = {"NFKA007": "03/06/2024", "ZZQM006": "22/05/2024", "NZRB001": "dès le 10/06/2024"}
    diagnoses = c.parsed("clinical_case_notes", "key_diagnoses")
    return DocSpec(
        "Compte rendu opératoire",
        CHU_TOURS,
        c.field("facture:DateFin"),
        [
            ("Intervention", c.field("facture:DateDebut")),
            ("Patient", p.formal),
            ("N° de séjour", "2024-0603-4471"),
        ],
        [
            Fields(
                [
                    ("Patient", f"{p.formal}, né le {p.born} (66 ans)"),
                    ("Chirurgien", f"{surgeon} — RPPS {fake_rpps(surgeon)}"),
                    ("Anesthésie", "Générale et bloc fémoral — ASA II (Dr Claire BOUVIER)"),
                    (
                        "Hospitalisation",
                        f"du {c.field('facture:DateDebut')} au {c.field('facture:DateFin')}",
                    ),
                ]
            ),
            Section("Indication"),
            Para(
                "Gonarthrose primitive fémoro-tibiale médiale droite, stade IV de Kellgren-Lawrence "
                "à l'IRM, invalidante : périmètre de marche inférieur à 500 m, escaliers impossibles. "
                "Échec d'un traitement médical bien conduit (trois infiltrations de corticoïdes, "
                "30 séances de kinésithérapie, antalgiques de palier II). Indication de prothèse "
                "totale validée en réunion de concertation pluridisciplinaire."
            ),
            Section("Diagnostics (CIM-10)"),
            Table(
                [Col("Code", 1.2), Col("Libellé", 8)],
                [
                    [d.split(" — ")[0], d.split(" — ")[1]]
                    for d in [diagnoses["primary_diagnosis"], *diagnoses["secondary_diagnoses"]]
                ],
            ),
            Section("Actes (CCAM)"),
            Table(
                [Col("Code", 1.4), Col("Libellé", 5.6), Col("Date", 2.2)],
                [[code, label, when[code]] for code, label in procedures],
            ),
            Section("Compte rendu"),
            Para(
                "Décubitus dorsal, garrot pneumatique à la racine de la cuisse (78 min). Voie d'abord "
                "para-patellaire médiale. Arthrose tricompartimentale à prédominance fémoro-tibiale "
                "médiale. Coupes fémorale et tibiale sur ancillaire, équilibrage ligamentaire "
                "satisfaisant. Prothèse totale postéro-stabilisée cimentée à plateau fixe. Fermeture "
                "plan par plan, pansement compressif. Antibioprophylaxie par céfazoline. Durée "
                "opératoire : 1 h 35, sans incident."
            ),
            Section("Suites et sortie"),
            Para(
                "Suites simples, lever à J1 avec appui complet autorisé. Prévention "
                "thromboembolique par HBPM pendant 35 jours. Comorbidités équilibrées (HTA sous "
                "amlodipine 5 mg, diabète de type 2 sous metformine, HbA1c 6,8 %). Sortie à J5 vers "
                "un centre de soins de suite et de réadaptation pour 20 séances de rééducation. "
                "Contrôle clinique et radiographique à 6 semaines."
            ),
            Signatures([("Le chirurgien", surgeon)], f"Tours, le {c.field('facture:DateFin')}"),
        ],
        subtitle="Arthroplastie totale du genou droit",
    )


@pdf("app-mw-hc-001", "facture_hospitalisation.pdf")
def _rousseau_invoice(c: Case) -> DocSpec:
    p = ROUSSEAU.check(c.field("declaration:NomAdherent"))
    lines = _rousseau_lines(c)
    billed = sum((line["billed"] for line in lines), Decimal("0"))
    allowed = sum((line["allowed"] for line in lines), Decimal("0"))
    secu, plan = c.money("decompte:PartSecu"), c.money("decompte:PartMutuelle")
    expect(f"{c.id} facture", billed, c.money("facture:MontantTotal"))
    issuer = Party(
        "CHU de Tours",
        "Direction des finances — frais de séjour",
        (
            "Centre hospitalier universitaire — Tours (37)",
            "Tél. +33 2 61 91 20 10 · facturation@chu-tours.example.fr",
        ),
        MEDICAL,
    )
    return DocSpec(
        "Facture d'hospitalisation",
        issuer,
        "05/07/2024",
        [
            ("Facture n°", "FH-2024-0603-4471"),
            ("Émise le", "05/07/2024"),
            ("Service", c.field("facture:NomEtablissement").split(" — ")[-1]),
        ],
        [
            Columns(
                [
                    ("Patient", [("", p.full), ("", p.address), ("", f"NIR {nir(p, '37')}")]),
                    (
                        "Prise en charge",
                        [
                            ("AMO", "CPAM d'Indre-et-Loire — 70 %"),
                            ("AMC", f"{PREVAIQ} — {c.field('declaration:NomContrat')}"),
                            ("Adhérent", c.field("declaration:NumeroAdherent")),
                            ("Mode", "Tiers payant"),
                        ],
                    ),
                ]
            ),
            Fields(
                [
                    ("Établissement", c.field("facture:NomEtablissement")),
                    (
                        "Séjour",
                        f"du {c.field('facture:DateDebut')} au {c.field('facture:DateFin')} "
                        "(5 nuits)",
                    ),
                ]
            ),
            Section("Détail des prestations du parcours"),
            Table(
                [
                    Col("Date", 1.8),
                    Col("Prestation", 4),
                    Col("Code", 1.5),
                    Col("Facturé", 1.7, "r"),
                    Col("Tarif conventionnel", 1.9, "r"),
                ],
                [
                    [
                        line["when"],
                        line["description"],
                        line["code"].replace("CCAM ", ""),
                        eur(line["billed"]),
                        eur(line["allowed"]),
                    ]
                    for line in lines
                ],
                footer=[["Total", "", "", eur(billed), eur(allowed)]],
            ),
            Totals(
                [
                    ("Montant total facturé", eur(billed)),
                    ("Ajustement au tarif conventionnel", eur(allowed - billed)),
                    ("Part Assurance Maladie (70 %)", eur(-secu)),
                    (f"Part complémentaire {PREVAIQ}", eur(-plan)),
                    ("Reste dû par le patient", eur(allowed - secu - plan)),
                ],
                width=260,
            ),
            Para(
                "Facture récapitulative du séjour et des prestations associées du parcours de soins "
                "(consultations préopératoires et rééducation prescrite à la sortie).",
                7.8,
                "i",
                MUTED,
            ),
        ],
    )


PETIT = Person(
    "Mme",
    "PETIT",
    "Sophie",
    "03/04/1968",
    "14 chemin des Lauves, 13100 Aix-en-Provence",
    "+33 6 39 98 26 40",
)
DR_FAURE = practitioner(
    "Dr Hélène FAURE",
    "Ophtalmologiste — conventionnée secteur 2",
    "21 boulevard du Roi René, 13100 Aix-en-Provence",
    "+33 4 65 71 23 48",
)
# Seed: OD +2.50 / OG +2.75, addition +2.00.
PETIT_RX = [("Œil droit (OD)", "+2,50", "+2,00"), ("Œil gauche (OG)", "+2,75", "+2,00")]


@pdf("app-hc-002", "ordonnance_ophtalmo.pdf")
def _petit_prescription(c: Case) -> DocSpec:
    p = PETIT.check(c.field("beneficiaire"))
    return DocSpec(
        "Ordonnance",
        DR_FAURE,
        "15/09/2025",
        [("Date", "15/09/2025"), ("Patiente", p.full)],
        [
            Fields(
                [("Patiente", f"{p.formal}, née le {p.born} (57 ans)"), ("Adresse", p.address)],
                cols=1,
                label_ratio=0.2,
            ),
            Section("Prescription de verres correcteurs"),
            Table(
                [
                    Col("Œil", 3),
                    Col("Sphère", 1.6, "r"),
                    Col("Cylindre", 1.6, "r"),
                    Col("Axe", 1.2, "r"),
                    Col("Addition", 1.6, "r"),
                ],
                [[eye, sphere, "—", "—", add] for eye, sphere, add in PETIT_RX],
            ),
            Bullets(
                [
                    "Verres progressifs — port permanent.",
                    "Traitement antireflet recommandé.",
                    "Ordonnance valable 3 ans pour le renouvellement des verres par l'opticien.",
                ]
            ),
            Para(
                "Examen de réfraction réalisé ce jour : presbytie évolutive sur hypermétropie. Fond "
                "d'œil normal, tension oculaire normale."
            ),
            Signatures(
                [("Signature du médecin", "Dr Hélène FAURE")], "Aix-en-Provence, le 15/09/2025"
            ),
        ],
    )


@pdf("app-hc-002", "facture_opticien.pdf")
def _petit_invoice(c: Case) -> DocSpec:
    p = PETIT.check(c.field("beneficiaire"))
    summary = c.parsed("claim_summary", "overview")
    items = [
        ("Monture acétate écaille, réf. MT-2045", D(165)),
        (
            f"Verre progressif OD {PETIT_RX[0][1]} add. {PETIT_RX[0][2]} — indice 1,6, "
            "antireflet durci",
            D(160),
        ),
        (
            f"Verre progressif OG {PETIT_RX[1][1]} add. {PETIT_RX[1][2]} — indice 1,6, "
            "antireflet durci",
            D(160),
        ),
    ]
    total = sum((v for _, v in items), Decimal("0"))
    ht = q2(total / D("1.2"))
    secu, plan, rest = (
        D(summary[k]) for k in ("ss_reimbursement", "net_assureur", "patient_reste")
    )
    expect(f"{c.id} facture", total, c.money("montant_facture"))
    expect(f"{c.id} répartition", secu + plan + rest, total)
    issuer = company(
        "Optique Granet",
        "Opticien diplômé — lunetterie et lentilles",
        "18 rue Espariat, 13100 Aix-en-Provence",
        "+33 4 65 71 38 92",
        "contact@optique-granet.example.fr",
        "#1E6F6A",
    )
    return DocSpec(
        "Facture n° FA-2025-0919-031",
        issuer,
        "19/09/2025",
        [("Date", "19/09/2025"), ("Client", p.full), ("Ordonnance du", "15/09/2025")],
        [
            Columns(
                [
                    ("Client", [("", p.full), ("", p.address), ("", f"Née le {p.born}")]),
                    (
                        "Prescription",
                        [
                            ("", "Dr Hélène FAURE, ophtalmologiste — 15/09/2025"),
                            (
                                "",
                                f"OD {PETIT_RX[0][1]} / OG {PETIT_RX[1][1]}, addition "
                                f"{PETIT_RX[0][2]}",
                            ),
                        ],
                    ),
                ]
            ),
            Section("Équipement optique (classe B — prix libres)"),
            Table(
                [Col("Désignation", 7), Col("Prix TTC", 2, "r")],
                [[label, eur(value)] for label, value in items],
            ),
            Totals(
                [("Total HT", eur(ht)), ("TVA 20 %", eur(total - ht)), ("Total TTC", eur(total))]
            ),
            Section("Prise en charge estimée"),
            Table(
                [Col("Organisme", 7), Col("Montant", 2, "r")],
                [
                    ["Assurance Maladie (base LPP)", eur(secu)],
                    [f"{PREVAIQ} — PrevaIQ Santé Sérénité (forfait optique annuel)", eur(plan)],
                ],
                footer=[["Reste à charge de la cliente", eur(rest)]],
            ),
            Stamp("ACQUITTÉE — 19/09/2025"),
            Para(
                "Équipement délivré et adapté le 19/09/2025. Garantie casse de 2 ans sur les verres.",
                7.8,
                "i",
                MUTED,
            ),
        ],
    )


DUBOIS = Person(
    "M.",
    "DUBOIS",
    "Philippe",
    "22/05/1960",
    "9 rue des Orfèvres, 67000 Strasbourg",
    "+33 6 39 98 38 12",
)


def _dubois_lines() -> list[tuple[str, str, Decimal, Decimal, str, Decimal]]:
    """(prestation, détail, facturé, base de remboursement, taux, remboursé AMO)."""
    rows = [
        ("Frais de séjour — forfait GHS cardiologie", "5 nuits", "5120", "5120", "80"),
        (
            "Endoprothèse coronaire active (DES)",
            "Liste des produits et prestations",
            "690",
            "690",
            "100",
        ),
        (
            "Honoraires — angioplastie coronaire avec endoprothèse",
            "CCAM DDAF006",
            "1480",
            "1480",
            "80",
        ),
        ("Honoraires — cardiologie et anesthésie", "Dépassements inclus", "520", "200", "70"),
        ("Biologie et imagerie", "Dépassements inclus", "510", "200", "60"),
        ("Forfait journalier hospitalier", "5 × 20,00 €", "100", "0", "0"),
    ]
    return [
        (
            name,
            detail,
            D(billed),
            D(base),
            f"{rate} %" if base != "0" else "—",
            q2(D(base) * D(rate) / 100),
        )
        for name, detail, billed, base, rate in rows
    ]


@pdf("app-hc-003", "compte_rendu_hospitalisation.pdf")
def _dubois_report(c: Case) -> DocSpec:
    p = DUBOIS.check(c.field("beneficiaire"))
    issuer = establishment(
        c.field("etablissement"),
        "Service de cardiologie interventionnelle",
        "Strasbourg (67)",
        "+33 3 53 01 45 90",
    )
    return DocSpec(
        "Compte rendu d'hospitalisation",
        issuer,
        "02/11/2025",
        [
            ("Séjour", "28/10/2025 → 02/11/2025"),
            ("Patient", p.formal),
            ("N° de séjour", "CSL-2025-10-8812"),
        ],
        [
            Fields(
                [
                    ("Patient", f"{p.formal}, né le {p.born} (65 ans)"),
                    ("Cardiologue", "Dr Anne KELLER"),
                    ("Mode d'entrée", "Urgences — douleur thoracique"),
                    ("Hébergement", "Chambre particulière, 5 nuits"),
                    ("Médecin traitant", "Dr Martine HOFFMANN, Strasbourg"),
                    ("Mode de sortie", "Domicile"),
                ]
            ),
            Section("Motif d'hospitalisation"),
            Para(
                "Angor instable : douleurs thoraciques de repos récidivantes depuis 48 heures, "
                "sous-décalage du segment ST en territoire antérieur, troponine négative. "
                "Antécédents : hypertension artérielle traitée, dyslipidémie, tabagisme sevré."
            ),
            Section("Examens et actes"),
            Table(
                [Col("Date", 1.6), Col("Examen / acte", 3.6), Col("Résultat", 4.6)],
                [
                    [
                        "28/10/2025",
                        "ECG, bilan biologique",
                        "Sous-décalage ST de V2 à V4, troponine négative",
                    ],
                    [
                        "29/10/2025",
                        "Coronarographie",
                        "Sténose serrée (85 à 90 %) de l'IVA proximale, "
                        "autres artères sans lésion significative",
                    ],
                    [
                        "29/10/2025",
                        c.field("acte_ccam").replace(" — ", " : "),
                        "Angioplastie de l'IVA "
                        "avec une endoprothèse active (DES 3,0 × 18 mm), bon résultat angiographique",
                    ],
                    [
                        "30/10/2025",
                        "Échocardiographie",
                        "FEVG 58 %, pas de trouble de la cinétique",
                    ],
                ],
            ),
            Section("Évolution"),
            Para(
                "Suites simples, pas de complication au point de ponction radiale. Surveillance en "
                "soins intensifs de cardiologie pendant 24 heures puis en chambre particulière. "
                "Sortie le 02/11/2025."
            ),
            Section("Traitement de sortie"),
            Bullets(
                [
                    "Aspirine 75 mg : 1 comprimé par jour, au long cours.",
                    "Ticagrélor 90 mg : 1 comprimé matin et soir pendant 12 mois.",
                    "Atorvastatine 80 mg : 1 comprimé le soir.",
                    "Bisoprolol 2,5 mg et ramipril 2,5 mg : 1 comprimé par jour.",
                ]
            ),
            Para(
                "Suivi : réadaptation cardiaque recommandée, consultation de contrôle à 1 mois, "
                "bilan lipidique à 6 semaines."
            ),
            Signatures([("Le cardiologue", "Dr Anne KELLER")], "Strasbourg, le 02/11/2025"),
        ],
    )


@pdf("app-hc-003", "facture_clinique.pdf")
def _dubois_invoice(c: Case) -> DocSpec:
    p = DUBOIS.check(c.field("beneficiaire"))
    summary = c.parsed("claim_summary", "overview")
    lines = _dubois_lines()
    total = sum((line[2] for line in lines), Decimal("0"))
    secu = sum((line[5] for line in lines), Decimal("0"))
    room = D(summary["chambre_particuliere"])
    expect(f"{c.id} facture", total, c.money("montant_total"))
    expect(f"{c.id} reste à charge", total - secu, D(summary["complement_assureur"]))
    expect(f"{c.id} chambre", D(80) * summary["duree_sejour"], room)
    issuer = company(
        c.field("etablissement"),
        "Établissement de santé privé — admissions et facturation",
        "40 route des Romains, 67200 Strasbourg",
        "+33 3 53 01 45 00",
        "facturation@clinique-saint-louis.example.fr",
        "#1E6F6A",
        vat=False,
    )
    return DocSpec(
        "Facture de séjour n° FS-2025-11873",
        issuer,
        "03/11/2025",
        [("Date", "03/11/2025"), ("Séjour", "28/10/2025 → 02/11/2025"), ("Patient", p.formal)],
        [
            Columns(
                [
                    ("Patient", [("", p.full), ("", p.address), ("", f"NIR {nir(p, '67')}")]),
                    (
                        "Prise en charge",
                        [
                            ("AMO", "CPAM du Bas-Rhin"),
                            ("AMC", f"{PREVAIQ} — PrevaIQ Santé Plus"),
                            ("Adhérent", "PRV-SANTE-24518"),
                        ],
                    ),
                ]
            ),
            Section("Frais de séjour et honoraires"),
            Table(
                [Col("Prestation", 5.2), Col("Détail", 3), Col("Montant", 1.7, "r")],
                [[name, detail, eur(billed)] for name, detail, billed, *_ in lines],
            ),
            Totals(
                [
                    ("Total facturé", eur(total)),
                    ("Part Assurance Maladie", eur(-secu)),
                    ("Reste à charge avant complémentaire", eur(total - secu)),
                ],
                width=270,
            ),
            Section("Facture annexe FS-2025-11873-A — exigence particulière du patient"),
            Table(
                [Col("Prestation", 5.2), Col("Détail", 3), Col("Montant", 1.7, "r")],
                [["Chambre particulière", f"{summary['duree_sejour']} nuits × 80,00 €", eur(room)]],
            ),
            Para(
                "La chambre particulière n'est pas remboursée par l'Assurance Maladie ; elle peut "
                "être prise en charge par votre complémentaire santé selon vos garanties.",
                7.8,
                "i",
                MUTED,
            ),
        ],
    )


@pdf("app-hc-003", "decompte_secu.pdf")
def _dubois_statement(c: Case) -> DocSpec:
    p = DUBOIS.check(c.field("beneficiaire"))
    summary = c.parsed("claim_summary", "overview")
    lines = _dubois_lines()
    total = sum((line[2] for line in lines), Decimal("0"))
    base = sum((line[3] for line in lines), Decimal("0"))
    secu = sum((line[5] for line in lines), Decimal("0"))
    expect(f"{c.id} décompte", secu, D(summary["ss_reimbursement"]))
    return DocSpec(
        "Relevé de remboursements",
        assurance_maladie("du Bas-Rhin", "Strasbourg (67)"),
        "04/11/2025",
        [
            ("Date du relevé", "04/11/2025"),
            ("N° de décompte", "67-2025-1104-552190"),
            ("Assuré", p.formal),
        ],
        [
            Fields(
                [
                    ("Assuré", p.formal),
                    ("N° de sécurité sociale", nir(p, "67")),
                    ("Établissement", c.field("etablissement")),
                    ("Séjour", "du 28/10/2025 au 02/11/2025"),
                ]
            ),
            Section("Détail des prestations"),
            Table(
                [
                    Col("Prestation", 4.6),
                    Col("Facturé", 1.6, "r"),
                    Col("Base de remb.", 1.7, "r"),
                    Col("Taux", 1, "r"),
                    Col("Remboursé", 1.6, "r"),
                ],
                [
                    [name, eur(billed), eur(b), rate, eur(paid)]
                    for name, _, billed, b, rate, paid in lines
                ],
                footer=[["Total", eur(total), eur(base), "", eur(secu)]],
            ),
            Totals(
                [
                    ("Total facturé", eur(total)),
                    ("Remboursé par l'Assurance Maladie", eur(secu)),
                    ("Reste à charge avant complémentaire", eur(total - secu)),
                ],
                width=270,
            ),
            Note(
                "",
                f"Les informations de ce relevé ont été transmises à votre organisme "
                f"complémentaire ({PREVAIQ}). Paiement à l'établissement (tiers payant).",
            ),
        ],
        subtitle="Décompte de prestations — hospitalisation",
    )


FONTAINE = Person(
    "Mme", "FONTAINE", "Aurélie", "08/06/1993", "31 rue Duguesclin, 69006 Lyon", "+33 6 39 98 45 76"
)


@pdf("app-hc-004", "certificat_accouchement.pdf")
def _fontaine_certificate(c: Case) -> DocSpec:
    p = FONTAINE.check(c.field("beneficiaire"))
    issuer = establishment(
        c.field("etablissement"),
        "Service de gynécologie-obstétrique — salle de naissance",
        "Lyon (69)",
        "+33 4 65 71 60 12",
    )
    return DocSpec(
        "Certificat d'accouchement",
        issuer,
        "17/01/2026",
        [("Date", "17/01/2026"), ("Patiente", p.full)],
        [
            Para(
                f"Je soussignée, Marion GIRAUD, sage-femme (RPPS {fake_rpps('Marion GIRAUD')}), "
                "certifie que :"
            ),
            Fields(
                [
                    ("Patiente", f"{p.full}, née le {p.born} (32 ans)"),
                    ("Domicile", p.address),
                    ("Date d'accouchement", f"{c.field('date_accouchement')} à 04h52"),
                    ("Mode d'accouchement", "Voie basse, sans complication"),
                    ("Enfant", "Né vivant et viable, de sexe féminin, prénommé Louise"),
                    ("Mensurations", "3 280 g — 50 cm — Apgar 10/10"),
                    ("Séjour", "Du 14/01/2026 au 17/01/2026 (3 nuits)"),
                ],
                cols=1,
                label_ratio=0.25,
            ),
            Para(
                "Certificat établi à la demande de l'intéressée pour faire valoir ses droits "
                "(déclaration de naissance, prestations familiales, prime de naissance de sa "
                "complémentaire santé)."
            ),
            Signatures([("La sage-femme", "Marion GIRAUD")], "Lyon, le 17/01/2026"),
        ],
    )


@pdf("app-hc-004", "facture_maternite.pdf")
def _fontaine_invoice(c: Case) -> DocSpec:
    p = FONTAINE.check(c.field("beneficiaire"))
    summary = c.parsed("claim_summary", "overview")
    rows = [
        ("Forfait séjour maternité (accouchement voie basse, 3 nuits)", "2280", "2280"),
        ("Honoraires obstétricaux — accouchement", "620", "350"),
        ("Anesthésie péridurale", "300", "250"),
    ]
    billed = sum((D(b) for _, b, _ in rows), Decimal("0"))
    base = sum((D(x) for *_, x in rows), Decimal("0"))
    expect(f"{c.id} facture", billed, D(summary["claim_amount"]))
    expect(f"{c.id} Sécu", base, D(summary["ss_reimbursement"]))
    expect(f"{c.id} chambre", D(3 * 40), D(summary["complement_chambre"]))
    issuer = company(
        c.field("etablissement"),
        "Bureau des admissions et de la facturation",
        "Lyon (69)",
        "+33 4 65 71 60 00",
        "facturation@hfme-lyon.example.fr",
        "#1E6F6A",
        vat=False,
    )
    return DocSpec(
        "Facture de séjour — maternité",
        issuer,
        "17/01/2026",
        [
            ("Facture n°", "MAT-2026-0117-209"),
            ("Date", "17/01/2026"),
            ("Séjour", "14/01/2026 → 17/01/2026"),
        ],
        [
            Columns(
                [
                    ("Patiente", [("", p.full), ("", p.address), ("", f"NIR {nir(p, '69')}")]),
                    (
                        "Prise en charge",
                        [
                            ("AMO", "CPAM du Rhône — maternité 100 %"),
                            ("AMC", PREVAIQ),
                            ("Adhérent", "PRV-SANTE-30177"),
                        ],
                    ),
                ]
            ),
            Section(f"Accouchement du {c.field('date_accouchement')}"),
            Table(
                [
                    Col("Prestation", 5),
                    Col("Facturé", 1.6, "r"),
                    Col("Base de remb.", 1.7, "r"),
                    Col("Assurance Maladie", 1.8, "r"),
                ],
                [[name, eur(b), eur(x), eur(x)] for name, b, x in rows],
                footer=[["Total", eur(billed), eur(base), eur(base)]],
            ),
            Totals(
                [
                    ("Total facturé", eur(billed)),
                    ("Part Assurance Maladie (100 %)", eur(-base)),
                    ("Reste à charge (dépassements)", eur(billed - base)),
                ],
                width=270,
            ),
            Section("Prestation pour exigence particulière (facturée séparément)"),
            Table(
                [Col("Prestation", 5), Col("Détail", 3), Col("Montant", 1.7, "r")],
                [["Chambre individuelle", "3 nuits × 40,00 €", eur(summary["complement_chambre"])]],
            ),
            Para(
                "Les dépassements d'honoraires et la chambre individuelle peuvent être pris en charge "
                "par votre complémentaire santé selon vos garanties.",
                7.8,
                "i",
                MUTED,
            ),
        ],
    )


MOREAU = Person(
    "Mme",
    "MOREAU",
    "Isabelle",
    "17/10/1972",
    "11 rue de Lisbonne, 75008 Paris",
    "+33 6 39 98 57 03",
)


@pdf("app-hc-005", "devis_dentaire.pdf")
def _moreau_quote(c: Case) -> DocSpec:
    p = MOREAU.check(c.field("beneficiaire"))
    summary = c.parsed("claim_summary", "overview")
    dentist = practitioner(
        "Dr Nicolas BLANCHARD",
        "Chirurgien-dentiste — conventionné",
        "24 rue de la Bienfaisance, 75008 Paris",
        "+33 1 99 00 34 71",
    )
    rows = [
        ("16", "Couronne dentoportée céramo-métallique", D(650), D("107.50")),
        (
            "14-15-16",
            "Bridge 3 éléments céramo-métallique (piliers 14 et 16, intermédiaire 15)",
            D(1950),
            D(215),
        ),
    ]
    fees = sum((r[2] for r in rows), Decimal("0"))
    base = sum((r[3] for r in rows), Decimal("0"))
    amo = [q2(r[3] * D("0.70")) for r in rows]
    expect(f"{c.id} devis", fees, c.money("montant_devis"))
    expect(f"{c.id} base", base, D(summary["ss_base"]))
    expect(f"{c.id} AMO", sum(amo, Decimal("0")), D(summary["ss_reimbursement"]))
    return DocSpec(
        "Devis pour traitements et actes bucco-dentaires",
        dentist,
        "02/03/2026",
        [("Date", "02/03/2026"), ("Validité", "6 mois"), ("Patiente", p.full)],
        [
            Fields(
                [
                    ("Patiente", p.formal),
                    ("Née le", p.born),
                    ("Adresse", p.address),
                    ("N° de sécurité sociale", nir(p, "75")),
                ]
            ),
            Section("Description du traitement"),
            Para(
                "Dent 15 absente ; dent 16 délabrée sous une ancienne obturation ; dent 14 fortement "
                "restaurée (radiographie panoramique du 02/03/2026). Traitement proposé : couronne "
                "céramo-métallique sur 16 et bridge de trois éléments 14-15-16."
            ),
            Table(
                [
                    Col("Dent(s)", 1.3),
                    Col("Acte", 4.4),
                    Col("Panier", 1.4),
                    Col("Honoraires", 1.6, "r"),
                    Col("Base de remb.", 1.6, "r"),
                    Col("AMO (70 %)", 1.5, "r"),
                ],
                [
                    [tooth, act, "Tarifs libres", eur(fee), eur(b), eur(a)]
                    for (tooth, act, fee, b), a in zip(rows, amo)
                ],
                footer=[["Total", "", "", eur(fees), eur(base), eur(sum(amo, Decimal("0")))]],
            ),
            Totals(
                [
                    ("Total des honoraires", eur(fees)),
                    ("Remboursement Assurance Maladie", eur(-sum(amo, Decimal("0")))),
                    ("Reste à charge avant complémentaire", eur(fees - sum(amo, Decimal("0")))),
                ],
                width=270,
            ),
            Para(
                "Matériaux : alliage non précieux et céramique, prothèses fabriquées en France. Devis "
                "à remettre à votre complémentaire santé pour une estimation de prise en charge.",
                7.8,
                "i",
                MUTED,
            ),
            Signatures(
                [("Le praticien", "Dr Nicolas BLANCHARD"), ("Bon pour accord — la patiente", "")],
                "Paris, le 02/03/2026",
            ),
        ],
        subtitle="Actes prothétiques — devis préalable",
    )


PICARD = Person(
    "Mme",
    "PICARD",
    "Delphine",
    "25/04/1994",
    "5 rue Lesdiguières, 38000 Grenoble",
    "+33 6 39 98 62 31",
)


@pdf("app-hc-006", "facture_dentiste.pdf")
def _picard_invoice(c: Case) -> DocSpec:
    p = PICARD.check(c.field("beneficiaire"))
    summary = c.parsed("claim_summary", "overview")
    dentist = practitioner(
        "Dr Marc BOURGEOIS",
        "Chirurgien-dentiste — conventionné",
        "6 place Grenette, 38000 Grenoble",
        "+33 4 65 71 52 08",
    )
    rows = [
        ("05/11/2025", "—", "Détartrage et polissage des dents (HBJD001)", D(55), D("28.92")),
        ("12/11/2025", "36", "Restauration d'une dent par composite, 1 face", D(70), D("17.79")),
        ("12/11/2025", "46", "Restauration d'une dent par composite, 1 face", D(70), D("17.79")),
    ]
    fees = sum((r[3] for r in rows), Decimal("0"))
    base = sum((r[4] for r in rows), Decimal("0"))
    amo = q2(base * D("0.70"))
    expect(f"{c.id} facture", fees, c.money("montant_facture"))
    expect(f"{c.id} AMO", amo, D(summary["ss_reimbursement"]))
    return DocSpec(
        "Note d'honoraires n° 2025-1112-07",
        dentist,
        "12/11/2025",
        [("Date", "12/11/2025"), ("Patiente", p.full)],
        [
            Fields(
                [
                    ("Patiente", p.formal),
                    ("Née le", p.born),
                    ("Adresse", p.address),
                    ("N° de sécurité sociale", nir(p, "38")),
                ]
            ),
            Section(c.field("acte")),
            Table(
                [
                    Col("Date", 1.5),
                    Col("Dent", 0.9),
                    Col("Acte", 5),
                    Col("Honoraires", 1.6, "r"),
                    Col("Base de remb.", 1.6, "r"),
                ],
                [[day, tooth, act, eur(fee), eur(b)] for day, tooth, act, fee, b in rows],
                footer=[["Total", "", "", eur(fees), eur(base)]],
            ),
            Totals(
                [
                    ("Base de remboursement", eur(base)),
                    ("Remboursement Assurance Maladie (70 %)", eur(amo)),
                    ("Total acquitté", eur(fees)),
                ],
                width=270,
            ),
            Stamp("ACQUITTÉE — 12/11/2025"),
            Para(
                "Honoraires acquittés le 12/11/2025 par carte bancaire. Feuille de soins "
                "électronique transmise à l'Assurance Maladie.",
                7.8,
                "i",
                MUTED,
            ),
        ],
    )


LEMAIRE = Person(
    "Mme", "LEMAIRE", "Sylvie", "21/09/1969", "48 rue de la Pompe, 75016 Paris", "+33 6 39 98 79 14"
)
DR_RENAULT = practitioner(
    "Dr Olivier RENAULT",
    "Cardiologue — conventionné secteur 2",
    "52 avenue Victor-Hugo, 75016 Paris",
    "+33 1 99 00 47 85",
)


@pdf("app-hc-007", "facture_cardiologue.pdf")
def _lemaire_invoice(c: Case) -> DocSpec:
    p = LEMAIRE.check(c.field("beneficiaire"))
    fee = c.money("montant_honoraires")
    excess = D(70)  # seed: dépassement 70 €
    return DocSpec(
        "Note d'honoraires n° 2026-0106-14",
        DR_RENAULT,
        "06/01/2026",
        [("Date", "06/01/2026"), ("Patiente", p.full)],
        [
            Fields(
                [
                    ("Patiente", p.formal),
                    ("Née le", p.born),
                    ("Adresse", p.address),
                    ("N° de sécurité sociale", nir(p, "75")),
                ]
            ),
            Section("Acte"),
            Table(
                [
                    Col("Date", 1.5),
                    Col("Acte", 5.5),
                    Col("Honoraires", 1.6, "r"),
                    Col("Dont dépassement", 1.8, "r"),
                ],
                [
                    [
                        "06/01/2026",
                        "Consultation de cardiologie avec électrocardiogramme de repos",
                        eur(fee),
                        eur(excess),
                    ]
                ],
            ),
            Totals(
                [
                    ("Honoraires", eur(fee)),
                    ("Dont dépassement d'honoraires", eur(excess)),
                    ("Total acquitté", eur(fee)),
                ],
                width=270,
            ),
            Stamp("ACQUITTÉE — 06/01/2026"),
            Para(
                "Médecin conventionné secteur 2 (honoraires libres) : le dépassement d'honoraires "
                "n'est pas remboursé par l'Assurance Maladie. Feuille de soins électronique "
                "transmise.",
                7.8,
                "i",
                MUTED,
            ),
        ],
    )


@pdf("app-hc-007", "ordonnance.pdf")
def _lemaire_prescription(c: Case) -> DocSpec:
    p = LEMAIRE.check(c.field("beneficiaire"))
    return DocSpec(
        "Ordonnance",
        DR_RENAULT,
        "06/01/2026",
        [("Date", "06/01/2026"), ("Patiente", p.full)],
        [
            Fields(
                [("Patiente", f"{p.formal}, née le {p.born} (56 ans)"), ("Adresse", p.address)],
                cols=1,
                label_ratio=0.2,
            ),
            Section("Prescription"),
            Bullets(
                [
                    "Épreuve d'effort (ECG d'effort) sur bicyclette ergométrique, à réaliser dans "
                    "le mois : recherche d'ischémie myocardique devant des douleurs thoraciques "
                    "atypiques à l'effort.",
                    "Bilan biologique à jeun : exploration d'une anomalie lipidique, glycémie, "
                    "créatininémie avec estimation du DFG.",
                ],
                9,
            ),
            Para("Résultats à me transmettre ; consultation de contrôle après l'épreuve d'effort."),
            Signatures([("Signature du médecin", "Dr Olivier RENAULT")], "Paris, le 06/01/2026"),
        ],
    )


FOURNIER = Person(
    "Mme",
    "FOURNIER",
    "Camille",
    "05/09/1992",
    "17 avenue de la Marne, 33700 Mérignac",
    "+33 6 39 98 83 50",
)


@pdf("app-hc-008", "prescription_irm.pdf")
def _fournier_mri(c: Case) -> DocSpec:
    p = FOURNIER.check(c.field("beneficiaire"))
    doctor = practitioner(
        "Dr Julien MARTIN",
        "Médecine générale — médecin traitant",
        "4 place Charles-de-Gaulle, 33700 Mérignac",
        "+33 5 36 49 28 60",
    )
    center = "Centre d'Imagerie Médicale de Mérignac"
    rows = [
        ("Acte d'imagerie : IRM du genou gauche (honoraires médicaux)", D(120)),
        ("Forfait technique IRM", D(190)),
        ("Dépassement d'honoraires (secteur 2)", D(70)),
    ]
    total = sum((v for _, v in rows), Decimal("0"))
    expect(f"{c.id} devis", total, c.money("montant_devis"))
    return DocSpec(
        "Prescription d'imagerie médicale",
        doctor,
        "26/03/2026",
        [("Date", "26/03/2026"), ("Patiente", p.full)],
        [
            Fields(
                [
                    ("Patiente", f"{p.formal}, née le {p.born} (33 ans)"),
                    ("Adresse", p.address),
                    ("N° de sécurité sociale", nir(p, "33")),
                ],
                cols=1,
                label_ratio=0.25,
            ),
            Section("Examen prescrit"),
            Para("IRM du genou gauche, sans injection.", 10, "b"),
            Section("Renseignements cliniques"),
            Para(
                "Douleurs persistantes du genou gauche depuis 6 semaines, apparues après une course "
                "à pied. Douleur de l'interligne interne, épanchement modéré, pas de blocage. "
                "Radiographies standard du 12/03/2026 sans anomalie osseuse. Suspicion de lésion "
                "méniscale interne."
            ),
            Note(
                "Entente préalable",
                "Examen demandé hors parcours de soins coordonnés : demande "
                "d'entente préalable adressée avec le devis du centre d'imagerie (ci-dessous).",
            ),
            Signatures([("Le médecin", "Dr Julien MARTIN")], "Mérignac, le 26/03/2026"),
            Section(f"Devis — {center}"),
            Fields(
                [
                    ("Établissement", f"{center}, 2 avenue de l'Yser, 33700 Mérignac"),
                    ("SIRET", fake_siret(center)),
                    ("Devis n°", "IRM-2026-0327-58"),
                    ("Date", "27/03/2026"),
                ]
            ),
            Table(
                [Col("Prestation", 7), Col("Montant", 2, "r")],
                [[label, eur(value)] for label, value in rows],
                footer=[["Total", eur(total)]],
            ),
            Para(
                "Rendez-vous proposé le 08/04/2026 à 14h30, sous réserve de l'accord de prise en "
                "charge.",
                7.8,
                "i",
                MUTED,
            ),
        ],
    )


# =============================================================================
# Automotive claims
# =============================================================================


@dataclass(frozen=True)
class Vehicle:
    owner: Person
    model: str
    plate: str
    insurer: str
    contract: str
    validity: str
    impact: str
    damage: str
    remarks: str
    licence: str


def licence(p: Person, year: str) -> str:
    code = _fake_digits(f"permis:{p.formal}", 7)
    return f"Permis B n° {year[2:]}{p.last[:2].upper()}{code[:5]} délivré en {year}"


def vehicle_rows(v: Vehicle) -> list[tuple[str, str]]:
    return [
        ("Preneur", v.owner.formal),
        ("Adresse", v.owner.address),
        ("Téléphone", v.owner.phone),
        ("Véhicule", v.model),
        ("Immatriculation", v.plate),
        ("Assureur", v.insurer),
        ("N° de contrat", v.contract),
        ("Attestation", v.validity),
        ("Conducteur", f"{v.owner.formal}, {v.owner.born_on}"),
        ("Permis", v.licence),
        ("Point de choc", v.impact),
        ("Dégâts apparents", v.damage),
        ("Observations", v.remarks),
    ]


def constat(
    c: Case,
    refs: list[tuple[str, str]],
    day: str,
    when: str,
    place: str,
    witnesses: str,
    other_damage: str,
    a: Vehicle,
    b: Vehicle | None,
    marks: tuple[set[int], set[int]],
    sketch: Sketch,
    signed: str,
    extra: list[Any] | None = None,
) -> DocSpec:
    b_box = (
        vehicle_rows(b)
        if b
        else [("", "Néant — aucun autre véhicule impliqué (choc contre un obstacle fixe).")]
    )
    signatures = [("Signature du conducteur A", a.owner.full)]
    if b:
        signatures.append(("Signature du conducteur B", b.owner.full))
    return DocSpec(
        "Constat amiable d'accident automobile",
        PRV_AUTO,
        day,
        refs,
        [
            Fields(
                [
                    ("1. Date et heure", when),
                    ("2. Lieu", place),
                    ("3. Blessés même légers", "Non"),
                    ("4. Dégâts matériels autres", other_damage),
                    ("5. Témoins", witnesses),
                ]
            ),
            Columns([("Véhicule A", vehicle_rows(a)), ("Véhicule B", b_box)], label_ratio=0.36),
            Section("12. Circonstances"),
            Circumstances(*marks),
            Section("13. Croquis de l'accident", keep=185),
            sketch,
            Signatures(signatures, signed),
            *(extra or []),
        ],
        subtitle="Ne constitue pas une reconnaissance de responsabilité, mais un relevé des "
        "identités et des faits",
    )


GARCIA = Person(
    "M.", "GARCIA", "Antonio", "19/02/1983", "12 rue Bayard, 31000 Toulouse", "+33 6 39 98 90 26"
)
FABRE = Person(
    "M.",
    "FABRE",
    "Julien",
    "07/10/1990",
    "3 impasse des Lilas, 31500 Toulouse",
    "+33 6 39 98 90 41",
)
# The seed names a real insurer for the third party: same policy digits, fictitious insurer.
GARCIA_THIRD_INSURER = "Mutuelle Garonnelle Assurances"


def _garcia_vehicles(c: Case) -> tuple[Vehicle, Vehicle]:
    a = Vehicle(
        GARCIA.check(c.field("constat:NomAssure")),
        f"{c.field('constat:MarqueVehicule')} {c.field('constat:ModeleVehicule')} "
        f"({c.field('constat:AnneeVehicule')})",
        c.field("constat:Immatriculation"),
        PREVAIQ,
        c.field("constat:NumeroPolice"),
        "Du 01/03/2024 au 28/02/2025",
        "Arrière",
        "Pare-chocs arrière, hayon (coffre)",
        "J'étais arrêté au feu rouge ; le véhicule B m'a percuté à l'arrière.",
        licence(GARCIA, "2001"),
    )
    target = c.parsed("payout_recommendation", "settlement_analysis")["subrogation_target"]
    policy = "MGA-" + re.search(r"(\d{4}-\d+)$", target).group(1)
    b = Vehicle(
        FABRE,
        "Peugeot 308 (2019)",
        "EZ-318-PD",
        GARCIA_THIRD_INSURER,
        policy,
        "Du 01/06/2024 au 31/05/2025",
        "Avant",
        "Pare-chocs avant, calandre",
        "Je n'ai pas pu m'arrêter à temps.",
        licence(FABRE, "2009"),
    )
    return a, b


@pdf("app-sc-auto-001", "constat_amiable.pdf")
def _garcia_constat(c: Case) -> DocSpec:
    a, b = _garcia_vehicles(c)
    day = c.field("constat:DateSinistre")
    return constat(
        c,
        [
            ("N° de constat", "CA-2024-TLS-88214"),
            ("Sinistre", c.field("constat:NumeroSinistre")),
            ("Date de l'accident", day),
        ],
        day,
        f"{day} vers 17h45",
        "Intersection avenue Jean Jaurès / rue de Metz, 31000 Toulouse",
        "Mme Laura PONS (+33 6 39 98 11 20) ; M. Karim BENALI (+33 6 39 98 11 21)",
        "Non",
        a,
        b,
        ({1}, {8}),
        Sketch(
            "rear",
            "A est arrêté au feu rouge avenue Jean Jaurès, à l'intersection "
            "avec la rue de Metz ; B, dans la même file, le heurte à l'arrière.",
        ),
        f"Toulouse, le {day}",
    )


@pdf("app-sc-auto-001", "rapport_police.pdf")
def _garcia_police(c: Case) -> DocSpec:
    a, b = _garcia_vehicles(c)
    day = c.field("constat:DateSinistre")
    issuer = Party(
        "Police nationale",
        "Commissariat central de Toulouse — brigade des accidents",
        ("Toulouse (31)", "Tél. +33 5 36 49 17 00"),
        POLICE,
    )
    return DocSpec(
        "Rapport d'intervention — accident matériel",
        issuer,
        day,
        [
            ("N° de rapport", c.field("rapport:NumeroRapport")),
            ("Date", day),
            ("Intervention", "18h05"),
        ],
        [
            Fields(
                [
                    ("Lieu", "Intersection avenue Jean Jaurès / rue de Metz, 31000 Toulouse"),
                    ("Accident", f"{day} vers 17h45"),
                    ("Conditions", "Nuit tombante, chaussée sèche, éclairage public allumé"),
                    ("Signalisation", "Feux tricolores en fonctionnement"),
                ]
            ),
            Section("Véhicules et conducteurs"),
            Table(
                [
                    Col("", 0.5),
                    Col("Véhicule", 2.4),
                    Col("Conducteur", 2.2),
                    Col("Assureur", 3.4),
                    Col("Alcoolémie", 1.4),
                ],
                [
                    [
                        k,
                        f"{v.model} — {v.plate}",
                        v.owner.formal,
                        f"{v.insurer} ({v.contract})",
                        "Négative",
                    ]
                    for k, v in (("A", a), ("B", b))
                ],
            ),
            Section("Constatations"),
            Para(
                "Le véhicule A était à l'arrêt au feu rouge avenue Jean Jaurès, à l'intersection "
                "avec la rue de Metz. Le véhicule B, qui circulait dans la même file, l'a percuté à "
                "l'arrière. Dégâts matériels : arrière du véhicule A (pare-chocs, hayon), avant du "
                "véhicule B. Aucun blessé ; les deux véhicules restent en état de circuler."
            ),
            Section("Témoignages"),
            Bullets(
                [
                    "Mme Laura PONS : le véhicule B n'a pas freiné à temps alors que le feu était "
                    "rouge depuis plusieurs secondes.",
                    "M. Karim BENALI : confirme que le véhicule A était immobilisé au feu.",
                ]
            ),
            Note(
                "",
                "Les conducteurs ont rempli un constat amiable sur place (n° CA-2024-TLS-88214). "
                "Le conducteur du véhicule B reconnaît ne pas avoir respecté la distance de "
                "sécurité.",
            ),
            Signatures(
                [("L'officier de police judiciaire", "Lieutenant Sophie MARTY")],
                f"Toulouse, le {day}",
            ),
        ],
    )


@pdf("app-sc-auto-001", "devis_reparation.pdf")
def _garcia_quote(c: Case) -> DocSpec:
    a, _ = _garcia_vehicles(c)
    issuer = company(
        "Carrosserie Toulouse Sud",
        "Carrosserie — peinture — mécanique",
        "145 route d'Espagne, 31100 Toulouse",
        "+33 5 36 49 31 77",
        "atelier@carrosserie-toulouse-sud.example.fr",
        "#3B4A5A",
    )
    estimate = c.parsed("damage_assessment", "estimate_validation")
    lines = [
        Line("Bouclier (pare-chocs) arrière apprêté", "1", "u", "410"),
        Line("Traverse (renfort) arrière", "1", "u", "215"),
        Line("Hayon nu apprêté", "1", "u", "220"),
        Line("Kit d'agrafes et fixations", "1", "forfait", "30"),
        Line(
            "Main-d'œuvre tôlerie T2 (bouclier, traverse, hayon)",
            str(estimate["labor_hours"]),
            "h",
            "60",
        ),
        Line("Main-d'œuvre peinture", "2", "h", "60"),
        Line("Ingrédients peinture", "1", "forfait", "198.33"),
    ]
    return DocSpec(
        f"Devis de réparation n° {estimate['estimate_id']}",
        issuer,
        "18/11/2024",
        [
            ("Date", "18/11/2024"),
            ("Véhicule", a.plate),
            ("Sinistre", c.field("constat:NumeroSinistre")),
        ],
        [
            Columns(
                [
                    ("Client", [("", a.owner.full), ("", a.owner.address), ("", a.owner.phone)]),
                    (
                        "Véhicule",
                        [
                            ("", a.model),
                            ("", f"Immatriculation {a.plate}"),
                            ("", "Kilométrage : 38 450 km"),
                        ],
                    ),
                ]
            ),
            Section("Détail des réparations"),
            *quote_blocks(lines, "0.20", c.money("devis:MontantReparation"), f"{c.id} devis"),
            Para(
                "Pièces d'origine constructeur. Main-d'œuvre T2 à 60,00 € HT de l'heure. "
                "Immobilisation estimée : 3 jours. Règlement direct par l'assureur (cession de "
                "créance).",
                7.8,
                "i",
                MUTED,
            ),
            Signatures(
                [("Le réceptionnaire", "Nicolas FERRER"), ("Bon pour accord — le client", "")],
                "Toulouse, le 18/11/2024",
            ),
        ],
    )


ARNAUD = Person(
    "M.", "ARNAUD", "Thierry", "11/11/1979", "27 rue de la Hache, 54000 Nancy", "+33 6 39 98 04 62"
)
PRESTIGE = company(
    "Prestige Carrosserie Nancy",
    "Carrosserie — peinture — véhicules premium",
    "18 boulevard d'Austrasie, 54000 Nancy",
    "+33 3 53 01 88 40",
    "atelier@prestige-carrosserie.example.fr",
    "#3B4A5A",
)


def _arnaud_vehicle(c: Case) -> Vehicle:
    return Vehicle(
        ARNAUD.check(c.field("constat:NomAssure")),
        f"{c.field('constat:MarqueVehicule')} {c.field('constat:ModeleVehicule')} "
        f"({c.field('constat:AnneeVehicule')})",
        c.field("constat:Immatriculation"),
        PREVAIQ,
        c.field("constat:NumeroPolice"),
        "Du 15/01/2024 au 14/01/2025",
        "Avant",
        "Pare-chocs, calandre, capot, deux optiques, ailes avant",
        f"{c.field('constat:Circonstances')} : un chevreuil a traversé, j'ai donné un coup "
        "de volant. Véhicule remorqué.",
        licence(ARNAUD, "1998"),
    )


@pdf("app-pp-auto-001", "constat_amiable.pdf")
def _arnaud_constat(c: Case) -> DocSpec:
    a = _arnaud_vehicle(c)
    day = c.field("constat:DateSinistre")
    return constat(
        c,
        [
            ("Sinistre", c.field("constat:NumeroSinistre")),
            ("Contrat A", a.contract),
            ("Date de l'accident", day),
        ],
        "02/12/2024",
        f"{day} vers 22h40",
        "RN57, sortie sud de Nancy, sens Nancy → Épinal (54)",
        "Aucun",
        "Oui — poteau en béton en bord de chaussée",
        a,
        None,
        (set(), set()),
        Sketch(
            "obstacle",
            "A circule sur la RN57 ; un animal traverse la chaussée ; A donne un coup "
            "de volant et percute un poteau en béton sur l'accotement droit.",
        ),
        "Nancy, le 02/12/2024",
    )


@pdf("app-pp-auto-001", "devis_reparation.pdf")
def _arnaud_quote(c: Case) -> DocSpec:
    a = _arnaud_vehicle(c)
    estimate = c.parsed("damage_assessment", "estimate_validation")
    hours, rate = str(estimate["labor_hours"]), str(estimate["labor_rate_per_hour"])
    lines = [
        Line("Bouclier avant complet", "1", "u", "1180"),
        Line("Calandre", "1", "u", "420"),
        Line("Capot", "1", "u", "1350"),
        Line("Traverse avant", "1", "u", "690"),
        Line("Projecteur avant gauche LED", "1", "u", "1245"),
        Line("Projecteur avant droit LED", "1", "u", "1245"),
        Line("Aile avant gauche", "1", "u", "185"),
        Line("Aile avant droite", "1", "u", "185"),
        Line("Main-d'œuvre tôlerie et mécanique T3", hours, "h", rate),
        Line("Sous-traitance : contrôle et réglage de la géométrie", "1", "forfait", "291.67"),
        Line("Peinture et ingrédients — éléments avant", "1", "forfait", "1833.33"),
        Line(
            "Raccord peinture panneaux arrière (porte arrière gauche et custode)",
            "1",
            "forfait",
            "483.33",
        ),
    ]
    return DocSpec(
        f"Devis de réparation n° {estimate['estimate_id']}",
        PRESTIGE,
        "02/12/2024",
        [
            ("Date", "02/12/2024"),
            ("Véhicule", a.plate),
            ("Sinistre", c.field("constat:NumeroSinistre")),
        ],
        [
            Columns(
                [
                    ("Client", [("", a.owner.full), ("", a.owner.address), ("", a.owner.phone)]),
                    (
                        "Véhicule",
                        [
                            ("", a.model),
                            ("", f"Immatriculation {a.plate}"),
                            ("", "Kilométrage : 31 920 km — non roulant, remorqué le 01/12/2024"),
                        ],
                    ),
                ]
            ),
            Section("Détail des réparations"),
            *quote_blocks(lines, "0.20", c.money("devis:MontantReparation"), f"{c.id} devis"),
            Para(
                "Pièces d'origine constructeur. Immobilisation estimée : 12 jours ouvrés. Devis "
                "établi sous réserve de dommages cachés constatés au démontage.",
                7.8,
                "i",
                MUTED,
            ),
            Signatures(
                [("Le chef d'atelier", "Damien COLIN"), ("Bon pour accord — le client", "")],
                "Nancy, le 02/12/2024",
            ),
        ],
    )


@pdf("app-pp-auto-001", "facture_remorquage.pdf")
def _arnaud_towing(c: Case) -> DocSpec:
    a = _arnaud_vehicle(c)
    issuer = company(
        c.field("remorquage:Societe"),
        "Dépannage — remorquage 24 h/24",
        "5 rue de l'Industrie, 54180 Heillecourt",
        "+33 3 53 01 90 12",
        "contact@lorraine-depannage.example.fr",
        "#B45309",
    )
    lines = [
        Line(
            "Forfait dépannage-remorquage véhicule léger (majoration nuit et dimanche)",
            "1",
            "forfait",
            "175",
        ),
        Line("Kilomètres en charge", "18", "km", "3.25"),
        Line("Gardiennage", "1", "jour", "4"),
    ]
    return DocSpec(
        "Facture n° LDA-2024-1201-87",
        issuer,
        "02/12/2024",
        [("Date", "02/12/2024"), ("Intervention", "01/12/2024 à 23h15"), ("Client", a.owner.full)],
        [
            Columns(
                [
                    ("Client", [("", a.owner.full), ("", a.owner.address), ("", a.owner.phone)]),
                    (
                        "Intervention",
                        [
                            ("", f"{a.model} — {a.plate}"),
                            ("", "RN57, sortie sud de Nancy — véhicule accidenté non roulant"),
                            ("", f"Remorqué vers {PRESTIGE.name}"),
                        ],
                    ),
                ]
            ),
            Section("Prestations"),
            *quote_blocks(lines, "0.20", c.money("remorquage:Montant"), f"{c.id} remorquage"),
            Stamp("ACQUITTÉE — 02/12/2024"),
            Para("Facture acquittée par carte bancaire le 02/12/2024.", 7.8, "i", MUTED),
        ],
    )


BERNARD = Person(
    "M.", "BERNARD", "Thomas", "02/03/2001", "8 rue Garibaldi, 69006 Lyon", "+33 6 39 98 13 97"
)
ROCHE = Person(
    "Mme", "ROCHE", "Chloé", "15/09/1987", "14 cours Gambetta, 69007 Lyon", "+33 6 39 98 13 64"
)


def _bernard_vehicles(c: Case) -> tuple[Vehicle, Vehicle]:
    a = Vehicle(
        BERNARD.check(c.field("assure")),
        c.field("vehicule"),
        "FS-234-AB",
        PREVAIQ,
        "AUTO-PRV-3318460",
        "Du 01/04/2025 au 31/03/2026",
        "Avant droit",
        "Aile avant droite rayée et enfoncée (40 cm), pare-chocs avant droit déformé",
        "En sortant de la place en marche arrière, mon avant droit a accroché l'arrière "
        "gauche du véhicule B en stationnement.",
        licence(BERNARD, "2022"),
    )
    b = Vehicle(
        ROCHE,
        "Renault Twingo (2017)",
        "DX-905-RL",
        "Assurances Valtéris",
        "VAL-2017-69-40218",
        "Du 01/01/2025 au 31/12/2025",
        "Arrière gauche",
        "Aile arrière gauche rayée",
        "Mon véhicule était garé ; je suis revenue sur place.",
        licence(ROCHE, "2006"),
    )
    return a, b


@pdf("app-auto-003", "constat_amiable.pdf")
def _bernard_constat(c: Case) -> DocSpec:
    a, b = _bernard_vehicles(c)
    return constat(
        c,
        [
            ("Sinistre", "SIN-TB-250612-01"),
            ("Contrat A", a.contract),
            ("Date de l'accident", "11/06/2025"),
        ],
        "11/06/2025",
        "11/06/2025 vers 16h30",
        "Parking du centre commercial de la Part-Dieu, niveau -2, 69003 Lyon",
        "Aucun",
        "Non",
        a,
        b,
        ({2, 14}, {1}),
        Sketch(
            "parking",
            "A quitte sa place en marche arrière et accroche, avec son avant droit, "
            "l'arrière gauche de B, stationné sur la place voisine.",
        ),
        "Lyon, le 11/06/2025",
    )


@pdf("app-auto-003", "devis_carrosserie.pdf")
def _bernard_quote(c: Case) -> DocSpec:
    a, _ = _bernard_vehicles(c)
    issuer = company(
        "Carrosserie Lyonnaise",
        "Carrosserie — peinture",
        "47 rue Paul Bert, 69003 Lyon",
        "+33 4 65 71 44 19",
        "atelier@carrosserie-lyonnaise.example.fr",
        "#3B4A5A",
    )
    lines = [
        Line("Redressage de l'aile avant droite", "2.5", "h", "62"),
        Line(
            "Réparation plastique et remise en forme du bouclier avant (côté droit)",
            "1.5",
            "h",
            "62",
        ),
        Line("Dépose et repose du bouclier avant et du projecteur droit", "0.5", "h", "62"),
        Line("Main-d'œuvre peinture (aile, bouclier, raccord capot)", "3.5", "h", "62"),
        Line("Ingrédients peinture", "1", "forfait", "240"),
        Line("Petites fournitures, agrafes et protections", "1", "forfait", "80.67"),
    ]
    return DocSpec(
        "Devis n° CL-2025-0612",
        issuer,
        "12/06/2025",
        [("Date", "12/06/2025"), ("Véhicule", a.plate), ("Client", a.owner.full)],
        [
            Columns(
                [
                    ("Client", [("", a.owner.full), ("", a.owner.address), ("", a.owner.phone)]),
                    (
                        "Véhicule",
                        [
                            ("", a.model),
                            ("", f"Immatriculation {a.plate}"),
                            ("", "Kilométrage : 24 180 km"),
                        ],
                    ),
                ]
            ),
            Section("Détail des réparations"),
            *quote_blocks(lines, "0.20", c.money("montant_devis"), f"{c.id} devis"),
            Para(
                "Immobilisation estimée : 2 jours. Franchise éventuelle selon votre contrat.",
                7.8,
                "i",
                MUTED,
            ),
            Signatures(
                [("L'atelier", "Karim HADDAD"), ("Bon pour accord — le client", "")],
                "Lyon, le 12/06/2025",
            ),
        ],
    )


LEFEBVRE = Person(
    "Mme",
    "LEFEBVRE",
    "Nathalie",
    "13/01/1980",
    "19 rue Solférino, 59000 Lille",
    "+33 6 39 98 28 84",
)
# The file name is the one referenced by the seed; the glazier itself is fictitious.
GLAZIER = company(
    "Vitrages Express Atlantique",
    "Vitrage automobile — centre de Lille Euralille",
    "12 rue des Canonniers, 59800 Lille",
    "+33 3 53 01 66 30",
    "lille@vitrages-express.example.fr",
    "#0E7490",
)


@pdf("app-auto-004", "declaration_bris_glace.pdf")
def _lefebvre_declaration(c: Case) -> DocSpec:
    p = LEFEBVRE.check(c.field("assure"))
    day = c.field("DateDeclaration")
    return DocSpec(
        "Déclaration de sinistre — bris de glace",
        PRV_AUTO,
        day,
        [("N° sinistre", "SIN-NL-251008-01"), ("Déclaré le", day), ("Contrat", "AUTO-PRV-4410276")],
        [
            Section("Assurée"),
            Fields(
                [
                    ("Nom et prénom", p.formal),
                    ("Date de naissance", p.born),
                    ("Adresse", p.address),
                    ("Téléphone", p.phone),
                    ("E-mail", p.email),
                    ("Contrat", "AUTO-PRV-4410276 — tous risques"),
                ]
            ),
            Section("Véhicule"),
            Fields(
                [
                    ("Véhicule", c.field("vehicule")),
                    ("Immatriculation", "EK-567-CD"),
                    ("Usage", "Privé et trajet travail"),
                    ("Kilométrage", "61 300 km"),
                ]
            ),
            Section("Sinistre"),
            Fields(
                [
                    ("Date et heure", "05/10/2025 vers 15h10"),
                    ("Lieu", "Autoroute A1 Lille → Paris, km 178"),
                    ("Cause", "Projection de gravillons par un poids lourd"),
                    ("Élément touché", "Pare-brise athermique"),
                    ("Évolution", "Éclat côté conducteur, fissure de 30 cm en 3 jours"),
                    ("Tiers", "Non identifié"),
                ]
            ),
            Section("Circonstances"),
            Para(
                "Le 05/10/2025 vers 15h10, sur l'autoroute A1 en direction de Paris, des gravillons "
                "projetés par un poids lourd ont fait un éclat sur le pare-brise, côté conducteur. "
                "L'éclat s'est transformé en fissure qui atteignait 30 cm le 08/10/2025 et gênait la "
                "visibilité : j'ai fait remplacer le pare-brise le jour même."
            ),
            Section("Réparation"),
            Fields(
                [
                    ("Réparateur", f"{GLAZIER.name} (centre de Lille Euralille)"),
                    ("Intervention", "Remplacement du pare-brise le 08/10/2025"),
                    ("Montant", f"{c.field('montant_facture')} TTC"),
                    ("Franchise", "0,00 € — garantie bris de glace sans franchise"),
                    ("Règlement", "Direct au réparateur (cession de créance)"),
                ]
            ),
            Section("Pièces jointes"),
            Bullets(["Facture du réparateur du 08/10/2025."]),
            *sworn("Lille", day, p),
        ],
    )


@pdf("app-auto-004", "facture_carglass.pdf")
def _lefebvre_invoice(c: Case) -> DocSpec:
    p = LEFEBVRE.check(c.field("assure"))
    total = c.money("montant_facture")
    lines = [
        Line("Pare-brise athermique avec bande pare-soleil", "1", "u", "372.17"),
        Line("Kit de collage polyuréthane et joint d'encadrement", "1", "u", "24.50"),
        Line("Main-d'œuvre dépose et pose du pare-brise", "1.5", "h", "58"),
        Line(
            "Transfert du capteur de pluie et calibrage de la caméra d'aide à la conduite",
            "1",
            "forfait",
            "33",
        ),
    ]
    return DocSpec(
        "Facture n° VEA-LIL-2025-10-0412",
        GLAZIER,
        "08/10/2025",
        [("Date", "08/10/2025"), ("Véhicule", "EK-567-CD"), ("Sinistre", "SIN-NL-251008-01")],
        [
            Columns(
                [
                    ("Client", [("", p.full), ("", p.address), ("", p.phone)]),
                    (
                        "Véhicule et assurance",
                        [
                            ("", f"{c.field('vehicule')} — EK-567-CD"),
                            ("", f"Assureur : {PREVAIQ}"),
                            ("", "Contrat AUTO-PRV-4410276"),
                        ],
                    ),
                ]
            ),
            Section("Remplacement du pare-brise"),
            *quote_blocks(lines, "0.20", total, f"{c.id} facture"),
            Section("Règlement"),
            Table(
                [Col("Payeur", 7), Col("Montant", 2, "r")],
                [[f"{PREVAIQ} — garantie bris de glace (franchise 0,00 €)", eur(total)]],
                footer=[["Reste à payer par la cliente", eur(0)]],
            ),
            Para(
                "Intervention réalisée le 08/10/2025. Cession de créance signée par l'assurée. "
                "Ancien pare-brise recyclé. Garantie de pose : 2 ans.",
                7.8,
                "i",
                MUTED,
            ),
        ],
    )


ROUX = Person(
    "M.", "ROUX", "Frédéric", "27/06/1986", "6 rue Victor Hugo, 33000 Bordeaux", "+33 6 39 98 35 09"
)


@pdf("app-auto-005", "depot_plainte.pdf")
def _roux_complaint(c: Case) -> DocSpec:
    p = ROUX.check(c.field("assure"))
    issuer = Party(
        "Police nationale",
        "Commissariat central de Bordeaux — accueil des plaintes",
        ("Bordeaux (33)", "Tél. +33 5 36 49 40 00"),
        POLICE,
    )
    return DocSpec(
        "Récépissé de dépôt de plainte",
        issuer,
        c.field("date_vol"),
        [
            ("N° de procédure", "2026/033/001954"),
            ("Date", f"{c.field('date_vol')} à 10h20"),
            ("Unité", "Accueil — plaintes"),
        ],
        [
            Section("Plaignant"),
            Fields(
                [
                    ("Nom et prénom", p.formal),
                    ("Né le", f"{p.born} à Pau (64)"),
                    ("Adresse", p.address),
                    ("Téléphone", p.phone),
                ]
            ),
            Section("Faits déclarés"),
            Fields(
                [
                    ("Qualification", "Vol de véhicule"),
                    ("Date des faits", f"Nuit du 14 au {c.field('date_vol')}"),
                    ("Lieu", f"{c.field('lieu_vol')} — voie publique, devant le domicile"),
                    ("Véhicule", f"{c.field('vehicule')} — gris foncé — FT-890-EF"),
                    ("Kilométrage déclaré", "48 210 km"),
                    ("Clés", "Les deux clés sont en possession du plaignant"),
                    ("Mode opératoire", "Inconnu — aucun débris de verre constaté sur la place"),
                ],
                cols=1,
                label_ratio=0.25,
            ),
            Section("Déclaration recueillie"),
            Para(
                "Le plaignant déclare avoir stationné et verrouillé son véhicule le 14/02/2026 vers "
                "19h30 devant son domicile, et avoir constaté sa disparition le 15/02/2026 à 07h45. "
                "Le véhicule est inscrit au fichier des véhicules volés."
            ),
            Note(
                "",
                "Le présent récépissé atteste du dépôt de plainte. En cas de découverte du "
                "véhicule, le plaignant sera avisé par le service.",
            ),
            Signatures(
                [
                    ("Le plaignant", p.full),
                    ("L'agent de police judiciaire", "Gardien de la paix A. LACOSTE"),
                ],
                f"Bordeaux, le {c.field('date_vol')}",
            ),
        ],
        subtitle="Article 15-3 du Code de procédure pénale",
    )


@pdf("app-auto-005", "rapport_expert.pdf")
def _roux_expert(c: Case) -> DocSpec:
    p = ROUX.check(c.field("assure"))
    damage = c.parsed("damage_assessment", "visual_damage_analysis")
    lines = [
        Line("Colonne de direction et antivol (neiman)", "1", "u", "1050"),
        Line("Serrure de porte conducteur, barillet et jeu de clés codé", "1", "u", "520"),
        Line("Main-d'œuvre mécanique et électricité", "8", "h", "70"),
        Line("Main-d'œuvre peinture (4 éléments rayés)", "10", "h", "70"),
        Line("Ingrédients peinture", "1", "forfait", "690"),
        Line("Nettoyage et désinfection de l'habitacle", "1", "forfait", "180"),
        Line("Diagnostic électronique et programmation de l'antidémarrage", "1", "forfait", "300"),
    ]
    return DocSpec(
        "Rapport d'expertise — véhicule volé retrouvé",
        MONDEAL,
        "20/02/2026",
        [("Rapport", "EXP-2026-0871"), ("Date", "20/02/2026"), ("Sinistre", "SIN-FR-260218-01")],
        [
            Fields(
                [
                    ("Mandant", f"{PREVAIQ} — Service Sinistres Automobile"),
                    ("Assuré", p.full),
                    ("Véhicule", f"{c.field('vehicule')} — FT-890-EF"),
                    ("Contrat", "AUTO-PRV-5172938"),
                    ("Examen", "19/02/2026, contradictoire, garage de Mérignac"),
                    ("Expert", "Sébastien LAFFONT, expert automobile"),
                ]
            ),
            Section("Historique"),
            Bullets(
                [
                    f"{c.field('date_vol')} : vol déclaré (plainte n° 2026/033/001954), kilométrage "
                    "déclaré 48 210 km.",
                    "17/02/2026 : véhicule retrouvé abandonné sur un parking de zone industrielle "
                    "à Mérignac, à environ 15 km du domicile.",
                    "19/02/2026 : examen du véhicule, kilométrage relevé 48 760 km.",
                ]
            ),
            Section("Constatations"),
            Table(
                [Col("Élément", 2.4), Col("Constat", 7)],
                [
                    ["Colonne de direction", "Forcée, antivol de direction (neiman) cassé"],
                    ["Porte conducteur", "Barillet de serrure arraché"],
                    ["Vitrages", "Intacts — aucun bris de glace"],
                    [
                        "Carrosserie",
                        "Rayures multiples sur les flancs gauche et droit (4 éléments)",
                    ],
                    ["Habitacle", "Souillé (mégots, canettes), sellerie non dégradée"],
                    ["Clés", "Deux clés présentées par l'assuré, fonctionnelles"],
                ],
            ),
            Section("Chiffrage des réparations"),
            *quote_blocks(lines, "0.20", D(damage["total_damage_estimate"]), f"{c.id} expertise"),
            Note(
                "Points d'attention",
                "Aucun bris de vitre alors que le mode d'effraction reste "
                "indéterminé ; environ 550 km parcourus en 2 jours ; véhicule retrouvé à environ "
                "15 km du domicile. Ces éléments sont portés à la connaissance de l'assureur.",
                "warn",
            ),
            Signatures([("L'expert", "Sébastien LAFFONT")], "Bordeaux, le 20/02/2026"),
        ],
    )


VINCENT = Person(
    "Mme", "VINCENT", "Émilie", "01/12/1990", "15 rue de France, 06000 Nice", "+33 6 39 98 47 31"
)
GIORDANO = Person(
    "M.", "GIORDANO", "Lucas", "23/04/1995", "8 avenue Borriglione, 06100 Nice", "+33 6 39 98 47 58"
)


@pdf("app-auto-006", "constat_amiable.pdf")
def _vincent_constat(c: Case) -> DocSpec:
    a = Vehicle(
        VINCENT.check(c.field("assure")),
        c.field("vehicule"),
        "GH-123-IJ",
        PREVAIQ,
        "AUTO-PRV-6024517",
        "Du 01/02/2025 au 31/01/2026",
        "Côté droit",
        "Portière passager rayée, rétroviseur droit cassé",
        "B a changé de file sans clignotant et m'a accrochée sur le côté droit.",
        licence(VINCENT, "2009"),
    )
    b = Vehicle(
        GIORDANO,
        "Volkswagen Polo (2018)",
        "FB-472-NC",
        "Rivazur Assurances",
        "RVA-2018-06-55120",
        "Du 01/07/2025 au 30/06/2026",
        "Avant gauche",
        "Pare-chocs avant gauche rayé",
        "J'ai changé de file pour tourner à gauche.",
        licence(GIORDANO, "2014"),
    )
    lines = [
        Line("Rétroviseur extérieur droit complet (coque, glace, moteur)", "1", "u", "385"),
        Line("Débosselage et préparation de la portière avant droite", "3", "h", "65"),
        Line("Peinture portière avant droite et raccord d'aile", "3", "h", "65"),
        Line("Ingrédients peinture", "1", "forfait", "210"),
        Line("Dépose et repose des garnitures, réglage du rétroviseur", "1", "h", "65"),
        Line("Petites fournitures et protections", "1", "forfait", "75"),
    ]
    garage = company(
        "Carrosserie Azur",
        "Carrosserie — peinture",
        "21 avenue de la Lanterne, 06200 Nice",
        "+33 4 65 71 81 26",
        "atelier@carrosserie-azur.example.fr",
        "#3B4A5A",
    )
    annex = [
        Section("Annexe — devis de réparation du véhicule A"),
        Fields(
            [
                ("Carrossier", f"{garage.name}, 21 avenue de la Lanterne, 06200 Nice"),
                ("SIRET", fake_siret(garage.name)),
                ("Devis n°", "CA-2025-0813-27"),
                ("Date", "13/08/2025"),
            ]
        ),
        *quote_blocks(lines, "0.20", c.money("montant_devis"), f"{c.id} devis"),
        Para(
            "Recours à exercer contre l'assureur du véhicule B (responsabilité du tiers : 100 %).",
            7.8,
            "i",
            MUTED,
        ),
    ]
    return constat(
        c,
        [
            ("Sinistre", "SIN-EV-250814-01"),
            ("Contrat A", a.contract),
            ("Date de l'accident", "12/08/2025"),
        ],
        "12/08/2025",
        "12/08/2025 vers 18h20",
        "Promenade des Anglais, à hauteur du boulevard Gambetta, 06000 Nice",
        "M. Paul ROSSI (+33 6 39 98 14 52)",
        "Non",
        a,
        b,
        ({9}, {10}),
        Sketch(
            "lane",
            "A circule dans la file de gauche ; B, dans la file de droite, change de file "
            "et accroche le côté droit de A.",
        ),
        "Nice, le 12/08/2025",
        annex,
    )


@pdf("app-auto-007", "declaration_sinistre.pdf")
def _fournier_declaration(c: Case) -> DocSpec:
    if c.data.get("status") != "error":
        raise ValueError(f"{c.id}: expected the unreadable-scan scenario (status error)")
    p, day = FOURNIER, c.created
    model, plate, contract = "Peugeot 2008 (2021)", "GB-318-TC", "AUTO-PRV-7350184"
    return DocSpec(
        "Déclaration de sinistre automobile",
        PRV_AUTO,
        day,
        [("Contrat", contract), ("Déclaré le", day)],
        [
            Section("Assurée"),
            Fields(
                [
                    ("Nom et prénom", p.formal),
                    ("Date de naissance", p.born),
                    ("Adresse", p.address),
                    ("Téléphone", p.phone),
                ]
            ),
            Section("Véhicule"),
            Fields(
                [
                    ("Véhicule", model),
                    ("Immatriculation", plate),
                    ("Contrat", f"{contract} — tous risques"),
                    ("Conductrice", p.formal),
                ]
            ),
            Section("Sinistre"),
            Fields(
                [
                    ("Date et heure", "28/11/2025 vers 18h10"),
                    ("Lieu", "Parking d'un centre commercial, avenue de la Somme, 33700 Mérignac"),
                    ("Nature", "Choc contre un plot en béton en marche arrière"),
                    ("Tiers", "Aucun"),
                ]
            ),
            Section("Circonstances"),
            Para(
                "En reculant pour sortir d'une place de stationnement, j'ai heurté un plot en béton "
                "que je n'avais pas vu. Le pare-chocs arrière est enfoncé et le feu arrière gauche "
                "est fissuré. Le véhicule reste roulant."
            ),
            Section("Dommages"),
            Bullets(["Pare-chocs arrière enfoncé côté gauche.", "Feu arrière gauche fissuré."]),
            *sworn("Mérignac", day, p),
        ],
        scanned=True,
    )


RENARD = Person(
    "M.",
    "RENARD",
    "Christophe",
    "14/08/1976",
    "7 rue Ampère, ZA de la Croix-Blanche, 49070 Beaucouzé",
    "+33 6 39 98 59 68",
)


@pdf("app-auto-008", "declaration_flotte.pdf")
def _renard_declaration(c: Case) -> DocSpec:
    RENARD.check(c.field("assure"))
    company_name = re.search(r"\((?:flotte )?(.+)\)", c.field("assure")).group(1)
    day = c.field("DateDeclaration")
    lines = [
        Line("Bouclier arrière", "1", "u", "520"),
        Line("Feux arrière avec feu de recul", "2", "u", "140"),
        Line("Main-d'œuvre tôlerie", "5", "h", "65"),
        Line("Peinture et ingrédients", "1", "forfait", "275"),
    ]
    return DocSpec(
        "Déclaration de sinistre — contrat flotte",
        PRV_PRO,
        day,
        [
            ("N° sinistre", "SIN-CR-260322-01"),
            ("Déclaré le", day),
            ("Contrat flotte", "FLT-PRO-2024-0318"),
        ],
        [
            Section("Souscripteur"),
            Fields(
                [
                    ("Entreprise", company_name),
                    ("SIRET", fake_siret(company_name)),
                    ("Adresse", RENARD.address),
                    ("Gestionnaire", f"{RENARD.full} (gérant)"),
                    ("Téléphone", RENARD.phone),
                    ("E-mail", "flotte@renard-transport.example.fr"),
                ]
            ),
            Section("Véhicule et conducteur"),
            Fields(
                [
                    ("Véhicule", c.field("vehicule")),
                    ("Immatriculation", "HJ-456-KL"),
                    ("N° de parc", "V07 — utilitaire de livraison"),
                    ("Kilométrage", "68 940 km"),
                    ("Conducteur", "M. Kévin ROBIN, chauffeur-livreur (salarié)"),
                    ("Permis", "Catégorie B, délivré en 2016"),
                ]
            ),
            Section("Sinistre"),
            Fields(
                [
                    ("Date et heure", "20/03/2026 vers 10h15"),
                    (
                        "Lieu",
                        "Quai de livraison d'un client, zone industrielle, 49124 "
                        "Saint-Barthélemy-d'Anjou",
                    ),
                    ("Nature", "Collision en marche arrière lors d'une livraison"),
                    ("Tiers", "Aucun — poteau de protection du quai"),
                    ("Responsabilité", "100 % assuré"),
                    ("Véhicule roulant", "Oui"),
                ]
            ),
            Para(
                "En reculant pour se mettre à quai, le conducteur a heurté le poteau métallique de "
                "protection. Le pare-chocs arrière est fendu et les feux arrière, dont les feux de "
                "recul, sont cassés."
            ),
            Section("Chiffrage initial (devis du garage partenaire)"),
            *quote_blocks(lines, "0.20", c.money("montant_devis"), f"{c.id} devis"),
            Note(
                "Validation du responsable de flotte",
                "En attente : la réparation sera lancée "
                "après validation du devis par le responsable de flotte.",
                "warn",
            ),
            Section("Pièces jointes"),
            Bullets(
                [
                    "photos_dommages.zip : 3 photos (vue arrière, feux de recul, pare-chocs).",
                    "Devis initial du garage partenaire.",
                ]
            ),
            Signatures(
                [("Le conducteur", "M. Kévin ROBIN"), ("Validation du responsable de flotte", "")],
                f"Beaucouzé, le {day}",
            ),
        ],
        subtitle="PrevaIQ PRO — flotte automobile",
    )


# =============================================================================
# Photos (MAI-Image-2.6)
# =============================================================================

STYLE = (
    " Photorealistic smartphone photo, natural light, slight imperfections in framing and "
    "focus. No people, no faces, no text, no logos or brand names, no watermark."
)
CAR = " No badges or emblems; license plates out of frame or not readable."


@dataclass(frozen=True)
class Photo:
    prompt: str
    width: int = 1536
    height: int = 1152
    grayscale: bool = False


def _photo(scene: str, car: bool = False, portrait: bool = False) -> Photo:
    prompt = scene + STYLE + (CAR if car else "")
    return Photo(prompt, 1152, 1536) if portrait else Photo(prompt)


PHOTOS: dict[tuple[str, str], Photo] = {
    ("app-house-hab-001", "photo_toiture.jpg"): _photo(
        "Photo taken from the garden of a detached 1930s house near Versailles, France, the day "
        "after a violent winter storm: on the brown mechanical clay tile roof, a ragged gap near "
        "the ridge where about twenty tiles were torn off, exposing wooden battens and dark "
        "underlay; a few displaced tiles hang over the edge, broken tile shards in the gutter and "
        "on the wet lawn. Grey overcast February sky, bare trees."
    ),
    ("app-house-hab-001", "photo_tuiles_endommagees.jpg"): _photo(
        "Close-up taken from a ladder at the eaves of a storm-damaged roof of brown mechanical "
        "interlocking clay tiles on a detached house in a French suburban town: several tiles "
        "cracked in half, others lifted and slipped out of their rows, sharp broken edges, moss in "
        "the joints, rain droplets, a gap revealing wooden battens. Overcast winter daylight. In "
        "the background typical French suburban houses with cream rendered walls, white shutters "
        "and clay tile roofs, bare trees; no landmark or monument."
    ),
    ("app-hab-002", "photo_parquet_gonflé.jpg"): _photo(
        "Kitchen floor of a French apartment after a washing machine leak: light oak floating "
        "laminate boards swollen and warped, raised joints and cupped edges over about eight "
        "square metres in front of a white front-loading washing machine without any visible "
        "brand, a detached white skirting board, darker damp patches, a folded towel on the floor. "
        "Daylight from a window, slightly high angle."
    ),
    ("app-hab-002", "photo_plafond_voisin.jpg"): _photo(
        "Looking up at the white painted ceiling of a living room in an older French apartment: a "
        "large irregular yellow-brown water stain of about three square metres with darker "
        "tide-mark edges, small paint cracks and a slight bulge, a simple pendant light nearby, "
        "cornice moulding along the wall. Soft daylight."
    ),
    ("app-hab-003", "photo_serrure_intacte.jpg"): _photo(
        "Close-up of the outside of the front door of an apartment in a residential building in "
        "Toulouse: a painted wooden door with an intact modern security lock cylinder, a brushed "
        "metal handle and escutcheon plate; the door edge, the strike plate and the frame are "
        "clean and undamaged, with no scratches, no pry marks, no splinters and no sign of forced "
        "entry. Corridor lighting, sharp focus, no brand markings on the lock.",
        portrait=True,
    ),
    ("app-hab-004", "photo_cave_inondee.jpg"): _photo(
        "Flooded basement cellar of a house in southern France after torrential rain, lit by a "
        "bare bulb and the phone flash: about sixty centimetres of murky brown water, floating "
        "cardboard boxes and plastic crates, two bicycles half submerged, an old chest freezer and "
        "a washing machine standing in the water, rough stone and concrete walls with a wet line, "
        "wooden steps leading down. Slightly grainy."
    ),
    ("app-hab-004", "photo_murs_rdc.jpg"): _photo(
        "Ground-floor room of a house in southern France after a flood: painted plaster walls with "
        "damp staining rising to about 1.2 metres, a clear tide line, bubbling and peeling paint, "
        "white salt efflorescence, swollen skirting boards, bare tiled floor, an unbranded "
        "dehumidifier running in a corner, furniture moved away. Daylight from a window."
    ),
    ("app-hab-005", "photo_toiture_tuiles.jpg"): _photo(
        "Roof of a house in Colmar, Alsace, two days after a violent June hailstorm, taken from a "
        "ladder: red mechanical clay tiles with about fifteen cracked or holed tiles, chips and "
        "fragments scattered on the slope, a blue plastic tarp temporarily covering part of the "
        "roof held by wooden battens, summer sky, vineyard hills in the background."
    ),
    ("app-hab-005", "photo_gouttiere.jpg"): _photo(
        "Close-up of a zinc half-round gutter along the edge of a red clay tile roof, dented and "
        "crushed over about three metres by large hailstones, many small round impact dents on the "
        "zinc, a bent bracket, a few broken tile chips lying in the gutter. Summer daylight."
    ),
    ("app-hab-005", "photo_velux_fissure.jpg"): _photo(
        "Inside an attic bedroom of a house: a roof window set in the sloping ceiling, its glass "
        "pane cracked by hail in a star pattern radiating from an impact point, water droplets "
        "running down the inside and a damp stain on the plaster below, a plastic bucket on the "
        "wooden floor catching drips. Overcast daylight through the window, no brand on the frame.",
        portrait=True,
    ),
    ("app-hab-006", "photo_fissure_mur.jpg"): _photo(
        "Load-bearing wall in the living room of an old Haussmann-style apartment in Lyon: a "
        "diagonal crack about two metres long running at 45 degrees across the painted plaster "
        "from the corner of a door frame towards the ceiling, three to five millimetres wide with "
        "crumbling edges, two small plaster crack-monitoring tell-tales across it, a wooden folding "
        "ruler resting against the wall for scale, parquet floor and moulded skirting. Daylight."
    ),
    ("app-hab-007", "photo_plafond_chambre.jpg"): _photo(
        "Looking up at the ceiling of a small bedroom in a rented apartment in Rennes, France: "
        "white ceiling paint blistered and bubbling over about six square metres after a water "
        "leak from the flat above, peeling flakes, a yellowish damp stain running down the top of "
        "the adjacent wall over about two square metres, a simple ceiling light, the edge of a bed "
        "with a grey duvet. Daylight."
    ),
    ("app-hc-005", "panoramique_dentaire.jpg"): Photo(
        "Grayscale dental panoramic radiograph (orthopantomogram) of an adult patient, realistic "
        "medical X-ray on a black background showing both jaws, all teeth with their roots, the "
        "mandible and the maxillary sinuses. On the left side of the image (the patient's upper "
        "right), the upper second premolar is missing and leaves a gap, the adjacent upper first "
        "molar shows deep decay under a large old filling, and the upper first premolar has a "
        "large filling. A few small fillings on other teeth. No text, no letters, no numbers, no "
        "labels, no names, no annotations, no orientation markers.",
        2048,
        1152,
        grayscale=True,
    ),
    ("app-auto-003", "photo_aile_droite.jpg"): _photo(
        "Underground shopping-centre car park with concrete pillars and fluorescent lighting: the "
        "front right wing of a white modern compact hatchback with a deep horizontal scratch about "
        "forty centimetres long scraped through the paint to bare metal and a slight dent, the "
        "right corner of the front bumper deformed and scuffed. Close three-quarter view.",
        car=True,
    ),
    ("app-auto-005", "photo_vehicule_retrouve.jpg"): _photo(
        "A dark grey compact five-door hatchback found abandoned in a nearly empty car park of an "
        "industrial estate near Bordeaux in February, overcast sky, warehouses behind: long "
        "scratches along the side bodywork, all windows intact with no broken glass, the driver's "
        "door lock cylinder torn out leaving a hole near the handle, cigarette butts and empty "
        "drink cans on the ground by the driver's door. Three-quarter side view.",
        car=True,
    ),
    ("app-pp-auto-001", "photo_dommages_avant.jpg"): _photo(
        "Car body repair workshop under fluorescent lights: the front of a dark blue premium "
        "four-door saloon after a frontal impact against a concrete pole: front bumper shattered "
        "and partly torn off, grille broken, bonnet folded in a deep V shape in the middle, both "
        "headlights cracked with the left one partly dislodged, front crossmember pushed back, "
        "airbags not deployed, no emblem on the grille.",
        car=True,
    ),
    ("app-pp-auto-001", "photo_dommages_lateral.jpg"): _photo(
        "Car body repair workshop: left side view of a dark blue premium four-door saloon showing "
        "the front left wing creased with fresh stress folds from a frontal impact, and older "
        "pre-existing damage: long faded scratches and small rust and oxidation spots on the front "
        "left wing and on the driver's door, clearly older than the fresh impact damage. "
        "Fluorescent workshop lighting.",
        car=True,
    ),
    ("app-sc-auto-001", "photo_pare_chocs_arriere.jpg"): _photo(
        "Parked in front of the plain closed door of a garage workshop: the rear of a metallic grey "
        "modern compact hatchback after a low-speed rear-end collision, the rear bumper moderately "
        "deformed with a crack along its lower edge and white paint transfer marks from the other "
        "car, tail lights intact, no other vehicle in view. Daylight.",
        car=True,
    ),
    ("app-sc-auto-001", "photo_coffre.jpg"): _photo(
        "Close-up of the lower edge of the tailgate of a metallic grey modern compact hatchback "
        "after a rear-end collision: slight buckling of the tailgate edge with small chips of "
        "missing paint, the bumper below scuffed, an intact tail light partly visible. Daylight in "
        "a garage.",
        car=True,
    ),
}

ARCHIVES: dict[tuple[str, str], dict[str, Photo]] = {
    ("app-auto-008", "photos_dommages.zip"): {
        "01_vue_arriere.jpg": _photo(
            "Delivery loading area of a business park: the rear of a white compact delivery van "
            "with two rear doors, the rear bumper cracked and pushed in on the right side and the "
            "right rear light cluster broken, a yellow and black steel protection post next to it. "
            "Overcast daylight, no company livery or lettering on the van.",
            car=True,
        ),
        "02_feux_de_recul.jpg": _photo(
            "Close-up of the broken rear light cluster of a white compact delivery van: cracked red "
            "and clear plastic lens with missing pieces, the reversing light bulb exposed, plastic "
            "shards on the bumper, scuff marks. Daylight.",
            car=True,
        ),
        "03_pare_chocs_arriere.jpg": _photo(
            "Close-up of the cracked black plastic rear bumper corner of a white compact delivery "
            "van after reversing into a steel post: a split in the plastic, scrape marks with "
            "yellow paint transfer, a misaligned bumper edge. Daylight.",
            car=True,
        ),
    },
}
ARCHIVE_TIMESTAMPS = {("app-auto-008", "photos_dommages.zip"): (2026, 3, 20, 10, 25, 0)}


class PhotoError(RuntimeError):
    """An image could not be generated (refused, invalid request or retries exhausted)."""


def _retry_delay(response: Any, attempt: int) -> float:
    headers = response.headers
    for name in ("retry-after-ms", "x-ms-retry-after-ms"):
        if headers.get(name, "").isdigit():
            return min(300.0, int(headers[name]) / 1000)
    value = headers.get("retry-after", "")
    if value.isdigit():
        return min(300.0, float(value))
    if value:
        try:
            when = email.utils.parsedate_to_datetime(value)
            return min(300.0, max(1.0, (when - dt.datetime.now(dt.timezone.utc)).total_seconds()))
        except (TypeError, ValueError):
            pass
    return min(240.0, 15.0 * 2 ** (attempt - 1))


class ImageClient:
    """Sequential MAI-Image client: Entra ID token, throttled, retries on 429/5xx."""

    RETRYABLE = {408, 429, 500, 502, 503, 504}

    def __init__(self, endpoint: str, deployment: str) -> None:
        from azure.identity import (
            AzureCliCredential,
            ChainedTokenCredential,
            DefaultAzureCredential,
        )

        self.url = f"{endpoint.rstrip('/')}/mai/v1/images/generations"
        self.deployment = deployment
        self._credential = ChainedTokenCredential(
            AzureCliCredential(process_timeout=60),
            DefaultAzureCredential(exclude_cli_credential=True),
        )
        self._token: Any = None
        self._last_request = -MIN_REQUEST_INTERVAL_S
        self.attempts: dict[str, int] = {}

    def _bearer(self) -> str:
        if self._token is None or self._token.expires_on - time.time() < 300:
            self._token = self._credential.get_token(MAI_SCOPE)
        return self._token.token

    def generate(self, label: str, photo: Photo) -> bytes:
        import httpx

        payload = {
            "model": self.deployment,
            "prompt": photo.prompt,
            "width": photo.width,
            "height": photo.height,
        }
        for attempt in range(1, MAX_ATTEMPTS + 1):
            pause = self._last_request + MIN_REQUEST_INTERVAL_S - time.monotonic()
            if pause > 0:
                time.sleep(pause)
            self._last_request = time.monotonic()
            self.attempts[label] = attempt
            try:
                response = httpx.post(
                    self.url,
                    json=payload,
                    timeout=httpx.Timeout(300, connect=30),
                    headers={"Authorization": f"Bearer {self._bearer()}"},
                )
            except httpx.TransportError as exc:
                delay = min(240.0, 15.0 * 2 ** (attempt - 1))
                print(f"    {label}: {type(exc).__name__}, retry in {delay:.0f} s", flush=True)
                time.sleep(delay)
                continue
            if response.status_code == 200:
                return base64.b64decode(response.json()["data"][0]["b64_json"])
            if response.status_code == 401:
                self._token = None
            if response.status_code in self.RETRYABLE or response.status_code == 401:
                delay = _retry_delay(response, attempt)
                print(
                    f"    {label}: HTTP {response.status_code}, retry in {delay:.0f} s "
                    f"(attempt {attempt}/{MAX_ATTEMPTS})",
                    flush=True,
                )
                time.sleep(delay)
                continue
            raise PhotoError(f"{label}: HTTP {response.status_code} {response.text[:400]}")
        raise PhotoError(f"{label}: no image after {MAX_ATTEMPTS} attempts")


def to_jpeg(png: bytes, grayscale: bool = False) -> bytes:
    """PNG from the model → JPEG (quality 85), long side capped at PHOTO_MAX_SIDE."""
    pix = fitz.Pixmap(png)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    target = fitz.csGRAY if grayscale else fitz.csRGB
    if pix.colorspace is None or pix.colorspace.n != target.n:
        pix = fitz.Pixmap(target, pix)
    longest = max(pix.width, pix.height)
    if longest > PHOTO_MAX_SIDE:
        scale = PHOTO_MAX_SIDE / longest
        pix = fitz.Pixmap(pix, round(pix.width * scale), round(pix.height * scale))
    return pix.tobytes("jpg", jpg_quality=JPEG_QUALITY)


def build_zip(members: dict[str, bytes], stamp: tuple[int, int, int, int, int, int]) -> bytes:
    """Deterministic zip (fixed timestamps, stored JPEGs)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            archive.writestr(info, members[name])
    return buffer.getvalue()


def read_zip(path: Path) -> dict[str, bytes]:
    if not path.exists():
        return {}
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


# =============================================================================
# Manifest and CLI
# =============================================================================

KINDS = {".pdf": "pdf", ".jpg": "photo", ".jpeg": "photo", ".png": "photo", ".zip": "archive"}


def asset_path(app_id: str, filename: str) -> tuple[Path, str]:
    folder = REPO_FOLDERS.get(app_id)
    if folder:
        return DEMO_DIR / folder / filename, "repo"
    return SEEDED_DIR / app_id / filename, "generated"


def check_coverage(cases: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Every seeded file must have exactly one source; every source must match a seeded file."""
    keys = [(case["id"], f["filename"]) for case in cases for f in case.get("files", [])]
    sources = set(PDF_BUILDERS) | set(PHOTOS) | set(ARCHIVES)
    missing = [k for k in keys if k[0] not in REPO_FOLDERS and k not in sources]
    stale = sources - set(keys)
    if missing or stale:
        raise SystemExit(
            f"Generator out of sync with the seed data — no source for {missing}, "
            f"unknown {sorted(stale)}"
        )
    return keys


def _provenance(photo: Photo, day: str | None) -> dict[str, Any]:
    return {"model": MAI_MODEL, "version": MAI_VERSION, "prompt": photo.prompt, "date": day}


def _known_provenance(previous: dict[str, Any] | None, photo: Photo, path: Path) -> dict[str, Any]:
    """Keep the recorded provenance of an existing photo (prompt actually used, date)."""
    if previous:
        return previous
    day = dt.date.fromtimestamp(path.stat().st_mtime).isoformat() if path.exists() else None
    return _provenance(photo, day)


def build_manifest(
    keys: list[tuple[str, str]],
    previous: dict[tuple[str, str], dict[str, Any]],
    generated: dict[tuple[str, ...], dict[str, Any]],
) -> dict[str, Any]:
    entries = []
    for app_id, filename in keys:
        path, origin = asset_path(app_id, filename)
        entry: dict[str, Any] = {
            "app_id": app_id,
            "filename": filename,
            "path": path.relative_to(ROOT).as_posix(),
            "origin": origin,
            "kind": KINDS[Path(filename).suffix.lower()],
        }
        before = previous.get((app_id, filename), {})
        if (app_id, filename) in PHOTOS:
            entry["generated_with"] = generated.get((app_id, filename)) or _known_provenance(
                before.get("generated_with"), PHOTOS[(app_id, filename)], path
            )
        if (app_id, filename) in ARCHIVES:
            known = {
                item["filename"]: item.get("generated_with") for item in before.get("contents", [])
            }
            entry["contents"] = [
                {
                    "filename": name,
                    "generated_with": generated.get((app_id, filename, name))
                    or _known_provenance(known.get(name), photo, path),
                }
                for name, photo in ARCHIVES[(app_id, filename)].items()
            ]
        entries.append(entry)
    for app_id, filename, relative in EXTRA_REPO_FILES:
        entries.append(
            {
                "app_id": app_id,
                "filename": filename,
                "path": (DEMO_DIR / relative).relative_to(ROOT).as_posix(),
                "origin": "repo",
                "kind": KINDS[Path(filename).suffix.lower()],
            }
        )
    return {
        "version": 1,
        "description": (
            "Fictitious demo files referenced by the PrevaIQ demo cases (seeded by "
            "scripts/seed_customer360.py from scripts/seed_data, plus demo cases uploaded in "
            "production). origin=repo: existing repo asset, referenced as is; origin=generated: "
            "built by scripts/generate_seeded_demo_files.py (PDFs from the seed data with PyMuPDF, "
            "photos with MAI-Image-2.6). Restore a running environment with "
            "scripts/restore_demo_files.py."
        ),
        "files": entries,
    }


def load_previous_manifest() -> dict[tuple[str, str], dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return {}
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {(entry["app_id"], entry["filename"]): entry for entry in data.get("files", [])}


def write_if_changed(path: Path, data: bytes) -> bool:
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def generate_photos(
    client: ImageClient,
    selected: set[str],
    force: bool,
    today: str,
    generated: dict[tuple[str, ...], dict[str, Any]],
    failures: list[str],
) -> None:
    for (app_id, filename), photo in PHOTOS.items():
        path = SEEDED_DIR / app_id / filename
        if (selected and app_id not in selected) or (path.exists() and not force):
            continue
        label = f"{app_id}/{filename}"
        print(f"  photo {label} ...", flush=True)
        try:
            write_if_changed(path, to_jpeg(client.generate(label, photo), photo.grayscale))
            generated[(app_id, filename)] = _provenance(photo, today)
        except PhotoError as exc:
            failures.append(str(exc))
            print(f"    FAILED {exc}", flush=True)
    for (app_id, filename), members in ARCHIVES.items():
        path = SEEDED_DIR / app_id / filename
        if selected and app_id not in selected:
            continue
        content = read_zip(path)
        todo = [name for name in members if force or name not in content]
        for name in todo:
            label = f"{app_id}/{filename}:{name}"
            print(f"  photo {label} ...", flush=True)
            try:
                content[name] = to_jpeg(
                    client.generate(label, members[name]), members[name].grayscale
                )
                generated[(app_id, filename, name)] = _provenance(members[name], today)
            except PhotoError as exc:
                failures.append(str(exc))
                print(f"    FAILED {exc}", flush=True)
        if todo:  # keep partial archives so that a rerun only generates what is missing
            kept = {name: data for name, data in content.items() if name in members}
            write_if_changed(path, build_zip(kept, ARCHIVE_TIMESTAMPS[(app_id, filename)]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--only",
        action="append",
        metavar="APP_ID",
        help="Limit generation to these cases (repeatable); the manifest stays complete",
    )
    parser.add_argument(
        "--photos",
        action="store_true",
        help=f"Generate missing photos with {MAI_MODEL} (Entra ID, az login)",
    )
    parser.add_argument("--force", action="store_true", help="Regenerate photos that already exist")
    parser.add_argument("--endpoint", default=os.environ.get("MAI_IMAGE_ENDPOINT", MAI_ENDPOINT))
    parser.add_argument(
        "--deployment", default=os.environ.get("MAI_IMAGE_DEPLOYMENT", MAI_DEPLOYMENT)
    )
    args = parser.parse_args(argv)

    cases = seeded_cases()
    by_id = {case["id"]: case for case in cases}
    selected = set(args.only or [])
    unknown = selected - set(by_id)
    if unknown:
        parser.error(f"unknown case(s): {', '.join(sorted(unknown))}")
    keys = check_coverage(cases)
    previous = load_previous_manifest()

    written = unchanged = 0
    for (app_id, filename), builder in PDF_BUILDERS.items():
        if selected and app_id not in selected:
            continue
        data = render_pdf(builder(Case(by_id[app_id])), f"{app_id}/{filename}")
        if write_if_changed(SEEDED_DIR / app_id / filename, data):
            written += 1
        else:
            unchanged += 1
    print(f"PDFs: {written} written, {unchanged} unchanged")

    generated: dict[tuple[str, ...], dict[str, Any]] = {}
    failures: list[str] = []
    if args.photos:
        client = ImageClient(args.endpoint, args.deployment)
        generate_photos(
            client, selected, args.force, dt.date.today().isoformat(), generated, failures
        )
        retried = {label: n for label, n in client.attempts.items() if n > 1}
        print(
            f"Photos: {len(generated)} generated, {len(failures)} failed"
            + (f", retried: {retried}" if retried else "")
        )

    manifest = build_manifest(keys, previous, generated)
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    changed = write_if_changed(MANIFEST_PATH, text.encode("utf-8"))
    print(f"Manifest: {len(manifest['files'])} entries ({'updated' if changed else 'unchanged'})")

    missing = [
        e["path"]
        for e in manifest["files"]
        if (not selected or e["app_id"] in selected) and not (ROOT / e["path"]).is_file()
    ]
    archives = [
        e
        for e in manifest["files"]
        if e["kind"] == "archive"
        and (ROOT / e["path"]).is_file()
        and (not selected or e["app_id"] in selected)
    ]
    for entry in archives:
        names = set(read_zip(ROOT / entry["path"]))
        expected = set(ARCHIVES[(entry["app_id"], entry["filename"])])
        if names != expected:
            missing.append(f"{entry['path']} ({len(names & expected)}/{len(expected)} photos)")
    for path in missing:
        print(f"  missing: {path}")
    if missing and not args.photos:
        print("Run again with --photos to generate the missing photos.")
    for failure in failures:
        print(f"  failed: {failure}")
    return 1 if missing or failures else 0


if __name__ == "__main__":
    sys.exit(main())
