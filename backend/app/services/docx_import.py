"""Deterministic Word question import with rich content and strict validation."""

import base64
import html
import io
import posixpath
import re
from zipfile import BadZipFile, ZipFile

from defusedxml import ElementTree as ET

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def import_docx(data: bytes):
    try:
        archive = ZipFile(io.BytesIO(data))
        if sum(x.file_size for x in archive.infolist()) > 40_000_000:
            raise ValueError("Expanded Word file exceeds 40 MB.")
        root = ET.fromstring(archive.read("word/document.xml"))
    except (BadZipFile, KeyError):
        raise ValueError("Upload a valid .docx Word document.")
    relationships = {}
    if "word/_rels/document.xml.rels" in archive.namelist():
        for rel in ET.fromstring(archive.read("word/_rels/document.xml.rels")):
            if rel.get("TargetMode") != "External":
                relationships[rel.get("Id")] = posixpath.normpath(
                    posixpath.join("word", rel.get("Target", ""))
                )

    errors = []

    def math(el):
        tag = el.tag.split("}")[-1]
        children = [x for x in el if not x.tag.split("}")[-1].endswith("Pr")]
        inner = "".join(math(x) for x in children)
        if tag == "t":
            return "<mtext>" + html.escape(el.text or "") + "</mtext>"
        if tag == "f":
            return "<mfrac>" + inner + "</mfrac>"
        if tag == "sSup":
            return "<msup>" + inner + "</msup>"
        if tag == "sSub":
            return "<msub>" + inner + "</msub>"
        if tag == "sSubSup":
            return "<msubsup>" + inner + "</msubsup>"
        if tag == "rad":
            expression = el.find("m:e", NS)
            degree = el.find("m:deg", NS)
            return (
                "<mroot>" + math(expression) + math(degree) + "</mroot>"
                if degree is not None and "".join(degree.itertext()).strip()
                else "<msqrt>" + math(expression) + "</msqrt>"
            )
        if tag == "d":
            begin = el.find("m:dPr/m:begChr", NS)
            end = el.find("m:dPr/m:endChr", NS)
            left = begin.get("{" + NS["m"] + "}val", "(") if begin is not None else "("
            right = end.get("{" + NS["m"] + "}val", ")") if end is not None else ")"
            return (
                "<mrow><mo>"
                + html.escape(left)
                + "</mo>"
                + inner
                + "<mo>"
                + html.escape(right)
                + "</mo></mrow>"
            )
        if tag in {
            "nary",
            "acc",
            "bar",
            "groupChr",
            "limLow",
            "limUpp",
            "eqArr",
            "box",
            "borderBox",
            "phant",
        }:
            errors.append(
                f"Equation construct {tag} needs conversion to an embedded image for accurate rendering."
            )
        if tag == "m":
            return "<mtable>" + inner + "</mtable>"
        if tag == "mr":
            return (
                "<mtr>"
                + "".join("<mtd>" + math(c) + "</mtd>" for c in children)
                + "</mtr>"
            )
        return "<mrow>" + inner + "</mrow>"

    def render(el):
        tag = el.tag.split("}")[-1]
        if tag == "t":
            return html.escape(el.text or "")
        if tag == "tab":
            return " "
        if tag == "br":
            return "<br/>"
        if tag in {"pPr", "rPr", "tblPr", "tcPr", "trPr", "tblGrid"}:
            return ""
        if tag == "oMath":
            return (
                '<math xmlns="http://www.w3.org/1998/Math/MathML">'
                + math(el)
                + "</math>"
            )
        if tag == "blip":
            target = relationships.get(el.get("{" + NS["r"] + "}embed"))
            if not target or target not in archive.namelist():
                errors.append("An embedded image could not be resolved.")
                return ""
            extension = target.rsplit(".", 1)[-1].lower()
            mime = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "gif": "image/gif",
                "webp": "image/webp",
            }.get(extension)
            if not mime:
                errors.append(f"Convert {extension} images to PNG/JPEG before upload.")
                return ""
            return (
                '<img alt="Question illustration" src="data:'
                + mime
                + ";base64,"
                + base64.b64encode(archive.read(target)).decode()
                + '"/>'
            )
        if tag in {"object", "pict", "AlternateContent"}:
            errors.append(
                "A legacy diagram/object must be converted to an embedded PNG/JPEG or native Word equation."
            )
            return ""
        inner = "".join(render(x) for x in el)
        wrapper = {"tbl": "table", "tr": "tr", "tc": "td", "p": "p"}.get(tag)
        if tag == "r":
            if el.find("w:rPr/w:b", NS) is not None:
                inner = "<strong>" + inner + "</strong>"
            if el.find("w:rPr/w:i", NS) is not None:
                inner = "<em>" + inner + "</em>"
            alignment = el.find("w:rPr/w:vertAlign", NS)
            if alignment is not None:
                value = alignment.get("{" + NS["w"] + "}val")
                if value == "subscript":
                    inner = "<sub>" + inner + "</sub>"
                if value == "superscript":
                    inner = "<sup>" + inner + "</sup>"
        return f"<{wrapper}>{inner}</{wrapper}>" if wrapper else inner

    questions = []
    current = None
    destination = None
    metadata = {}
    for block in root.find("w:body", NS):
        text = "".join(t.text or "" for t in block.findall(".//w:t", NS)).strip()
        markup = render(block)
        if not text and not ("<img" in markup or "<math" in markup):
            continue
        header = re.match(
            r"^\[(Lesson|Sub-Topic|Type|Marks|Negative Marks)\]\s*(.*)", text, re.I
        )
        if header and current is None:
            metadata[header[1]] = header[2]
            continue
        match = re.match(r"^Q\.?\s*\d+\)\s*", text, re.I)
        option = re.match(r"^(\*)?\[([a-d])\]\s*(?:[a-d]\)\s*)?", text, re.I)
        explanation = re.match(r"^\[S\d+\]\s*", text, re.I)
        hint = re.match(r"^\[Hint\]\s*", text, re.I)
        marker = match or option or explanation or hint
        if marker:
            # Preserve HTML and remove only the plain-text marker across split runs.
            remaining = len(marker[0])

            def strip_prefix(m):
                nonlocal remaining
                raw = m[0]
                decoded = html.unescape(raw)
                take = min(remaining, len(decoded))
                remaining -= take
                return html.escape(decoded[take:])

            markup = re.sub(r"(?<=>)[^<]+", strip_prefix, markup)
        if match:
            current = dict(
                prompt=markup,
                options=["", "", "", ""],
                correct=-1,
                explanation="",
                hint="",
            )
            questions.append(current)
            destination = "prompt"
        elif current is not None:
            if option:
                index = ord(option[2].lower()) - 97
                if current["options"][index]:
                    errors.append(f"Question {len(questions)} has a duplicate option.")
                current["options"][index] = markup
                destination = index
                if option[1]:
                    if current["correct"] != -1:
                        errors.append(
                            f"Question {len(questions)} has multiple correct options."
                        )
                    current["correct"] = index
            elif explanation:
                current["explanation"] = markup
                destination = "explanation"
            elif hint:
                current["hint"] = markup
                destination = "hint"
            elif isinstance(destination, int):
                current["options"][destination] += markup
            elif destination:
                current[destination] += markup
    if not questions:
        errors.append("No questions found. Use Q.1) followed by [a] through [d].")
    for i, q in enumerate(questions, 1):
        if any(not x for x in q["options"]) or q["correct"] not in range(4):
            errors.append(
                f"Question {i} needs four options and exactly one * correct answer."
            )
        if not q["hint"] or not q["explanation"]:
            errors.append(f"Question {i} needs [Hint] and [S{i}] explanation.")
    missing = [
        name
        for name in ["Lesson", "Sub-Topic", "Type", "Marks", "Negative Marks"]
        if name not in metadata
    ]
    if missing:
        errors.append(
            "Missing required metadata: "
            + ", ".join("[" + name + "]" for name in missing)
        )
    if errors:
        raise ValueError("\n".join(dict.fromkeys(errors)))
    return {"metadata": metadata, "questions": questions}
