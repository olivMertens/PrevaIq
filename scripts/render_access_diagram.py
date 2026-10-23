"""Export the deliberately simple, icon-free access schematic from its drawio source."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import fitz


def render() -> None:
    base = Path(__file__).resolve().parents[1] / "docs" / "architecture" / "prevaiq-access"
    model = ET.parse(base.with_suffix(".drawio")).find(".//mxGraphModel")
    if model is None:
        raise ValueError("missing graph model")
    cells = {cell.attrib["id"]: cell for cell in model.findall(".//mxCell")}
    svg = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": model.attrib["pageWidth"],
            "height": model.attrib["pageHeight"],
            "viewBox": f"0 0 {model.attrib['pageWidth']} {model.attrib['pageHeight']}",
        },
    )
    ET.SubElement(svg, "rect", {"width": "100%", "height": "100%", "fill": "#FFFFFF"})
    defs = ET.SubElement(svg, "defs")
    marker = ET.SubElement(
        defs,
        "marker",
        {
            "id": "arrow",
            "viewBox": "0 0 10 10",
            "refX": "10",
            "refY": "5",
            "markerWidth": "6",
            "markerHeight": "6",
            "orient": "auto",
        },
    )
    ET.SubElement(marker, "path", {"d": "M 0 0 L 10 5 L 0 10 Z", "fill": "#17395C"})
    boxes = {}
    for key, cell in cells.items():
        if cell.get("vertex") != "1":
            continue
        geometry = cell.find("mxGeometry")
        if geometry is None:
            raise ValueError(f"missing geometry: {key}")
        x, y, w, h = (float(geometry.get(name, "0")) for name in ("x", "y", "width", "height"))
        style = dict(part.split("=", 1) for part in cell.get("style", "").split(";") if "=" in part)
        group = ET.SubElement(svg, "g", {"id": key, "transform": f"translate({x} {y})"})
        if not cell.get("style", "").startswith("text;"):
            ET.SubElement(
                group,
                "rect",
                {
                    "width": str(w),
                    "height": str(h),
                    "fill": style["fillColor"],
                    "stroke": style["strokeColor"],
                    "rx": "0",
                },
            )
            boxes[key] = (x, y, w, h)
        lines = cell.get("value", "").splitlines()
        size = float(style.get("fontSize", "13"))
        for index, line in enumerate(lines):
            if (
                fitz.get_text_length(line, fontname="hebo" if index == 0 else "helv", fontsize=size)
                > w - 24
            ):
                raise ValueError(f"text exceeds node width: {key}: {line}")
            if 25 + index * (size + 6) > h - 6:
                raise ValueError(f"text exceeds node height: {key}")
            text = ET.SubElement(
                group,
                "text",
                {
                    "x": "12",
                    "y": str(25 + index * (size + 6)),
                    "font-size": str(size),
                    "font-family": "Arial, sans-serif",
                    "fill": style.get("fontColor", "#17395C"),
                    "font-weight": "bold" if index == 0 and key != "note" else "normal",
                },
            )
            text.text = line
    segments = []
    for cell in cells.values():
        if cell.get("edge") != "1":
            continue
        style = dict(part.split("=", 1) for part in cell.get("style", "").split(";") if "=" in part)
        source, target = cell.attrib["source"], cell.attrib["target"]
        sx, sy, sw, sh = boxes[source]
        tx, ty, tw, th = boxes[target]
        a = (sx + sw * float(style["exitX"]), sy + sh * float(style["exitY"]))
        b = (tx + tw * float(style["entryX"]), ty + th * float(style["entryY"]))
        if a[0] != b[0] and a[1] != b[1]:
            raise ValueError("this exporter requires straight orthogonal edges")
        for key, (x, y, w, h) in boxes.items():
            if key not in (source, target):
                if (
                    a[1] == b[1]
                    and y < a[1] < y + h
                    and max(a[0], b[0]) > x
                    and min(a[0], b[0]) < x + w
                ):
                    raise ValueError(f"edge crosses {key}")
                if (
                    a[0] == b[0]
                    and x < a[0] < x + w
                    and max(a[1], b[1]) > y
                    and min(a[1], b[1]) < y + h
                ):
                    raise ValueError(f"edge crosses {key}")
        for c, d in segments:
            if (
                a[1] == b[1]
                and c[0] == d[0]
                and min(a[0], b[0]) < c[0] < max(a[0], b[0])
                and min(c[1], d[1]) < a[1] < max(c[1], d[1])
            ):
                raise ValueError("crossing edges")
            if (
                a[0] == b[0]
                and c[1] == d[1]
                and min(c[0], d[0]) < a[0] < max(c[0], d[0])
                and min(a[1], b[1]) < c[1] < max(a[1], b[1])
            ):
                raise ValueError("crossing edges")
        segments.append((a, b))
        ET.SubElement(
            svg,
            "path",
            {
                "d": f"M {a[0]} {a[1]} L {b[0]} {b[1]}",
                "fill": "none",
                "stroke": "#17395C",
                "stroke-width": "2",
            },
        )
        length = abs(b[0] - a[0]) + abs(b[1] - a[1])
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        p = (b[0] - 9 * ux - 4 * uy, b[1] - 9 * uy + 4 * ux)
        q = (b[0] - 9 * ux + 4 * uy, b[1] - 9 * uy - 4 * ux)
        ET.SubElement(
            svg,
            "polygon",
            {
                "points": f"{b[0]},{b[1]} {p[0]},{p[1]} {q[0]},{q[1]}",
                "fill": "#17395C",
            },
        )
    ET.ElementTree(svg).write(base.with_suffix(".svg"), encoding="utf-8", xml_declaration=True)
    with fitz.open(base.with_suffix(".svg")) as document:
        pdf = document.convert_to_pdf()
    with fitz.open("pdf", pdf) as document:
        document[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(base.with_suffix(".png"))


if __name__ == "__main__":
    render()
