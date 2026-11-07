"""Validate editable architecture graphs, export SVG with draw.io and rasterize that SVG."""

from __future__ import annotations

import argparse
import base64
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

import fitz

ROOT = Path(__file__).resolve().parents[1]
SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
EPS = 0.001


def styles(cell: ET.Element) -> dict[str, str]:
    return dict(item.split("=", 1) for item in cell.get("style", "").split(";") if "=" in item)


def validate_geometry(source: Path) -> dict[str, int]:
    model = ET.parse(source).find(".//mxGraphModel")
    if model is None:
        raise ValueError(f"{source}: missing mxGraphModel")
    cells = {cell.attrib["id"]: cell for cell in model.findall(".//mxCell")}
    rectangles: dict[str, tuple[float, float, float, float]] = {}

    def rectangle(key: str) -> tuple[float, float, float, float]:
        if key in rectangles:
            return rectangles[key]
        cell = cells[key]
        geometry = cell.find("mxGeometry")
        if geometry is None:
            raise ValueError(f"{key}: missing geometry")
        x, y, w, h = (float(geometry.get(name, "0")) for name in ("x", "y", "width", "height"))
        parent = cell.get("parent")
        if parent in cells and cells[parent].get("vertex") == "1":
            px, py, _, _ = rectangle(parent)
            x, y = x + px, y + py
        rectangles[key] = (x, y, w, h)
        return rectangles[key]

    def descends_from(key: str, parent: str) -> bool:
        while key in cells:
            if key == parent:
                return True
            key = cells[key].get("parent", "")
        return False

    vertices = {key: cell for key, cell in cells.items() if cell.get("vertex") == "1"}
    for key in vertices:
        rectangle(key)
        if vertices[key].get("diagramRole") == "label":
            style = styles(vertices[key])
            _, _, width, height = rectangle(key)
            font_size = float(style.get("fontSize", "14"))
            font = "hebo" if style.get("fontStyle") == "1" else "helv"
            lines = vertices[key].get("value", "").splitlines()
            if any(
                fitz.get_text_length(line, fontname=font, fontsize=font_size) > width
                for line in lines
            ):
                raise ValueError(f"{key}: text exceeds label width")
            if len(lines) * font_size * 1.2 > height + 1:
                raise ValueError(f"{key}: text exceeds label height")
    nodes = [key for key, cell in vertices.items() if cell.get("diagramRole") == "node"]
    for index, key in enumerate(nodes):
        x, y, w, h = rectangle(key)
        for other in nodes[index + 1 :]:
            ox, oy, ow, oh = rectangle(other)
            if min(x + w, ox + ow) > max(x, ox) + EPS and min(y + h, oy + oh) > max(y, oy) + EPS:
                raise ValueError(f"Overlapping nodes: {key}, {other}")
    obstacles = [
        key for key, cell in vertices.items() if cell.get("diagramRole") in {"node", "label"}
    ]
    segments: list[tuple[str, tuple[float, float], tuple[float, float]]] = []
    edge_count = 0
    for key, cell in cells.items():
        if cell.get("edge") != "1":
            continue
        edge_count += 1
        source_id, target_id = cell.attrib["source"], cell.attrib["target"]
        sx, sy, sw, sh = rectangle(source_id)
        tx, ty, tw, th = rectangle(target_id)
        style = styles(cell)
        start = (sx + sw * float(style["exitX"]), sy + sh * float(style["exitY"]))
        end = (tx + tw * float(style["entryX"]), ty + th * float(style["entryY"]))
        points = [
            start,
            *(
                (float(point.get("x", "0")), float(point.get("y", "0")))
                for point in cell.findall("mxGeometry/Array[@as='points']/mxPoint")
            ),
            end,
        ]
        for a, b in zip(points, points[1:]):
            horizontal = abs(a[1] - b[1]) < EPS
            vertical = abs(a[0] - b[0]) < EPS
            if not (horizontal or vertical):
                raise ValueError(f"Diagonal edge segment: {key}")
            if abs(a[0] - b[0]) + abs(a[1] - b[1]) < EPS:
                continue
            for obstacle in obstacles:
                if descends_from(obstacle, source_id) or descends_from(obstacle, target_id):
                    continue
                x, y, w, h = rectangle(obstacle)
                hit = (
                    horizontal
                    and y + EPS < a[1] < y + h - EPS
                    and max(a[0], b[0]) > x + EPS
                    and min(a[0], b[0]) < x + w - EPS
                ) or (
                    vertical
                    and x + EPS < a[0] < x + w - EPS
                    and max(a[1], b[1]) > y + EPS
                    and min(a[1], b[1]) < y + h - EPS
                )
                if hit:
                    raise ValueError(f"{key} crosses node/label {obstacle}")
            for previous, c, d in segments:
                if previous == key:
                    continue
                old_horizontal = abs(c[1] - d[1]) < EPS
                if horizontal == old_horizontal:
                    axis = 0 if horizontal else 1
                    other = 1 - axis
                    overlap = min(max(a[axis], b[axis]), max(c[axis], d[axis])) - max(
                        min(a[axis], b[axis]), min(c[axis], d[axis])
                    )
                    if overlap > EPS and abs(a[other] - c[other]) < 16 - EPS:
                        raise ValueError(f"Overlapping/close parallel lanes: {key}, {previous}")
                else:
                    ha, hb, va, vb = (a, b, c, d) if horizontal else (c, d, a, b)
                    if (
                        min(ha[0], hb[0]) - EPS <= va[0] <= max(ha[0], hb[0]) + EPS
                        and min(va[1], vb[1]) - EPS <= ha[1] <= max(va[1], vb[1]) + EPS
                    ):
                        intersection = (va[0], ha[1])
                        shared_endpoint = all(
                            any(
                                abs(point[0] - intersection[0]) < EPS
                                and abs(point[1] - intersection[1]) < EPS
                                for point in pair
                            )
                            for pair in ((a, b), (c, d))
                        )
                        if not shared_endpoint:
                            raise ValueError(f"Crossing edges: {key}, {previous}")
            segments.append((key, a, b))
        final = abs(points[-1][0] - points[-2][0]) + abs(points[-1][1] - points[-2][1])
        if final < 15 - EPS:
            raise ValueError(f"{key}: final arrow approach is shorter than 15px")
        previous = points[-2]
        ex, ey = float(style["entryX"]), float(style["entryY"])
        perpendicular = (
            (ex == 0 and abs(previous[1] - end[1]) < EPS and previous[0] <= tx - 15 + EPS)
            or (ex == 1 and abs(previous[1] - end[1]) < EPS and previous[0] >= tx + tw + 15 - EPS)
            or (ey == 0 and abs(previous[0] - end[0]) < EPS and previous[1] <= ty - 15 + EPS)
            or (ey == 1 and abs(previous[0] - end[0]) < EPS and previous[1] >= ty + th + 15 - EPS)
        )
        if not perpendicular:
            raise ValueError(f"{key}: arrow must approach the target border perpendicularly")
    return {"nodes": len(nodes), "edges": edge_count, "segments": len(segments)}


def inline_svg_images(path: Path) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    parents = {child: parent for parent in root.iter() for child in parent}
    for index, image in enumerate(list(root.iter(f"{{{SVG}}}image"))):
        href = image.get("href") or image.get(f"{{{XLINK}}}href", "")
        if not href.startswith("data:"):
            raise ValueError(f"External SVG image reference in {path.name}")
        if not href.startswith("data:image/svg+xml"):
            continue
        header, payload = href.split(",", 1)
        raw = base64.b64decode(payload) if ";base64" in header else unquote(payload).encode()
        nested = ET.fromstring(raw)
        ids = {
            element.get("id"): f"icon-{index}-{element.get('id')}"
            for element in nested.iter()
            if element.get("id")
        }
        classes = {
            name: f"icon-{index}-{name}"
            for element in nested.iter()
            for name in element.get("class", "").split()
        }
        for element in nested.iter():
            if element.tag.split("}")[-1] == "script":
                raise ValueError("Script in icon SVG")
            for name, value in list(element.attrib.items()):
                if name == "id":
                    element.set(name, ids[value])
                    continue
                for old, new in ids.items():
                    value = value.replace(f"url(#{old})", f"url(#{new})")
                    if value == f"#{old}":
                        value = f"#{new}"
                element.set(name, value)
            if element.get("class"):
                element.set(
                    "class", " ".join(classes[name] for name in element.attrib["class"].split())
                )
            if element.tag.split("}")[-1] == "style" and element.text:
                text = element.text
                for old, new in classes.items():
                    text = re.sub(rf"\.{re.escape(old)}(?![\w-])", f".{new}", text)
                for old, new in ids.items():
                    text = text.replace(f"url(#{old})", f"url(#{new})")
                    text = re.sub(rf"#{re.escape(old)}(?=\s*[{{>+~.:])", f"#{new}", text)
                element.text = text
        for name in ("x", "y", "width", "height", "transform", "opacity"):
            if image.get(name) is not None:
                nested.set(name, image.attrib[name])
        nested.set("preserveAspectRatio", "xMidYMid meet")
        parent = parents[image]
        position = list(parent).index(image)
        parent.remove(image)
        parent.insert(position, nested)
    for element in root.iter():
        if element.tag.split("}")[-1] in {"script", "foreignObject"}:
            raise ValueError("New architecture SVG must be script-free and plain-text vector")
        for name in ("href", f"{{{XLINK}}}href"):
            value = element.get(name, "")
            if value and not value.startswith(("#", "data:")):
                raise ValueError("External asset/link in exported architecture SVG")
    all_ids = [element.attrib["id"] for element in root.iter() if "id" in element.attrib]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Duplicate SVG IDs")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def find_drawio() -> str:
    for executable in ("drawio", "draw.io"):
        if result := shutil.which(executable):
            return result
    candidate = Path.home() / "AppData" / "Local" / "Programs" / "draw.io" / "draw.io.exe"
    if candidate.is_file():
        return str(candidate)
    raise FileNotFoundError("Install draw.io Desktop or supply --drawio-executable")


def render(
    source: Path,
    executable: str,
    scale: float = 1.5,
    resvg_module: str = "@resvg/resvg-js",
) -> dict[str, int]:
    counts = validate_geometry(source)
    target = source.with_suffix(".svg")
    subprocess.run(
        [
            executable,
            "--export",
            "--format",
            "svg",
            "--output",
            str(target),
            "--embed-svg-images",
            "--embed-svg-fonts",
            "false",
            "--theme",
            "light",
            "--size",
            "page",
            "--timeout",
            "60",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    )
    inline_svg_images(target)
    rasterizer = """
const fs = require('node:fs');
const { Resvg } = require(process.argv[1]);
const svg = fs.readFileSync(process.argv[2]);
const renderer = new Resvg(svg, {
  fitTo: {mode: 'zoom', value: Number(process.argv[4])},
  font: {loadSystemFonts: true, defaultFontFamily: 'Arial'}
});
fs.writeFileSync(process.argv[3], renderer.render().asPng());
"""
    subprocess.run(
        [
            "node",
            "-e",
            rasterizer,
            resvg_module,
            str(target),
            str(source.with_suffix(".png")),
            str(scale),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="*", type=Path)
    parser.add_argument("--drawio-executable")
    parser.add_argument("--resvg-module", default="@resvg/resvg-js")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    sources = args.sources or [
        ROOT / "docs" / "architecture" / f"{name}.drawio"
        for name in ("prevaiq-architecture", "prevaiq-aurora-runtime")
    ]
    for source in sources:
        counts = (
            validate_geometry(source)
            if args.check_only
            else render(
                source, args.drawio_executable or find_drawio(), resvg_module=args.resvg_module
            )
        )
        print(f"{source.name}: {counts}")


if __name__ == "__main__":
    main()
