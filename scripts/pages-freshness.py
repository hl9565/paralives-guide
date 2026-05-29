#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

CURRENT_EA_VERSION = "0.1"
STALE_THRESHOLD_DAYS = {"HOT": 21, "WARM": 45, "COLD": 120}
TIER_RE = re.compile(r"<!--\s*maintenance-tier:\s*(HOT|WARM|COLD)\s*-->")
UPDATED_RE = re.compile(r'<div class="article-meta">.*?<span>Updated:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})</span>', re.S)
VERSION_RE = re.compile(r'<div class="article-meta">.*?<span>Game Version:\s*EA\s+([0-9]+(?:\.[0-9]+)*)</span>', re.S)


@dataclass
class StaleRow:
    file: str
    tier: str
    updated: str
    days: int


@dataclass
class DriftRow:
    file: str
    tier: str
    verified: str
    current: str


@dataclass
class MissingRow:
    file: str
    reason: str


@dataclass
class FreshRow:
    file: str
    tier: str
    updated: str
    days: int


def parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def scan_pages(root: Path, current_version: str) -> dict[str, list[object]]:
    today = date.today()
    current_tuple = parse_version(current_version)
    results: dict[str, list[object]] = {"stale": [], "drift": [], "missing": [], "fresh": []}

    for page in sorted(root.glob("*.html")):
        text = page.read_text(encoding="utf-8")
        tier_match = TIER_RE.search(text)
        if not tier_match:
            continue

        updated_match = UPDATED_RE.search(text)
        version_match = VERSION_RE.search(text)
        if not updated_match or not version_match:
            missing_bits: list[str] = []
            if not updated_match:
                missing_bits.append("Updated")
            if not version_match:
                missing_bits.append("Game Version")
            if len(missing_bits) == 2:
                reason = "no .article-meta Updated or Game Version value"
            else:
                reason = f"no .article-meta {missing_bits[0]} value"
            results["missing"].append(MissingRow(page.name, reason))
            continue

        tier = tier_match.group(1)
        updated = updated_match.group(1)
        verified = version_match.group(1)
        updated_date = datetime.strptime(updated, "%Y-%m-%d").date()
        days = (today - updated_date).days

        if parse_version(verified) < current_tuple:
            results["drift"].append(DriftRow(page.name, tier, verified, current_version))
        elif days > STALE_THRESHOLD_DAYS[tier]:
            results["stale"].append(StaleRow(page.name, tier, updated, days))
        else:
            results["fresh"].append(FreshRow(page.name, tier, updated, days))

    return results


def format_rows(rows: list[object], renderer) -> list[str]:
    if not rows:
        return []
    width = max(len(getattr(row, "file")) for row in rows)
    return [renderer(row, width) for row in rows]


def render_human(results: dict[str, list[object]]) -> str:
    lines: list[str] = []
    sections = [
        ("== STALE (verified > N days) ==", results["stale"], lambda row, width: f"- {row.file.ljust(width)} [{row.tier}]  last updated: {row.updated} ({row.days} days)"),
        ("== VERSION DRIFT (verified against older EA) ==", results["drift"], lambda row, width: f"- {row.file.ljust(width)} [{row.tier}]  verified: EA {row.verified}  current: EA {row.current}"),
        ("== MISSING META (cannot audit) ==", results["missing"], lambda row, width: f"- {row.file.ljust(width)} {row.reason}"),
        ("== FRESH ==", results["fresh"], lambda row, width: f"- {row.file.ljust(width)} [{row.tier}]  last updated: {row.updated} ({row.days} days)"),
    ]
    for heading, rows, renderer in sections:
        rendered = format_rows(rows, renderer)
        if not rendered:
            continue
        if lines:
            lines.append("")
        lines.append(heading)
        lines.extend(rendered)

    total = sum(len(results[key]) for key in ("stale", "drift", "missing", "fresh"))
    if lines:
        lines.append("")
    lines.append(
        f"Audit complete: {total} files | {len(results['stale'])} stale | {len(results['drift'])} drift | {len(results['missing'])} missing | {len(results['fresh'])} fresh"
    )
    return "\n".join(lines)


def render_json(results: dict[str, list[object]], current_version: str) -> str:
    payload = {
        "audit_date": date.today().isoformat(),
        "current_ea_version": current_version,
        "stale": [asdict(row) for row in results["stale"]],
        "drift": [asdict(row) for row in results["drift"]],
        "missing": [asdict(row) for row in results["missing"]],
        "fresh": [asdict(row) for row in results["fresh"]],
    }
    return json.dumps(payload, indent=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-version", default=CURRENT_EA_VERSION, help="override the baked-in current EA version (e.g. 0.2)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON to stdout instead of the human report")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        parse_version(args.current_version)
        results = scan_pages(project_root(), args.current_version)
        output = render_json(results, args.current_version) if args.json else render_human(results)
        print(output)
        return 0
    except Exception as exc:
        print(f"pages-freshness.py error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
