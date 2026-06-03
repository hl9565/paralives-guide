#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".source-monitor-cache"
PAGE_PATH = REPO_ROOT / "patch-notes.html"
AUTO_RE = re.compile(
    r"(?P<start>\s*<!-- patch-notes:auto-start -->\n)(?P<body>.*?)(?P<end>\s*<!-- patch-notes:auto-end -->)",
    re.S,
)
DATE_MODIFIED_RE = re.compile(r'("dateModified":\s*")[0-9]{4}-[0-9]{2}-[0-9]{2}(")')
UPDATED_RE = re.compile(r"(<span>Updated:\s*)[0-9]{4}-[0-9]{2}-[0-9]{2}(</span>)")
FOOTNOTE_RE = re.compile(
    r"(Checked against the official <span translate=\"no\">Steam Community Announcements</span> listing and official <span translate=\"no\">paralives.com</span> pages as of )"
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"(?:\..*?</p>)",
    re.S,
)
STEAM_OFFICIAL_MARKER = "steam_community_announcements"
PATCH_TITLE_RE = re.compile(r"\b(patch notes|hotfix|known issues)\b", re.I)
LAUNCH_TITLE_RE = re.compile(r"paralives is out now", re.I)
VERSION_RE = re.compile(r"\b(0\.\d+(?:\.\d+)?[a-z]?)\b", re.I)


@dataclass(frozen=True)
class PatchItem:
    title: str
    url: str
    posted: str
    excerpt: str
    source: str


def latest_json_digest() -> Path | None:
    candidates = sorted(CACHE_DIR.glob("digest-*.json"))
    return candidates[-1] if candidates else None


def item_source_allowed(source_name: str, url: str) -> bool:
    if source_name == "paralives_news":
        return True
    if source_name == "steam_news":
        return STEAM_OFFICIAL_MARKER in url
    return False


def is_patch_item(title: str) -> bool:
    return bool(PATCH_TITLE_RE.search(title) or LAUNCH_TITLE_RE.search(title))


def dedupe_key(item: dict[str, object]) -> str:
    title = str(item.get("title", "")).strip().lower()
    version = version_label(title)
    if version:
        return f"version:{version.lower()}"
    return f"title:{title}"


def version_label(title: str) -> str | None:
    match = VERSION_RE.search(title)
    if match:
        return match.group(1)
    if LAUNCH_TITLE_RE.search(title):
        return "0.1.0"
    return None


def collect_patch_items(payload: dict[str, object]) -> list[PatchItem]:
    results = payload.get("results", {})
    if not isinstance(results, dict):
        raise ValueError("digest JSON has no results object")

    chosen: dict[str, PatchItem] = {}
    for source_name, source_payload in results.items():
        if not isinstance(source_payload, dict):
            continue
        if source_payload.get("status") != "ok" or source_payload.get("trust") != "official":
            continue
        items = source_payload.get("items", [])
        if not isinstance(items, list):
            continue
        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            title = str(raw_item.get("title", "")).strip()
            url = str(raw_item.get("url", "")).strip()
            if not title or not url:
                continue
            if not item_source_allowed(str(source_name), url) or not is_patch_item(title):
                continue
            key = dedupe_key(raw_item)
            candidate = PatchItem(
                title=title,
                url=url,
                posted=str(raw_item.get("date", "unknown")).strip() or "unknown",
                excerpt=str(raw_item.get("excerpt", "")).strip(),
                source=str(source_name),
            )
            existing = chosen.get(key)
            if existing is None or candidate.source == "paralives_news":
                chosen[key] = candidate

    return sorted(chosen.values(), key=lambda item: item.posted, reverse=True)


def version_id(label: str) -> str:
    return "v" + re.sub(r"[^0-9a-z]+", "-", label.lower()).strip("-")


def label_for(item: PatchItem) -> str:
    title = item.title.lower()
    if LAUNCH_TITLE_RE.search(item.title):
        return "Launch"
    if "known issues" in title:
        return "Known issues"
    if "hotfix" in title:
        return "Hotfix"
    if "patch" in title:
        return "Patch"
    return "Official update"


def heading_for(item: PatchItem) -> str:
    version = version_label(item.title)
    if version:
        return f"Version {version}"
    return item.title


def summary_for(item: PatchItem) -> str:
    version = version_label(item.title)
    source_name = "paralives.com" if item.source == "paralives_news" else "Steam"
    if LAUNCH_TITLE_RE.search(item.title):
        return (
            f"Paralives entered Steam Early Access on {item.posted}. "
            "This launch entry is kept as the baseline for the 0.1 patch line."
        )
    if "hotfix" in item.title.lower():
        return (
            f"The official {source_name} item for {html.escape(item.title)} was posted on {item.posted}. "
            "It is a narrow follow-up fix to the launch patch line, so this archive links to the official source instead of reposting the full note."
        )
    if version:
        return (
            f"The official {source_name} patch notes for {html.escape(item.title)} were posted on {item.posted}. "
            "The entry belongs to the Early Access 0.1 line and is summarized here only at routing level."
        )
    return (
        f"The official {source_name} item {html.escape(item.title)} was posted on {item.posted}. "
        "No exact version label is exposed in the title, so the archive keeps the entry under its official title."
    )


def detail_for(item: PatchItem) -> str:
    excerpt = item.excerpt
    if LAUNCH_TITLE_RE.search(item.title):
        return (
            "The official launch notice confirms the public Early Access starting point; later patch and hotfix entries are organized above it in reverse date order."
        )
    if "known issues" in item.title.lower():
        return (
            "The source is a launch-period known-issues notice rather than a numbered patch, so it stays separate from versioned patch notes."
        )
    if excerpt:
        cleaned = re.sub(r"\s+", " ", excerpt)
        if len(cleaned) > 220:
            cleaned = cleaned[:217].rstrip() + "..."
        return html.escape(cleaned)
    return "The official listing did not expose enough body text for a reliable summary."


def render_patch_block(items: list[PatchItem]) -> str:
    lines = ["      <div class=\"version-stack\">"]
    if not items:
        lines.extend(
            [
                "        <section class=\"version-card\" id=\"no-patches-yet\">",
                "          <div class=\"label\">Status</div>",
                "          <h3>No official patch entries found</h3>",
                "          <p class=\"version-meta\">Checked latest digest</p>",
                "          <p>The source monitor did not find official patch-note or hotfix items in the current digest.</p>",
                "        </section>",
            ]
        )
    for index, item in enumerate(items):
        heading = heading_for(item)
        anchor = version_id(heading.replace("Version ", ""))
        if "known issues" in item.title.lower():
            anchor = "vknown-issues"
        if index:
            lines.append("")
        lines.extend(
            [
                f"        <section class=\"version-card\" id=\"{anchor}\">",
                f"          <div class=\"label\">{html.escape(label_for(item))}</div>",
                f"          <h3>{html.escape(heading)}</h3>",
                f"          <p class=\"version-meta\">Posted {html.escape(item.posted)}</p>",
                f"          <p>{summary_for(item)}</p>",
                f"          <p>{detail_for(item)}</p>",
                f"          <a class=\"source-link\" href=\"{html.escape(item.url, quote=True)}\">Official source</a>",
                "        </section>",
            ]
        )
    lines.append("      </div>")
    return "\n".join(lines)


def update_version_index(text: str, items: list[PatchItem]) -> str:
    links = []
    for item in items:
        heading = heading_for(item)
        anchor = version_id(heading.replace("Version ", ""))
        label = heading.replace("Version ", "")
        if "known issues" in item.title.lower():
            anchor = "vknown-issues"
            label = "Known issues"
        links.append(f'        <a href="#{anchor}">{html.escape(label)}</a>')
    block = "      <div class=\"version-index\">\n" + "\n".join(links) + "\n      </div>"
    return re.sub(r"      <div class=\"version-index\">\n.*?\n      </div>", block, text, count=1, flags=re.S)


def update_page(page_path: Path, items: list[PatchItem], checked_date: str) -> None:
    text = page_path.read_text(encoding="utf-8")
    if items:
        block = render_patch_block(items)
        if not AUTO_RE.search(text):
            raise ValueError("patch-notes auto marker block not found")
        text = AUTO_RE.sub(lambda m: f"{m.group('start')}{block}\n      <!-- patch-notes:auto-end -->", text, count=1)
        text = update_version_index(text, items)
    text = DATE_MODIFIED_RE.sub(rf"\g<1>{checked_date}\2", text, count=1)
    text = UPDATED_RE.sub(rf"\g<1>{checked_date}\2", text, count=1)
    refresh_runbook = (
        f"Checked against the official <span translate=\"no\">Steam Community Announcements</span> listing and official "
        f"<span translate=\"no\">paralives.com</span> pages as of {checked_date}. Version cards inside the marker block "
        "are generated by <code>scripts/update-patch-notes.py</code> from official-tier source-monitor digests: official "
        "<span translate=\"no\">paralives.com</span> pages and official <span translate=\"no\">Steam Community Announcements</span> only. "
        "To refresh after an official patch, run <code>python3 scripts/source-monitor.py scan --format json</code>, then "
        "<code>python3 scripts/update-patch-notes.py</code>."
    )
    text = FOOTNOTE_RE.sub(lambda m: refresh_runbook + "</p>", text, count=1)
    page_path.write_text(text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update patch-notes.html from a source-monitor JSON digest.")
    parser.add_argument("--digest", type=Path, help="Path to a digest-YYYY-MM-DD.json file. Defaults to the latest JSON digest.")
    parser.add_argument("--page", type=Path, default=PAGE_PATH, help="Patch notes HTML page to update.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    digest_path = args.digest or latest_json_digest()
    if digest_path is None or not digest_path.exists():
        print("No JSON digest found. Run source-monitor.py scan --format json first.", file=sys.stderr)
        return 1
    payload = json.loads(digest_path.read_text(encoding="utf-8"))
    checked_date = str(payload.get("scan_started", date.today().isoformat()))[:10]
    try:
        items = collect_patch_items(payload)
        update_page(args.page, items, checked_date)
    except Exception as exc:
        print(f"update-patch-notes.py error: {exc}", file=sys.stderr)
        return 1
    print(f"Updated {args.page} with {len(items)} official patch entries from {digest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
