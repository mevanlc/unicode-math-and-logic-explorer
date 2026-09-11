# Unicode math and logic explorer

An offline explorer for mathematical and logical notation. The current milestone
is a candidate inventory for reviewing the repertoire before defining our own
domains and symbol families.

## Build and browse

```sh
uv run tools/build_inventory.py
open target/inventory.html
```

The builder uses Python's standard library and the vendored Unicode 17.0.0 files.
It needs no network access once a suitable Python runtime is available to `uv`.
The report opens directly through `file://` and loads its database using a normal
`<script>` element. It has no CDN dependencies, server, fetch requests, or module
imports. All report assets are generated together in `target/`.

The report provides:

- All candidates in ascending codepoint order, or grouping by Unicode block,
  NamesList subheading, character kind, or script. Blocks follow codepoint order;
  other groups use alphabetical order. Symbols within every group follow codepoint order.
- Search by literal character, standardized variant, name, alias, usage note, or
  hexadecimal codepoint (`U+2229`, `0x2229`, or `2229`).
- Filters for the Math property, additional candidates, non-ASCII letters, and script.
- Details including aliases, notes, related characters, canonical/compatibility
  decompositions, standardized variants, and the reasons a character is a candidate.
- Copying of exact characters or variant sequences. Dotted circles used to preview
  combining marks are never copied. Glyph coverage depends on installed fonts.

## Inputs and generated files

| Location | Purpose |
| --- | --- |
| `ucd/17.0.0/` | Unmodified Unicode source data and its documentation. |
| `data/candidate-sources.json` | Review-pool sources: properties, blocks, ranges, and individual codepoints with reasons. |
| `tools/` | Builder, report templates, and checks. |
| `target/inventory.html` | Generated report entry point. |
| `target/inventory.js` | Script-loadable `globalThis.SYMBOL_INVENTORY` database. |
| `target/inventory.json` | The same inventory as readable JSON. |
| `target/inventory-summary.json` | Counts by block, script, kind, category, subheading, and candidate source. |
| `target/inventory-report.css`, `target/inventory-report.js` | Generated report assets. |

The initial review pool has **3,389 candidates**: **2,322 with the Math property**
and **1,067 additional characters**, across **29 blocks**. All **1,197 non-ASCII
letters** remain available for inspection. The letter filter changes the view;
it makes no permanent inclusion decision.

Whole blocks intentionally bring in adjacent characters that may prove irrelevant.
The candidate configuration is not the final repertoire or a list of domain tags.
Candidate-source counts overlap, because a character can enter through several sources.
Only explicitly named scalar entries in UnicodeData are candidates; unassigned
holes, controls without character names, and algorithmic name ranges are not imported.

Names, categories, decompositions, and numeric values come from `UnicodeData.txt`;
properties from `DerivedCoreProperties.txt` and `PropList.txt`; block boundaries
from `Blocks.txt`; script information from `Scripts.txt` and `ScriptExtensions.txt`;
formal aliases from `NameAliases.txt`; and variants from `StandardizedVariants.txt`.
`PropertyValueAliases.txt` expands category and script names.

NamesList supplies editorial aliases, annotations, and subheading context only.
Repeated subheadings keep separate occurrence IDs and notices even when the report
groups their labels together. Raw annotations retain their markers and source
line numbers. NamesList chart ranges are never used as authoritative block ranges.
Script metadata alone does not establish language independence.

Output includes the candidate configuration and SHA-256 hashes of its Unicode
source files. Builds are deterministic and have no wall-clock timestamps or
machine-specific paths in the data. Invalid configuration is checked before
writing output. To place a review build elsewhere:

```sh
uv run tools/build_inventory.py --output-dir target/another-review
```

## Checks

```sh
uv run tools/test_inventory.py
uv run tools/check_report.py
```

The first command checks parsing, source joins, repertoire coverage, and repeatable
output. The second uses Playwright and an installed Google Chrome in a separate
headless session, with networking disabled. It checks `file://` loading, filtering,
search, exact clipboard content, variant sequences, and mobile layout, and writes
screenshots to `target/`. Playwright itself may need downloading on its first run.
Build the report before running the browser check.

## Next milestone

Review the repertoire, especially non-ASCII mathematical letters and complete
styled alphabets. Then add explicit inclusion/exclusion decisions and our domain
and symbol-family tags as curated data, and generate the final explorer database.
UTR #25 MathClass is a separate supplementary dataset and is not yet vendored.

Unicode source data is © 2025 Unicode, Inc. Original notices are preserved in the
vendored files; see [Unicode terms of use](https://www.unicode.org/terms_of_use.html).
