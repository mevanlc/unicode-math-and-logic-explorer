#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Check editorial parsing, authoritative joins, and deterministic output."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

from build_inventory import (
    ROOT,
    build_inventory,
    cross_reference,
    parse_nameslist,
    write_inventory,
)


class NamesListTests(unittest.TestCase):
    def test_context_boundaries_and_markers(self):
        names = parse_nameslist(
            "@@@\tA title\n"
            "@+\tA title notice\n"
            "\ta paragraph, not an annotation marker\n"
            "@@\t2200\tMath\t22FF\n"
            "@@+\n"
            "@+\tA block notice\n"
            "\tx 2192\n"
            "@\t\tRelations\n"
            "@+\tA section notice\n"
            "2241\tNOT TILDE\n"
            "\t= an alias\n"
            "\t\t% A FORMAL ALIAS\n"
            "\t* A note\n"
            "@+\tA character notice\n"
            "\tx (tilde operator - 223C)\n"
            "\t: 223C 0338\n"
            "\t# <font> 223C\n"
            "\t~ 2241 FE00 variation label\n"
            "\ta prose line\n"
            "\t; ignored text\n"
            "@\tRelations\n"
            "2242\tMINUS TILDE\n"
            "@~\tStandardized Variation Sequences\n"
            "@+\tSummary notice\n"
            "@@\t2300\tTechnical\t23FF\n"
            "2300\tDIAMETER SIGN\n"
        )
        first = names.entries[0x2241]
        second = names.entries[0x2242]
        self.assertNotEqual(first["section"], second["section"])
        self.assertEqual(
            [s["label"] for s in names.sections.values()], ["Relations", "Relations"]
        )
        self.assertEqual(
            [a["marker"] for a in first["annotations"]],
            ["=", "%", "*", "@+", "x", ":", "#", "~", ""],
        )
        self.assertEqual(first["annotations"][-1]["text"], "a prose line")
        self.assertEqual(second["annotations"], [])
        self.assertEqual(
            names.sections[first["section"]]["annotations"][0]["text"],
            "A section notice",
        )
        self.assertEqual(len(names.chart_blocks[first["chartBlock"]]["annotations"]), 2)
        self.assertIsNone(names.entries[0x2300]["section"])
        self.assertNotEqual(first["chartBlock"], names.entries[0x2300]["chartBlock"])

    def test_cross_reference_forms(self):
        for text in ["(n-ary intersection - 22C2)", "22C2 n-ary intersection", "22C2"]:
            self.assertEqual(cross_reference(text), 0x22C2)
        self.assertEqual(cross_reference("(cjk unified ideograph-4E00 - 4E00)"), 0x4E00)
        with self.assertRaises(ValueError):
            cross_reference("not a cross-reference")


class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = build_inventory(
            ROOT / "ucd" / "17.0.0", ROOT / "data" / "candidate-sources.json"
        )
        cls.symbols = {s["codepoint"]: s for s in cls.inventory["symbols"]}
        (ROOT / "target").mkdir(exist_ok=True)

    def test_repertoire_coverage_and_order(self):
        cps = [s["codepoint"] for s in self.inventory["symbols"]]
        self.assertEqual(cps, sorted(set(cps)))
        self.assertEqual(self.inventory["summary"]["math"], 2322)
        self.assertEqual(self.inventory["summary"]["generalCategories"]["Sm"], 960)
        self.assertEqual(len(self.symbols), 3389)
        self.assertNotIn(0x1D455, self.symbols)  # Unassigned hole in the math alphabet.
        self.assertNotIn(0x03A2, self.symbols)  # Unassigned Greek alphabet position.
        self.assertEqual(self.symbols[0x1D400]["char"], "𝐀")
        self.assertTrue(self.symbols[0x1D400]["math"])

    def test_additional_candidates_and_real_blocks(self):
        for cp in [ord("("), ord("A"), 0x00B0, 0x00B7, 0x03C0, 0x2026]:
            self.assertIn(cp, self.symbols)
            self.assertFalse(self.symbols[cp]["math"])
        self.assertEqual(self.symbols[ord("A")]["block"], "Basic Latin")
        self.assertEqual(self.symbols[ord("A")]["script"], "Latin")
        self.assertEqual(self.symbols[0x03C0]["scriptExtensions"], ["Greek"])
        self.assertIn("Latin", self.symbols[0x00B7]["scriptExtensions"])
        self.assertTrue(self.symbols[0x00B7]["candidateReasons"])

    def test_notes_aliases_and_variants(self):
        intersection = self.symbols[0x2229]
        self.assertIn("cap, hat", intersection["aliases"])
        self.assertEqual(intersection["crossReferences"][0]["codepoint"], 0x22C2)
        self.assertEqual(intersection["variants"][0]["codepoints"], [0x2229, 0xFE00])
        self.assertEqual(intersection["variants"][0]["char"], "∩\ufe00")
        self.assertEqual(intersection["variants"][0]["description"], "with serifs")
        aliases = self.symbols[0x2118]["formalAliases"]
        self.assertIn(
            {"name": "WEIERSTRASS ELLIPTIC FUNCTION", "type": "correction"}, aliases
        )
        section_id = self.symbols[0x22EE]["namesList"]["section"]
        section = self.inventory["sections"][section_id]
        self.assertEqual(section["label"], "Matrix ellipses")
        self.assertIn("row/column elision", section["annotations"][0]["text"])

    def test_decompositions_and_invisible_characters(self):
        self.assertEqual(
            self.symbols[0x2241]["decomposition"],
            {"type": "canonical", "codepoints": [0x223C, 0x0338]},
        )
        self.assertEqual(
            self.symbols[0x222C]["decomposition"],
            {"type": "compat", "codepoints": [0x222B, 0x222B]},
        )
        self.assertEqual(
            self.symbols[0x1D400]["decomposition"],
            {"type": "font", "codepoints": [0x0041]},
        )
        self.assertEqual(self.symbols[0x2062]["kind"], "Format/control")
        self.assertIn(
            "Default_Ignorable_Code_Point", self.symbols[0x2062]["properties"]
        )
        self.assertEqual(self.symbols[0x20D7]["kind"], "Combining mark")

    def test_deterministic_artifacts(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "target") as directory:
            output = Path(directory)
            write_inventory(self.inventory, output)
            first = {p.name: p.read_bytes() for p in output.iterdir()}
            write_inventory(self.inventory, output)
            second = {p.name: p.read_bytes() for p in output.iterdir()}
            self.assertEqual(first, second)
            self.assertEqual(len(first), 6)
            self.assertEqual(json.loads(first["inventory.json"]), self.inventory)
            self.assertIn(b"globalThis.SYMBOL_INVENTORY = ", first["inventory.js"])

    def test_unknown_configuration_fails(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "target") as directory:
            config = json.loads((ROOT / "data" / "candidate-sources.json").read_text())
            config["blocks"].append("Not a real block")
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "Unknown block"):
                build_inventory(ROOT / "ucd" / "17.0.0", path)


if __name__ == "__main__":
    unittest.main()
