#!/usr/bin/env python3
"""Suggest a git-ignored `categories.local.yaml` from a real invoice folder.

Privacy: this script reads your private PDFs locally and writes the discovered
vendor tokens ONLY into the git-ignored output file. It prints **counts only**
to the console — never vendor names, amounts, or filenames.

It works in three steps:
  1. Extract text from each file and find the ones the *base* config sends to
     manual review.
  2. For each, derive a candidate vendor token (a web domain label, or a line
     ending in GmbH/AG/...). Auto-assign a category using a built-in map of
     well-known *public* German vendors. Unknown vendors are written into a
     "# REVIEW" block for you to place by hand.
  3. Re-route every file with the new local config and report the new
     manual-review count.

Usage:
    python scripts/suggest_local_config.py \
        --input ./tax_input_docs \
        --base-config config/categories.yaml \
        --out config/categories.local.yaml
"""

from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path

import yaml

# Make the package importable when run from the repo root without installing.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from invoice_sorter.classifier import classify  # noqa: E402
from invoice_sorter.config import load_config  # noqa: E402
from invoice_sorter.extraction_adapter import _extract_pdf_light  # noqa: E402
from invoice_sorter.metadata_extraction import extract_metadata_hybrid  # noqa: E402
from invoice_sorter.models import DocumentResult, ProcessingStatus  # noqa: E402
from invoice_sorter.routing import route  # noqa: E402

# Built-in, PUBLIC knowledge: vendor token -> category. Safe to commit.
VENDOR_KNOWLEDGE: dict[str, str] = {
    # Internet / telco
    "telekom": "Internet", "vodafone": "Internet", "o2": "Internet",
    "congstar": "Internet", "1und1": "Internet", "pyur": "Internet",
    "m-net": "Internet",
    # Energy / home
    "eon": "Haushalt", "enbw": "Haushalt", "vattenfall": "Haushalt",
    "rwe": "Haushalt", "yello": "Haushalt", "eprimo": "Haushalt",
    "stadtwerke": "Haushalt", "ikea": "Haushalt", "obi": "Haushalt",
    "bauhaus": "Haushalt", "hornbach": "Haushalt", "lichtblick": "Haushalt",
    # Insurance
    "allianz": "Versicherung", "huk": "Versicherung", "huk24": "Versicherung",
    "axa": "Versicherung", "ergo": "Versicherung", "devk": "Versicherung",
    "generali": "Versicherung", "gothaer": "Versicherung",
    "cosmosdirekt": "Versicherung", "debeka": "Versicherung",
    # Health
    "aok": "Gesundheit", "barmer": "Gesundheit", "dak": "Gesundheit",
    "fielmann": "Gesundheit", "apollo": "Gesundheit", "apotheke": "Gesundheit",
    "doctolib": "Gesundheit",
    # Mobility
    "aral": "Auto / Mobilität", "shell": "Auto / Mobilität",
    "esso": "Auto / Mobilität", "bahn": "Auto / Mobilität",
    "flixbus": "Auto / Mobilität", "sixt": "Auto / Mobilität",
    "adac": "Auto / Mobilität", "freenow": "Auto / Mobilität",
    # Music
    "thomann": "Musik", "steinberg": "Musik", "ableton": "Musik",
    "native-instruments": "Musik", "session": "Musik",
    # Software / cloud
    "openai": "Software / Cloud Services", "anthropic": "Software / Cloud Services",
    "github": "Software / Cloud Services", "microsoft": "Software / Cloud Services",
    "apple": "Software / Cloud Services", "google": "Software / Cloud Services",
    "adobe": "Software / Cloud Services", "atlassian": "Software / Cloud Services",
    "notion": "Software / Cloud Services", "slack": "Software / Cloud Services",
    "zoom": "Software / Cloud Services", "dropbox": "Software / Cloud Services",
    "jetbrains": "Software / Cloud Services", "hetzner": "Software / Cloud Services",
    "strato": "Software / Cloud Services", "ionos": "Software / Cloud Services",
    "digitalocean": "Software / Cloud Services", "figma": "Software / Cloud Services",
    "1password": "Software / Cloud Services", "spotify": "Software / Cloud Services",
    "netflix": "Software / Cloud Services", "aws": "Software / Cloud Services",
    # Bank / finance
    "paypal": "Bank / Finanzen", "klarna": "Bank / Finanzen", "n26": "Bank / Finanzen",
    "dkb": "Bank / Finanzen", "ing": "Bank / Finanzen", "sparkasse": "Bank / Finanzen",
    "volksbank": "Bank / Finanzen", "comdirect": "Bank / Finanzen",
    "commerzbank": "Bank / Finanzen", "postbank": "Bank / Finanzen",
    "revolut": "Bank / Finanzen", "wise": "Bank / Finanzen",
    "scalable": "Bank / Finanzen", "traderepublic": "Bank / Finanzen",
    # Work / learning
    "udemy": "Arbeit", "coursera": "Arbeit", "heise": "Arbeit", "staples": "Arbeit",
    # Taxes
    "finanzamt": "Steuern", "elster": "Steuern", "wiso": "Steuern", "taxfix": "Steuern",
}

_DOMAIN_RE = re.compile(
    r"\b(?:www\.)?([a-z0-9][a-z0-9-]{1,30})\.(?:de|com|net|org|io|eu|at|ch|info)\b",
    re.IGNORECASE,
)
_GENERIC_DOMAIN_LABELS = {
    "mail", "info", "rechnung", "rechnungen", "noreply", "no-reply", "support",
    "service", "kontakt", "example", "gmail", "gmx", "web", "outlook", "yahoo",
    "t-online", "email", "billing", "invoice",
}
_COMPANY_RE = re.compile(
    r"^\s*(.{2,50}?\b(?:GmbH|AG|KG|UG|SE|mbH|e\.K\.|Ltd|Inc|& Co\.?\s*KG))",
    re.MULTILINE,
)


def candidate_vendor(text: str) -> str | None:
    """Return a short candidate vendor token, or None.

    Tries, in order: a web-domain label, a line ending in GmbH/AG/..., then the
    first prominent text line (often the sender). The last is noisy but at least
    captures *something* for you to review.
    """
    for m in _DOMAIN_RE.finditer(text):
        label = m.group(1).lower()
        if label not in _GENERIC_DOMAIN_LABELS and len(label) >= 3:
            return label
    m = _COMPANY_RE.search(text)
    if m:
        name = re.sub(r"\s+", " ", m.group(1)).strip(" ,.-")
        if 2 <= len(name) <= 50:
            return name
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip(" ,.-")
        # A plausible sender line: starts with a letter, mostly letters, short.
        if (3 <= len(line) <= 40 and line[0].isalpha()
                and sum(ch.isalpha() or ch.isspace() for ch in line) >= len(line) - 2):
            return line
    return None


def _extractor(use_docling: bool):
    if use_docling:
        from invoice_sorter.extraction_adapter import extract_document
        return extract_document
    return _extract_pdf_light


def lookup_category(token: str) -> str | None:
    low = token.lower()
    for key, cat in VENDOR_KNOWLEDGE.items():
        if key in low:
            return cat
    return None


def analyze(input_dir: Path, config, extract):
    """Return (manual_files, assigned: cat->set(vendor), unknown: list[token])."""
    manual_files = []
    assigned: dict[str, set[str]] = collections.defaultdict(set)
    unknown: list[str] = []
    for pdf in sorted(input_dir.rglob("*.pdf")):
        ex = extract(pdf)
        class_text = ex.classify_text()
        r = DocumentResult(source_path=pdf)
        r.text = class_text
        r.extraction_status = ex.status
        r.metadata = extract_metadata_hybrid(ex.text, class_text, config)
        c = classify(class_text, r.metadata, config)
        r.confidence = c.confidence
        r.category = route(r, c, config)
        if r.status == ProcessingStatus.MANUAL_REVIEW:
            manual_files.append(pdf)
            token = candidate_vendor(ex.text)
            if not token:
                continue
            cat = lookup_category(token)
            if cat and cat in config.category_names():
                assigned[cat].add(token)
            else:
                unknown.append(token)
    return manual_files, assigned, unknown


def build_local_config(config, assigned: dict[str, set[str]]) -> dict:
    cats: dict[str, dict] = {}
    for category in config.categories:
        entry: dict = {}
        if category.keywords:
            entry["keywords"] = list(category.keywords)
        vendors = list(category.vendors)
        for v in sorted(assigned.get(category.name, set())):
            if v.lower() not in {x.lower() for x in vendors}:
                vendors.append(v)
        if vendors:
            entry["vendors"] = vendors
        if not entry:
            entry["keywords"] = []
        cats[category.name] = entry
    return {
        "settings": {
            "confidence_threshold": config.confidence_threshold,
            "manual_review_category": config.manual_review_category,
            "default_currency": config.default_currency,
        },
        "categories": cats,
    }


def reroute_count(input_dir: Path, config, extract) -> int:
    manual = 0
    for pdf in sorted(input_dir.rglob("*.pdf")):
        ex = extract(pdf)
        class_text = ex.classify_text()
        r = DocumentResult(source_path=pdf)
        r.text = class_text
        r.extraction_status = ex.status
        r.metadata = extract_metadata_hybrid(ex.text, class_text, config)
        c = classify(class_text, r.metadata, config)
        r.confidence = c.confidence
        route(r, c, config)
        if r.status == ProcessingStatus.MANUAL_REVIEW:
            manual += 1
    return manual


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-config", default="config/categories.yaml")
    ap.add_argument("--out", default="config/categories.local.yaml")
    ap.add_argument("--use-docling", action="store_true",
                    help="Use the Docling backend (richer text/OCR, slower)")
    args = ap.parse_args()

    input_dir = Path(args.input)
    base = load_config(args.base_config)

    raw_extract = _extractor(args.use_docling)
    _cache: dict[Path, object] = {}

    def extract(p):  # extract each file once, reuse across both passes
        if p not in _cache:
            _cache[p] = raw_extract(p)
        return _cache[p]

    manual_files, assigned, unknown = analyze(input_dir, base, extract)
    local = build_local_config(base, assigned)

    out = Path(args.out)
    header = (
        "# AUTO-GENERATED git-ignored local config — contains YOUR private vendor\n"
        "# names. Do NOT commit. Pass it with --config.\n"
        "# Auto-assigned vendors were added under their category below.\n"
    )
    body = yaml.safe_dump(local, allow_unicode=True, sort_keys=False)
    review = ""
    if unknown:
        review = (
            "\n# ---------------------------------------------------------------\n"
            "# REVIEW: these vendor tokens were found in manual-review files but\n"
            "# could not be auto-assigned. Move each under the right category's\n"
            "# 'vendors:' list above, then re-run.\n"
        )
        for tok in sorted(set(unknown)):
            review += f"#   - {tok}\n"
    out.write_text(header + body + review, encoding="utf-8")

    new_config = load_config(out)
    new_manual = reroute_count(input_dir, new_config, extract)
    base_manual = len(manual_files)

    # Counts only — never print vendor strings.
    print(f"Files analyzed:                 {len(list(input_dir.rglob('*.pdf')))}")
    print(f"Manual review (base config):    {base_manual}")
    print(f"Auto-assigned known vendors:    {sum(len(v) for v in assigned.values())}")
    print(f"Captured, need your assignment: {len(set(unknown))}")
    print(f"Manual review (after local):    {new_manual}")
    print(f"\nWrote: {out}  (git-ignored)")
    print("Open it, move the '# REVIEW' vendors under the right categories, re-run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
