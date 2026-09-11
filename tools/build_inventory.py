#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Build a reproducible, offline candidate inventory from vendored Unicode data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROPERTY_FILES = ("DerivedCoreProperties.txt", "PropList.txt")
DISPLAY_PROPERTIES = {
    "Math",
    "Other_Math",
    "Diacritic",
    "Default_Ignorable_Code_Point",
    "Variation_Selector",
    "Deprecated",
    "Pattern_Syntax",
}
DATA_FILES = (
    "UnicodeData.txt",
    "Blocks.txt",
    "Scripts.txt",
    "ScriptExtensions.txt",
    "NameAliases.txt",
    "PropertyValueAliases.txt",
    "StandardizedVariants.txt",
    "NamesList.txt",
    "ReadMe.txt",
    *PROPERTY_FILES,
)
ANNOTATION_TYPES = {
    "=": "alias",
    "%": "formalAlias",
    "*": "note",
    "x": "crossReference",
    ":": "canonicalDecomposition",
    "#": "compatibilityDecomposition",
    "~": "variation",
    "@+": "notice",
}
CHAR_LINE = re.compile(r"^([0-9A-F]{4,6})\t+(.+)$")


def codepoint(value: str) -> int:
    if not re.fullmatch(r"[0-9A-Fa-f]{4,6}", value):
        raise ValueError(f"Expected a hexadecimal codepoint: {value!r}")
    number = int(value, 16)
    if number > 0x10FFFF or 0xD800 <= number <= 0xDFFF:
        raise ValueError(f"Not a Unicode scalar value: {value}")
    return number


def code_range(value: str) -> tuple[int, int]:
    bounds = value.split("..")
    first, last = int(bounds[0], 16), int(bounds[-1], 16)
    if not 0 <= first <= last <= 0x10FFFF:
        raise ValueError(f"Invalid Unicode range: {value}")
    return first, last


def data_rows(text: str):
    for line in text.splitlines():
        content = line.split("#", 1)[0].strip()
        if content:
            yield [item.strip() for item in content.split(";")]


class RangeMap:
    def __init__(self, rows, default):
        self.ranges = sorted((code_range(row[0]), row[1]) for row in rows)
        self.starts = [bounds[0] for bounds, _ in self.ranges]
        self.default = default

    def get(self, number: int):
        index = bisect_right(self.starts, number) - 1
        if index >= 0:
            (_, end), value = self.ranges[index]
            if number <= end:
                return value
        return self.default


def unicode_characters(text: str) -> dict[int, dict]:
    """Read explicit scalar entries; algorithmic ranges are outside this inventory."""
    characters = {}
    for fields in data_rows(text):
        number = int(fields[0], 16)
        if fields[1].startswith("<") or 0xD800 <= number <= 0xDFFF:
            continue
        decomposition = None
        if fields[5]:
            pieces = fields[5].split()
            kind = pieces.pop(0)[1:-1] if pieces[0].startswith("<") else "canonical"
            decomposition = {"type": kind, "codepoints": [int(p, 16) for p in pieces]}
        characters[number] = {
            "codepoint": number,
            "hex": f"{number:04X}",
            "char": chr(number),
            "name": fields[1],
            "generalCategory": fields[2],
            "combiningClass": int(fields[3]),
            "bidiClass": fields[4],
            "bidiMirrored": fields[9] == "Y",
            "numericValue": fields[8] or None,
            "decomposition": decomposition,
        }
    return characters


@dataclass
class NamesList:
    entries: dict[int, dict] = field(default_factory=dict)
    sections: dict[str, dict] = field(default_factory=dict)
    chart_blocks: dict[str, dict] = field(default_factory=dict)


def parse_nameslist(text: str) -> NamesList:
    """Extract editorial context only; retain original annotation text and markers."""
    result = NamesList()
    current = None
    section = None
    chart_block = None
    summary = False
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line or line.startswith(";"):
            continue
        if line.startswith("@"):  # Prefixes are record types, not heading depths.
            parts = line.split("\t")
            marker = parts[0]
            payload = "\t".join(parts[1:]).lstrip("\t")
            if marker == "@@" and payload:
                chart_block = f"block:{line_number}"
                result.chart_blocks[chart_block] = {
                    "line": line_number,
                    "header": payload,
                    "annotations": [],
                }
                current = section = None
                summary = False
            elif marker in {"@~", "@@~", "@@@~"}:
                current = section = None
                summary = True
            elif marker == "@" and not summary:
                section = f"section:{line_number}"
                result.sections[section] = {
                    "line": line_number,
                    "label": payload,
                    "chartBlock": chart_block,
                    "annotations": [],
                }
                current = None
            elif marker == "@+" and not summary:
                annotation = {
                    "marker": marker,
                    "type": "notice",
                    "text": payload,
                    "line": line_number,
                }
                if current is not None:
                    result.entries[current]["annotations"].append(annotation)
                elif section:
                    result.sections[section]["annotations"].append(annotation)
                elif chart_block:
                    result.chart_blocks[chart_block]["annotations"].append(annotation)
            elif marker not in {"@", "@@", "@@+", "@@@", "@@@+", "@+"}:
                raise ValueError(
                    f"Unknown NamesList directive at line {line_number}: {marker}"
                )
            continue
        match = CHAR_LINE.fullmatch(line)
        if match:
            current = int(match[1], 16)
            if current in result.entries:
                raise ValueError(f"Duplicate NamesList character: {match[1]}")
            result.entries[current] = {
                "line": line_number,
                "section": section,
                "chartBlock": chart_block,
                "annotations": [],
            }
            continue
        if line.startswith("\t") and not summary:
            payload = line.lstrip("\t")
            if payload.startswith(";"):
                continue
            marker = payload[0] if len(payload) > 1 and payload[1] == " " else ""
            if marker not in ANNOTATION_TYPES:
                marker = ""
            annotation = {
                "marker": marker,
                "type": ANNOTATION_TYPES.get(marker, "note"),
                "text": payload[2:] if marker else payload,
                "line": line_number,
            }
            if current is not None:
                result.entries[current]["annotations"].append(annotation)
            elif section:
                result.sections[section]["annotations"].append(annotation)
            elif chart_block:
                result.chart_blocks[chart_block]["annotations"].append(annotation)
    return result


def cross_reference(text: str) -> int:
    # Both documented forms occur: "(name - CODE)" and "CODE [name]".
    match = re.fullmatch(r"\(.+ - ([0-9A-F]{4,6})\)", text)
    if not match:
        match = re.match(r"^([0-9A-F]{4,6})(?:\s|$)", text)
    if not match:
        raise ValueError(f"Unrecognized NamesList cross-reference: {text!r}")
    return codepoint(match[1])


def character_kind(category: str) -> str:
    return {
        "L": "Letter",
        "N": "Number",
        "M": "Combining mark",
        "S": "Symbol",
        "P": "Punctuation",
        "Z": "Separator",
        "C": "Format/control",
    }[category[0]]


def read_sources(ucd: Path, config_path: Path) -> tuple[dict, dict, list]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if set(config) != {
        "unicodeVersion",
        "properties",
        "blocks",
        "ranges",
        "codepoints",
    }:
        raise ValueError(
            "Candidate sources must specify unicodeVersion, properties, blocks, ranges, and codepoints"
        )
    if config["unicodeVersion"] != "17.0.0":
        raise ValueError("This builder expects the vendored Unicode 17.0.0 data")
    contents = {}
    manifest = []
    for name in DATA_FILES:
        raw = (ucd / name).read_bytes()
        contents[name] = raw.decode("utf-8")
        manifest.append({"file": name, "sha256": hashlib.sha256(raw).hexdigest()})
        if (
            name != "UnicodeData.txt"
            and config["unicodeVersion"] not in contents[name][:1000]
        ):
            raise ValueError(
                f"{name} does not identify Unicode {config['unicodeVersion']}"
            )
    return config, contents, manifest


def build_inventory(ucd: Path, config_path: Path) -> dict:
    config, files, manifest = read_sources(ucd, config_path)
    characters = unicode_characters(files["UnicodeData.txt"])
    names = parse_nameslist(files["NamesList.txt"])
    block_rows = list(data_rows(files["Blocks.txt"]))
    blocks = RangeMap(block_rows, "No_Block")
    scripts = RangeMap(data_rows(files["Scripts.txt"]), "Unknown")
    extensions = RangeMap(data_rows(files["ScriptExtensions.txt"]), None)
    value_aliases = defaultdict(dict)
    for prop, short, long, *_ in data_rows(files["PropertyValueAliases.txt"]):
        value_aliases[prop][short] = long

    properties = defaultdict(set)
    for name in PROPERTY_FILES:
        for row in data_rows(files[name]):
            if len(row) == 2:
                first, last = code_range(row[0])
                properties[row[1]].update(range(first, last + 1))

    reasons = defaultdict(set)
    for prop in config["properties"]:
        if prop not in properties:
            raise ValueError(f"Unknown binary property: {prop}")
        for cp in properties[prop]:
            reasons[cp].add(f"Property: {prop}")
    known_blocks = {row[1]: code_range(row[0]) for row in block_rows}
    for name in config["blocks"]:
        if name not in known_blocks:
            raise ValueError(f"Unknown block: {name}")
        first, last = known_blocks[name]
        for cp in range(first, last + 1):
            reasons[cp].add(f"Block: {name}")
    for item in config["ranges"]:
        first, last = codepoint(item["start"]), codepoint(item["end"])
        if first > last or not item["reason"].strip():
            raise ValueError(f"Invalid candidate range: {item}")
        for cp in range(first, last + 1):
            reasons[cp].add(item["reason"])
    for item in config["codepoints"]:
        cp = codepoint(item["codepoint"])
        if cp not in characters or not item["reason"].strip():
            raise ValueError(f"Invalid explicit candidate: {item}")
        reasons[cp].add(item["reason"])

    aliases = defaultdict(list)
    for cp, alias, kind in data_rows(files["NameAliases.txt"]):
        aliases[int(cp, 16)].append({"name": alias, "type": kind})
    variants = defaultdict(list)
    for sequence, description, contexts, *_ in data_rows(
        files["StandardizedVariants.txt"]
    ):
        cps = [int(cp, 16) for cp in sequence.split()]
        variants[cps[0]].append(
            {
                "codepoints": cps,
                "char": "".join(chr(cp) for cp in cps),
                "description": description,
                "contexts": contexts.split(),
            }
        )

    candidates = []
    for cp in sorted(reasons.keys() & characters.keys()):
        symbol = characters[cp].copy()
        context = names.entries.get(cp)
        if context is None:
            raise ValueError(f"Missing NamesList context for U+{cp:04X}")
        script = scripts.get(cp)
        extension = extensions.get(cp)
        script_extensions = (
            [value_aliases["sc"][item] for item in extension.split()]
            if extension
            else [script]
        )
        annotations = context["annotations"]
        refs = []
        for annotation in annotations:
            if annotation["type"] == "crossReference":
                target = cross_reference(annotation["text"])
                refs.append(
                    {
                        "codepoint": target,
                        "name": characters.get(target, {}).get(
                            "name", annotation["text"]
                        ),
                        "inInventory": target in reasons and target in characters,
                    }
                )
        symbol.update(
            {
                "generalCategoryName": value_aliases["gc"][symbol["generalCategory"]],
                "kind": character_kind(symbol["generalCategory"]),
                "block": blocks.get(cp),
                "script": script,
                "scriptExtensions": sorted(script_extensions),
                "math": cp in properties["Math"],
                "ascii": cp < 128,
                "properties": sorted(
                    prop for prop in DISPLAY_PROPERTIES if cp in properties[prop]
                ),
                "candidateReasons": sorted(reasons[cp]),
                "formalAliases": aliases[cp],
                "aliases": [a["text"] for a in annotations if a["type"] == "alias"],
                "crossReferences": refs,
                "variants": variants[cp],
                "namesList": context,
            }
        )
        candidates.append(symbol)

    actual = {s["codepoint"] for s in candidates}
    if "Math" in config["properties"] and properties["Math"] - actual:
        raise ValueError("Some Math characters are missing from the inventory")
    used_sections = {s["namesList"]["section"] for s in candidates}
    used_blocks = {s["namesList"]["chartBlock"] for s in candidates}
    sections = {
        key: value for key, value in names.sections.items() if key in used_sections
    }
    chart_blocks = {
        key: value for key, value in names.chart_blocks.items() if key in used_blocks
    }
    summary = {
        "candidates": len(candidates),
        "math": sum(s["math"] for s in candidates),
        "additional": sum(not s["math"] for s in candidates),
        "letters": sum(s["kind"] == "Letter" for s in candidates),
        "nonAsciiLetters": sum(
            s["kind"] == "Letter" and not s["ascii"] for s in candidates
        ),
        "withVariants": sum(bool(s["variants"]) for s in candidates),
        "blocks": dict(sorted(Counter(s["block"] for s in candidates).items())),
        "scripts": dict(sorted(Counter(s["script"] for s in candidates).items())),
        "kinds": dict(sorted(Counter(s["kind"] for s in candidates).items())),
        "generalCategories": dict(
            sorted(Counter(s["generalCategory"] for s in candidates).items())
        ),
        "subheadings": dict(
            sorted(
                Counter(
                    sections[s["namesList"]["section"]]["label"]
                    if s["namesList"]["section"]
                    else "No subheading"
                    for s in candidates
                ).items()
            )
        ),
        "candidateReasons": dict(
            sorted(
                Counter(
                    reason for s in candidates for reason in s["candidateReasons"]
                ).items()
            )
        ),
    }
    return {
        "schemaVersion": 1,
        "unicodeVersion": config["unicodeVersion"],
        "purpose": "Candidate inventory for review; not the final symbol repertoire.",
        "candidateSources": config,
        "sourceFiles": manifest,
        "summary": summary,
        "sections": sections,
        "chartBlocks": chart_blocks,
        "symbols": candidates,
    }


def write_inventory(inventory: dict, output: Path) -> None:
    # Prepare everything before touching the output directory.
    json_text = json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
    script_json = json.dumps(inventory, ensure_ascii=False, separators=(",", ":"))
    script_json = script_json.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    artifacts = {
        "inventory.json": json_text,
        "inventory.js": "// Generated by tools/build_inventory.py.\n"
        + "// Unicode data © 2025 Unicode, Inc. https://www.unicode.org/terms_of_use.html\n"
        + "globalThis.SYMBOL_INVENTORY = "
        + script_json
        + ";\n",
        "inventory-summary.json": json.dumps(
            inventory["summary"], ensure_ascii=False, indent=2
        )
        + "\n",
    }
    for source, destination in (
        ("inventory.html", "inventory.html"),
        ("inventory.css", "inventory-report.css"),
        ("inventory.js", "inventory-report.js"),
    ):
        artifacts[destination] = (ROOT / "tools" / "report" / source).read_text(
            encoding="utf-8"
        )
    output.mkdir(parents=True, exist_ok=True)
    for name, text in artifacts.items():
        (output / name).write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sources",
        type=Path,
        default=ROOT / "data" / "candidate-sources.json",
        help="Candidate source configuration (default: data/candidate-sources.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "target",
        help="Generated report directory (default: target/)",
    )
    args = parser.parse_args()
    try:
        inventory = build_inventory(ROOT / "ucd" / "17.0.0", args.sources)
        write_inventory(inventory, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Inventory build failed: {error}\n")
    summary = inventory["summary"]
    print(
        f"{summary['candidates']:,} candidates: {summary['math']:,} Math + {summary['additional']:,} additional"
    )
    print(
        f"{len(summary['blocks'])} blocks; {summary['nonAsciiLetters']:,} non-ASCII letters for review"
    )
    print(f"Report: {(args.output_dir / 'inventory.html').resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
