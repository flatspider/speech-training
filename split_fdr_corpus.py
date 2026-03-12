#!/usr/bin/env python3
"""Split the UCSB FDR corpus into executive orders vs conversational material."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


SEPARATOR = "=" * 72
DEFAULT_EXCLUDED_CATEGORY = "Executive Orders"


@dataclass
class ParsedDoc:
    path: Path
    title: str
    date: str
    category: str
    url: str
    body: str

    @property
    def word_count(self) -> int:
        return len(self.body.split())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy UCSB text files into separate folders for conversational FDR "
            "training and executive orders."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("fdr_ucsb/txt"),
        help="Directory containing UCSB .txt files.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("prepared_corpora"),
        help="Directory where split corpora will be written.",
    )
    parser.add_argument(
        "--excluded-category",
        default=DEFAULT_EXCLUDED_CATEGORY,
        help="Category to carve out of the conversational corpus.",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=50,
        help="Skip very short files below this many body words.",
    )
    return parser.parse_args()


def parse_ucsb_file(path: Path) -> ParsedDoc:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    header, body = raw.split(SEPARATOR, 1) if SEPARATOR in raw else ("", raw)

    meta = {"title": "", "date": "", "category": "Unknown", "url": ""}
    for line in header.splitlines():
        line = line.strip()
        if line.startswith("Title:"):
            meta["title"] = line.split(":", 1)[1].strip()
        elif line.startswith("Date:"):
            meta["date"] = line.split(":", 1)[1].strip()
        elif line.startswith("Category:"):
            meta["category"] = line.split(":", 1)[1].strip()
        elif line.startswith("URL:"):
            meta["url"] = line.split(":", 1)[1].strip()

    return ParsedDoc(
        path=path,
        title=meta["title"],
        date=meta["date"],
        category=meta["category"],
        url=meta["url"],
        body=body.strip(),
    )


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def copy_doc(doc: ParsedDoc, destination_dir: Path) -> None:
    ensure_dir(destination_dir)
    shutil.copy2(doc.path, destination_dir / doc.path.name)


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir
    output_root = args.output_root
    excluded_category = args.excluded_category
    min_words = args.min_words

    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    conversational_dir = output_root / "conversational_fdr" / "txt"
    excluded_slug = excluded_category.lower().replace(" ", "_")
    excluded_dir = output_root / excluded_slug / "txt"

    ensure_dir(conversational_dir)
    ensure_dir(excluded_dir)

    stats = {
        "input_dir": str(input_dir.resolve()),
        "output_root": str(output_root.resolve()),
        "excluded_category": excluded_category,
        "min_words": min_words,
        "totals": {
            "all_files_seen": 0,
            "kept_files": 0,
            "skipped_short_files": 0,
            "conversational_files": 0,
            "excluded_files": 0,
            "conversational_words": 0,
            "excluded_words": 0,
        },
    }

    for path in sorted(input_dir.glob("*.txt")):
        stats["totals"]["all_files_seen"] += 1
        doc = parse_ucsb_file(path)
        if doc.word_count < min_words:
            stats["totals"]["skipped_short_files"] += 1
            continue

        stats["totals"]["kept_files"] += 1
        if doc.category == excluded_category:
            copy_doc(doc, excluded_dir)
            stats["totals"]["excluded_files"] += 1
            stats["totals"]["excluded_words"] += doc.word_count
        else:
            copy_doc(doc, conversational_dir)
            stats["totals"]["conversational_files"] += 1
            stats["totals"]["conversational_words"] += doc.word_count

    summary_path = output_root / "split_summary.json"
    summary_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    print("Corpus split complete")
    print(f"Input dir            : {input_dir}")
    print(f"Output root          : {output_root}")
    print(f"Excluded category    : {excluded_category}")
    print(f"Skipped short files  : {stats['totals']['skipped_short_files']}")
    print(f"Conversational files : {stats['totals']['conversational_files']}")
    print(f"Conversational words : {stats['totals']['conversational_words']:,}")
    print(f"Excluded files       : {stats['totals']['excluded_files']}")
    print(f"Excluded words       : {stats['totals']['excluded_words']:,}")
    print(f"Summary JSON         : {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
