#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib import error, parse, request

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".workshop-cache"
PAGE_PATH = REPO_ROOT / "mods.html"
BROWSE_URL = "https://steamcommunity.com/workshop/browse/?appid=1118520&browsesort=totaluniquesubscribers&section=readytouseitems"
DETAILS_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
USER_AGENT = "Mozilla/5.0 (compatible; ParalivesGuideWorkshopSnapshot/1.0; +https://paralivesguide.help/)"
AUTO_RE = re.compile(
    r"(?P<start>\s*<!-- workshop-snapshot:auto-start -->\n)(?P<body>.*?)(?P<end>\s*<!-- workshop-snapshot:auto-end -->)",
    re.S,
)
SNAPSHOT_SECTION_RE = re.compile(
    r"(?P<head>\s*<h2 class=\"sec\" id=\"snapshot\">Most-subscribed mods on Steam Workshop right now</h2>\n)"
    r"(?P<body>.*?)(?=\n\s*<h2 class=\"sec\" id=\"risks\">)",
    re.S,
)


@dataclass(frozen=True)
class WorkshopItem:
    publishedfileid: str
    title: str
    subscriptions: int
    tags: list[str]
    updated: str
    url: str


def fetch_text(url: str, *, timeout: int) -> str:
    req = request.Request(url, headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def post_form(url: str, fields: dict[str, str], *, timeout: int) -> dict[str, object]:
    encoded = parse.urlencode(fields).encode("utf-8")
    req = request.Request(
        url,
        data=encoded,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def collect_ids(html_text: str, limit: int) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"sharedfiles/filedetails/\?id=(\d+)", html_text):
        item_id = match.group(1)
        if item_id in seen:
            continue
        seen.add(item_id)
        ids.append(item_id)
        if len(ids) >= limit:
            break
    return ids


def int_field(raw: object, default: int = 0) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def date_from_unix(raw: object) -> str:
    timestamp = int_field(raw)
    if timestamp <= 0:
        return "unknown"
    return datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()


def usable_item(raw: dict[str, object]) -> bool:
    if int_field(raw.get("result")) != 1:
        return False
    if not str(raw.get("title", "")).strip():
        return False
    if int_field(raw.get("banned")):
        return False
    visibility = raw.get("visibility")
    return visibility is None or int_field(visibility) == 0


def details_for(ids: list[str], *, details_url: str, timeout: int) -> list[WorkshopItem]:
    fields = {"itemcount": str(len(ids))}
    for index, item_id in enumerate(ids):
        fields[f"publishedfileids[{index}]"] = item_id
    payload = post_form(details_url, fields, timeout=timeout)
    details = payload.get("response", {}).get("publishedfiledetails", [])
    if not isinstance(details, list):
        raise ValueError("Steam details response did not include publishedfiledetails")

    items: list[WorkshopItem] = []
    for raw in details:
        if not isinstance(raw, dict) or not usable_item(raw):
            continue
        item_id = str(raw.get("publishedfileid", "")).strip()
        if not item_id:
            continue
        tag_names = []
        tags = raw.get("tags", [])
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, dict):
                    tag_name = str(tag.get("tag", "")).strip()
                    if tag_name:
                        tag_names.append(tag_name)
        items.append(
            WorkshopItem(
                publishedfileid=item_id,
                title=str(raw.get("title", "")).strip(),
                subscriptions=int_field(raw.get("subscriptions")),
                tags=tag_names,
                updated=date_from_unix(raw.get("time_updated")),
                url=f"https://steamcommunity.com/sharedfiles/filedetails/?id={item_id}",
            )
        )
    items.sort(key=lambda item: item.subscriptions, reverse=True)
    return items


def render_snapshot(items: list[WorkshopItem], snapshot_date: str) -> str:
    rows = []
    for item in items:
        tags = ", ".join(item.tags) if item.tags else "untagged"
        rows.append(
            "          <tr>"
            f"<td><span translate=\"no\">{html.escape(item.title)}</span></td>"
            f"<td>{item.subscriptions:,}</td>"
            f"<td><span translate=\"no\">{html.escape(tags)}</span></td>"
            f"<td>{html.escape(item.updated)}</td>"
            f"<td><a href=\"{html.escape(item.url, quote=True)}\"><span translate=\"no\">View on Steam Workshop</span></a></td>"
            "</tr>"
        )
    return "\n".join(
        [
            "      <p>This snapshot is ordered strictly by <span translate=\"no\">Steam</span>'s own subscriber count. Subscriber count is a popularity signal on <span translate=\"no\">Steam Workshop</span>, not a recommendation, quality ranking, or endorsement from this site.</p>",
            f"      <p class=\"snapshot-date\">Snapshot as of {snapshot_date}. Refresh manually with <code>python3 scripts/workshop-snapshot.py</code>.</p>",
            "      <div class=\"factbox workshop-snapshot\">",
            "        <h3>Most-subscribed public Workshop items</h3>",
            "        <table>",
            "          <tr><th>Mod title</th><th>Subscribers</th><th>Tags</th><th>Updated</th><th>Link</th></tr>",
            *rows,
            "        </table>",
            "      </div>",
            "      <p>The table is generated from public <span translate=\"no\">Steam Workshop</span> data and intentionally omits author names and preview images. Item pages show those details on <span translate=\"no\">Steam</span>.</p>",
            "      <p>Refresh runbook: run <code>python3 scripts/workshop-snapshot.py</code> after checking that the public Workshop page is reachable. The command fetches public item IDs, writes a dated JSON file under <code>.workshop-cache/</code>, and rewrites only this marker block.</p>",
        ]
    )


def update_page(page_path: Path, items: list[WorkshopItem], snapshot_date: str) -> None:
    text = page_path.read_text(encoding="utf-8")
    block = render_snapshot(items, snapshot_date)
    if AUTO_RE.search(text):
        text = AUTO_RE.sub(lambda m: f"{m.group('start')}{block}\n      <!-- workshop-snapshot:auto-end -->", text, count=1)
    elif SNAPSHOT_SECTION_RE.search(text):
        replacement = (
            r"\g<head>      <!-- workshop-snapshot:auto-start -->\n"
            + block.replace("\\", "\\\\")
            + "\n      <!-- workshop-snapshot:auto-end -->\n"
        )
        text = SNAPSHOT_SECTION_RE.sub(replacement, text, count=1)
    else:
        raise ValueError("mods.html snapshot section or marker block not found")
    text = text.replace(
        '      <div class="note"><b>Status:</b> Workshop data could not be fetched during this implementation because the <span translate="no">Steam Workshop</span> request did not return in time. The snapshot section below links the hub without inventing rows.</div>\n\n',
        "",
    )
    page_path.write_text(text, encoding="utf-8")


def write_cache(items: list[WorkshopItem], snapshot_date: str) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"snapshot-{snapshot_date}.json"
    payload = {
        "snapshot_date": snapshot_date,
        "source": BROWSE_URL,
        "items": [asdict(item) for item in items],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update mods.html from public Steam Workshop subscriber data.")
    parser.add_argument("--page", type=Path, default=PAGE_PATH, help="HTML page to update.")
    parser.add_argument("--browse-url", default=BROWSE_URL, help="Workshop browse URL.")
    parser.add_argument("--details-url", default=DETAILS_URL, help="Steam GetPublishedFileDetails URL.")
    parser.add_argument("--id-limit", type=int, default=15, help="Number of browse-page item IDs to request.")
    parser.add_argument("--row-limit", type=int, default=10, help="Number of rows to render.")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    snapshot_date = date.today().isoformat()
    try:
        browse_html = fetch_text(args.browse_url, timeout=args.timeout)
        ids = collect_ids(browse_html, args.id_limit)
        if not ids:
            raise ValueError("no Workshop published-file IDs found on browse page")
        items = details_for(ids, details_url=args.details_url, timeout=args.timeout)[: args.row_limit]
        if not items:
            raise ValueError("Steam details response returned zero usable public Workshop items")
        cache_path = write_cache(items, snapshot_date)
        update_page(args.page, items, snapshot_date)
    except (OSError, error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        print(f"workshop-snapshot.py error: {exc}", file=sys.stderr)
        return 1
    print(f"Updated {args.page} with {len(items)} Workshop rows from {cache_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
