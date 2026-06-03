#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:
    BeautifulSoup = None

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".source-monitor-cache"
LAST_SEEN_PATH = CACHE_DIR / "last-seen.json"
USER_AGENT = "paralives-source-monitor/0.1 by huanglin (https://paralivesguide.help)"
REQUEST_TIMEOUT = 15
MONTH_PATTERN = (
    r"January|February|March|April|May|June|July|August|September|October|November|December"
)
DATE_RE = re.compile(rf"\b({MONTH_PATTERN})\s+\d{{1,2}},\s+\d{{4}}\b")
TAG_RE = re.compile(r"<[^>]+>")

KEYWORDS = [
    "trait",
    "traits",
    "personality",
    "Paramaker",
    "Para",
    "Paras",
    "career",
    "careers",
    "hobby",
    "hobbies",
    "build mode",
    "building",
    "Early Access",
    "patch",
    "hotfix",
    "fix",
    "fixed",
    "added",
    "removed",
    "balance",
    "crash",
    "save",
    "performance",
    "EA",
    "0.1",
    "0.2",
    "0.3",
    "0.4",
    "0.5",
    "0.1.0",
    "0.1.1",
    "0.1.2",
    "0.1.3",
]

SOURCES = {
    "paralives_news": {
        "kind": "html",
        "url": "https://paralives.com/news",
        "enabled": True,
        "trust": "official",
    },
    "paralives_development": {
        "kind": "html",
        "url": "https://paralives.com/development",
        "enabled": False,
        "trust": "official",
    },
    "steam_news": {
        "kind": "steam",
        "appid": 1118520,  # Paralives' Steam app id
        "enabled": True,
        "trust": "official",
    },
    "reddit": {
        "kind": "reddit",
        "subreddit": "paralives",
        "enabled": False,
        "trust": "community",
    },
    "youtube": {
        "kind": "youtube_rss",
        "channel_id": "",  # TO FILL: visit https://www.youtube.com/@ParalivesStudio,
        # view page source, search for "channelId" or "externalId"
        # (string starting with "UC..."), paste here. Then flip enabled to True.
        "enabled": False,
        "trust": "official",
    },
    "bluesky": {
        "kind": "bluesky",
        "handle": "",  # TO FILL: Paralives Studio's Bluesky handle, e.g. "paralivesstudio.bsky.social".
        # If Paralives Studio is not on Bluesky, leave empty and enabled=False.
        "enabled": False,
        "trust": "official",
    },
}


@dataclass
class SourceItem:
    source: str
    title: str
    url: str
    date: str
    excerpt: str
    cursor: str
    sort_ts: float
    matched: list[str]
    trust: str = ""
    version: str | None = None


@dataclass
class SourceResult:
    status: str
    trust: str
    fetched: int = 0
    matched_count: int = 0
    items: list[SourceItem] | None = None
    error: str | None = None
    skip_reason: str | None = None
    cursor_field: str | None = None
    latest_cursor: str | None = None


def http_get(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def parse_isoish_datetime(value: str) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        parsed = None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_human_date(value: str) -> datetime | None:
    if not value or value == "unknown":
        return None
    stripped = value.strip()
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(stripped, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    parsed = parse_isoish_datetime(stripped)
    if parsed is not None:
        return parsed
    return None


def sort_timestamp(date_text: str) -> float:
    parsed = parse_human_date(date_text)
    if parsed is None:
        return 0.0
    return parsed.timestamp()


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_tags(value: str) -> str:
    return collapse_whitespace(TAG_RE.sub(" ", value))


def keyword_matches(text: str, keyword: str) -> bool:
    if is_case_sensitive_keyword(keyword):
        return keyword in text
    return keyword.lower() in text.lower()


def is_case_sensitive_keyword(keyword: str) -> bool:
    return bool(keyword) and keyword[0].isupper()


def matched_keywords(text: str) -> list[str]:
    matches = []
    for keyword in KEYWORDS:
        if keyword_matches(text, keyword):
            matches.append(keyword)
    return matches


EA_VERSION_RE = re.compile(r"\bEA\s*(\d+\.\d+(?:\.\d+)?)\b")
BARE_VERSION_RE = re.compile(r"\b(0\.\d+(?:\.\d+)?)\b")


def extract_version(title: str, excerpt: str, *, source_name: str) -> str | None:
    combined = f"{title}\n{excerpt}"
    match = EA_VERSION_RE.search(combined)
    if match:
        return match.group(1)
    bare_match = BARE_VERSION_RE.search(title)
    if bare_match:
        return bare_match.group(1)
    return None


def validate_source_configs() -> None:
    for name, config in SOURCES.items():
        trust = config.get("trust")
        if trust not in {"official", "community"}:
            raise ValueError(f"Source '{name}' must declare trust as 'official' or 'community'.")


def read_json_url(url: str) -> object:
    return json.loads(http_get(url))


def absolute_paralives_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return f"https://paralives.com{href}"
    return f"https://paralives.com/{href.lstrip('/')}"


def choose_excerpt(container) -> str:
    paragraphs = []
    for node in container.find_all(["p", "div"]):
        text = collapse_whitespace(node.get_text(" ", strip=True))
        if len(text) < 40:
            continue
        if text not in paragraphs:
            paragraphs.append(text)
        if len(paragraphs) == 2:
            break
    if paragraphs:
        return " ".join(paragraphs)
    return collapse_whitespace(container.get_text(" ", strip=True))


def fetch_official_html_source(name: str, config: dict[str, object]) -> list[SourceItem]:
    if BeautifulSoup is None:
        raise RuntimeError(f"beautifulsoup4 is required to scan {name}; install scripts/requirements.txt")
    soup = BeautifulSoup(http_get(str(config["url"])), "html.parser")
    items = []
    seen_urls = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/news/" not in href:
            continue
        title = collapse_whitespace(anchor.get_text(" ", strip=True))
        if not title:
            continue
        url = absolute_paralives_url(href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        container = anchor
        for parent in anchor.parents:
            if getattr(parent, "name", None) in {"article", "li", "section", "div"}:
                parent_text = collapse_whitespace(parent.get_text(" ", strip=True))
                if len(parent_text) >= max(60, len(title) + 20):
                    container = parent
                    break
        date_text = "unknown"
        time_tag = container.find("time")
        if time_tag is not None:
            date_candidate = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
            parsed = parse_human_date(collapse_whitespace(date_candidate))
            if parsed is not None:
                date_text = parsed.date().isoformat()
            else:
                date_text = collapse_whitespace(date_candidate) or "unknown"
        if date_text == "unknown":
            container_text = collapse_whitespace(container.get_text(" ", strip=True))
            match = DATE_RE.search(container_text)
            if match:
                parsed = parse_human_date(match.group(0))
                if parsed is not None:
                    date_text = parsed.date().isoformat()
                else:
                    date_text = match.group(0)
        excerpt = choose_excerpt(container)
        if excerpt == title:
            excerpt = ""
        items.append(
            SourceItem(
                source=name,
                title=title,
                url=url,
                date=date_text,
                excerpt=excerpt,
                cursor=url,
                sort_ts=sort_timestamp(date_text),
                matched=[],
                trust=str(config["trust"]),
                version=extract_version(title, excerpt, source_name=name),
            )
        )
    return items


def fetch_steam_news(name: str, config: dict[str, object]) -> list[SourceItem]:
    payload = read_json_url(
        f"https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid={config['appid']}&count=50&format=json"
    )
    items = []
    appnews = payload.get("appnews", {}) if isinstance(payload, dict) else {}
    for entry in appnews.get("newsitems", []) if isinstance(appnews, dict) else []:
        if not isinstance(entry, dict):
            continue
        stamp = int(entry.get("date", 0) or 0)
        parsed = datetime.fromtimestamp(stamp, tz=timezone.utc) if stamp else None
        items.append(
            SourceItem(
                source=name,
                title=collapse_whitespace(str(entry.get("title", ""))),
                url=collapse_whitespace(str(entry.get("url", ""))),
                date=parsed.date().isoformat() if parsed is not None else "unknown",
                excerpt=strip_tags(str(entry.get("contents", ""))),
                cursor=collapse_whitespace(str(entry.get("gid", ""))),
                sort_ts=parsed.timestamp() if parsed is not None else 0.0,
                matched=[],
                trust=str(config["trust"]),
                version=extract_version(
                    collapse_whitespace(str(entry.get("title", ""))),
                    strip_tags(str(entry.get("contents", ""))),
                    source_name=name,
                ),
            )
        )
    return items


def fetch_reddit(name: str, config: dict[str, object]) -> list[SourceItem]:
    payload = read_json_url(f"https://www.reddit.com/r/{config['subreddit']}/new.json?limit=100")
    items = []
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    children = data.get("children", []) if isinstance(data, dict) else []
    for child in children:
        entry = child.get("data", {}) if isinstance(child, dict) else {}
        if not isinstance(entry, dict):
            continue
        stamp = float(entry.get("created_utc", 0) or 0)
        parsed = datetime.fromtimestamp(stamp, tz=timezone.utc) if stamp else None
        permalink = collapse_whitespace(str(entry.get("permalink", "")))
        items.append(
            SourceItem(
                source=name,
                title=collapse_whitespace(str(entry.get("title", ""))),
                url=f"https://www.reddit.com{permalink}",
                date=parsed.date().isoformat() if parsed is not None else "unknown",
                excerpt=collapse_whitespace(str(entry.get("selftext", ""))),
                cursor=f"t3_{collapse_whitespace(str(entry.get('id', '')))}",
                sort_ts=parsed.timestamp() if parsed is not None else 0.0,
                matched=[],
                trust=str(config["trust"]),
                version=extract_version(
                    collapse_whitespace(str(entry.get("title", ""))),
                    collapse_whitespace(str(entry.get("selftext", ""))),
                    source_name=name,
                ),
            )
        )
    return items


def fetch_youtube_rss(name: str, config: dict[str, object]) -> list[SourceItem]:
    root = ET.fromstring(
        http_get(f"https://www.youtube.com/feeds/videos.xml?channel_id={config['channel_id']}")
    )
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    items = []
    for entry in root.findall("atom:entry", ns):
        title = collapse_whitespace(entry.findtext("atom:title", default="", namespaces=ns))
        link = entry.find("atom:link", ns)
        published = collapse_whitespace(entry.findtext("atom:published", default="", namespaces=ns))
        parsed = parse_human_date(published)
        description = collapse_whitespace(entry.findtext("media:group/media:description", default="", namespaces=ns))
        video_id = collapse_whitespace(entry.findtext("yt:videoId", default="", namespaces=ns))
        items.append(
            SourceItem(
                source=name,
                title=title,
                url=link.get("href", "") if link is not None else "",
                date=parsed.date().isoformat() if parsed is not None else "unknown",
                excerpt=description,
                cursor=video_id,
                sort_ts=parsed.timestamp() if parsed is not None else 0.0,
                matched=[],
                trust=str(config["trust"]),
                version=extract_version(title, description, source_name=name),
            )
        )
    return items


def bluesky_post_url(handle: str, uri: str) -> str:
    rkey = uri.rstrip("/").split("/")[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def fetch_bluesky(name: str, config: dict[str, object]) -> list[SourceItem]:
    payload = read_json_url(
        "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
        f"?actor={config['handle']}&limit=50"
    )
    items = []
    feed = payload.get("feed", []) if isinstance(payload, dict) else []
    for entry in feed:
        post = entry.get("post", {}) if isinstance(entry, dict) else {}
        record = post.get("record", {}) if isinstance(post, dict) else {}
        if not isinstance(post, dict) or not isinstance(record, dict):
            continue
        text = collapse_whitespace(str(record.get("text", "")))
        published = collapse_whitespace(str(record.get("createdAt", "")))
        parsed = parse_human_date(published)
        uri = collapse_whitespace(str(post.get("uri", "")))
        title = text if len(text) <= 120 else f"{text[:117].rstrip()}..."
        items.append(
            SourceItem(
                source=name,
                title=title,
                url=bluesky_post_url(str(config["handle"]), uri),
                date=parsed.date().isoformat() if parsed is not None else "unknown",
                excerpt=text,
                cursor=uri,
                sort_ts=parsed.timestamp() if parsed is not None else 0.0,
                matched=[],
                trust=str(config["trust"]),
                version=extract_version(title, text, source_name=name),
            )
        )
    return items


FETCHERS = {
    "html": fetch_official_html_source,
    "steam": fetch_steam_news,
    "reddit": fetch_reddit,
    "youtube_rss": fetch_youtube_rss,
    "bluesky": fetch_bluesky,
}

CURSOR_FIELDS = {
    "paralives_news": "last_seen_url",
    "paralives_development": "last_seen_url",
    "steam_news": "last_seen_gid",
    "reddit": "last_seen_id",
    "youtube": "last_seen_video_id",
    "bluesky": "last_seen_uri",
}


def load_last_seen() -> dict[str, dict[str, str]]:
    if not LAST_SEEN_PATH.exists():
        return {}
    try:
        payload = json.loads(LAST_SEEN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_last_seen(state: dict[str, dict[str, str]]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = LAST_SEEN_PATH.with_name(f"{LAST_SEEN_PATH.name}.tmp")
    temp_path.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(temp_path, LAST_SEEN_PATH)


def source_skip_reason(name: str, config: dict[str, object]) -> str | None:
    if name == "youtube" and not str(config.get("channel_id", "")).strip():
        return "channel_id not configured"
    if name == "bluesky" and not str(config.get("handle", "")).strip():
        return "handle not configured"
    if not bool(config.get("enabled")):
        return "disabled"
    return None


def filter_new_items(
    items: list[SourceItem],
    *,
    cursor_field: str,
    previous_state: dict[str, str] | None,
    since_date: datetime | None,
    full: bool,
) -> list[SourceItem]:
    if full:
        return items
    if since_date is not None:
        filtered = []
        for item in items:
            parsed = parse_human_date(item.date)
            if parsed is None or parsed >= since_date:
                filtered.append(item)
        return filtered
    if not previous_state:
        return items
    last_seen_cursor = str(previous_state.get(cursor_field, "")).strip()
    if not last_seen_cursor:
        return items
    fresh_items = []
    found_cursor = False
    for item in items:
        if item.cursor == last_seen_cursor:
            found_cursor = True
            break
        fresh_items.append(item)
    if found_cursor:
        return fresh_items
    return items


def format_summary_line(name: str, result: SourceResult) -> str:
    if result.status == "ok":
        return f"- {name}: {result.fetched} posts fetched, {result.matched_count} matched"
    if result.status == "skipped":
        return f"- {name}: skipped ({result.skip_reason})"
    return f"- {name}: fetch failed ({result.error})"


def truncate_excerpt(value: str, limit: int = 400) -> str:
    text = collapse_whitespace(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def render_source_section(name: str, result: SourceResult) -> list[str]:
    lines = [f"### {name}", ""]
    if result.status == "error":
        lines.append(f"**FETCH FAILED**: {result.error}")
        return lines
    for item in result.items or []:
        lines.append(f"#### {item.title}")
        lines.append(f"- **URL**: {item.url}")
        lines.append(f"- **Date**: {item.date}")
        lines.append(f"- **Matched**: {', '.join(item.matched)}")
        lines.append(f"- **Excerpt**: {truncate_excerpt(item.excerpt)}")
        lines.append("")
    if not (result.items or []):
        lines.append("_No matching posts._")
    return lines


def render_digest(scan_started: datetime, results: dict[str, SourceResult]) -> str:
    lines = [
        f"# Paralives source-monitor digest — {scan_started.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"**Keywords**: {', '.join(KEYWORDS)}",
        "",
        "**Scan summary**:",
    ]
    for name in results:
        lines.append(format_summary_line(name, results[name]))

    grouped_names = {
        "official": [name for name, result in results.items() if result.trust == "official"],
        "community": [name for name, result in results.items() if result.trust == "community"],
    }

    lines.extend(["", "---", "", "## Official sources (citable)", ""])
    if grouped_names["official"]:
        for name in grouped_names["official"]:
            lines.extend(render_source_section(name, results[name]))
            lines.append("")
    else:
        lines.append("_No items this scan._")

    lines.extend(["---", "", "## Community leads (verify before citing)", ""])
    lines.append("Community items are leads only. Do not cite directly in articles without confirming from an official source.")
    lines.append("")
    if grouped_names["community"]:
        for name in grouped_names["community"]:
            lines.extend(render_source_section(name, results[name]))
            lines.append("")
    else:
        lines.append("_No items this scan._")

    lines.append("")
    return "\n".join(lines)


def save_digest(scan_started: datetime, digest: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest_path = CACHE_DIR / f"digest-{scan_started.date().isoformat()}.md"
    digest_path.write_text(digest, encoding="utf-8")
    return digest_path


def save_json_digest(scan_started: datetime, payload: dict[str, object]) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest_path = CACHE_DIR / f"digest-{scan_started.date().isoformat()}.json"
    digest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return digest_path


def build_json_digest(scan_started: datetime, results: dict[str, SourceResult]) -> dict[str, object]:
    payload: dict[str, object] = {
        "scan_started": scan_started.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "keywords": KEYWORDS,
        "results": {},
    }
    result_payload: dict[str, object] = {}
    for name, result in results.items():
        entry: dict[str, object] = {
            "status": result.status,
            "trust": result.trust,
            "fetched": result.fetched,
            "matched_count": result.matched_count,
            "items": [],
        }
        if result.status == "skipped":
            entry["error"] = None
            entry["skip_reason"] = result.skip_reason
        elif result.status == "error":
            entry["error"] = result.error
            entry["skip_reason"] = None
        else:
            entry["error"] = None
            entry["skip_reason"] = None
        entry["items"] = [
            {
                "title": item.title,
                "url": item.url,
                "date": item.date,
                "excerpt": item.excerpt,
                "matched": item.matched,
                "trust": item.trust,
                "version": item.version,
            }
            for item in (result.items or [])
        ]
        result_payload[name] = entry
    payload["results"] = result_payload
    return payload


def scan_sources(args: argparse.Namespace) -> int:
    validate_source_configs()
    since_date = parse_human_date(args.since) if args.since else None
    if args.since and since_date is None:
        print("--since must be in YYYY-MM-DD format.", file=sys.stderr)
        return 2
    scan_started = datetime.now(timezone.utc)
    last_seen = load_last_seen()
    results = {}
    new_state = dict(last_seen)
    selected_sources = [args.source] if args.source else list(SOURCES.keys())

    for name in selected_sources:
        config = SOURCES[name]
        cursor_field = CURSOR_FIELDS[name]
        skip_reason = source_skip_reason(name, config)
        if skip_reason is not None:
            results[name] = SourceResult(
                status="skipped",
                trust=str(config["trust"]),
                skip_reason=skip_reason,
            )
            continue
        try:
            fetcher = FETCHERS[str(config["kind"])]
            fetched_items = fetcher(name, config)
            fetched_items.sort(key=lambda item: item.sort_ts, reverse=True)
            fresh_items = filter_new_items(
                fetched_items,
                cursor_field=cursor_field,
                previous_state=last_seen.get(name),
                since_date=since_date,
                full=bool(args.full),
            )
            matched_items = []
            for item in fresh_items:
                combined = f"{item.title}\n{item.excerpt}"
                matched = matched_keywords(combined)
                if matched:
                    item.matched = matched
                    matched_items.append(item)
            latest_cursor = fetched_items[0].cursor if fetched_items else None
            results[name] = SourceResult(
                status="ok",
                trust=str(config["trust"]),
                fetched=len(fetched_items),
                matched_count=len(matched_items),
                items=matched_items,
                cursor_field=cursor_field,
                latest_cursor=latest_cursor,
            )
            if latest_cursor:
                new_state[name] = {
                    cursor_field: latest_cursor,
                    "scanned_at": scan_started.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                }
        except Exception as exc:
            print(f"[{name}] fetch failed: {exc}", file=sys.stderr)
            results[name] = SourceResult(
                status="error",
                trust=str(config["trust"]),
                error=str(exc),
            )

    digest = render_digest(scan_started, results)
    digest_path = save_digest(scan_started, digest)
    if args.format == "json":
        save_json_digest(scan_started, build_json_digest(scan_started, results))
    write_last_seen(new_state)
    print(f"Wrote digest to {digest_path}")
    return 0


def most_recent_digest_path() -> Path | None:
    candidates = sorted(CACHE_DIR.glob("digest-*.md"))
    return candidates[-1] if candidates else None


def report_digest(args: argparse.Namespace) -> int:
    validate_source_configs()
    if args.date:
        digest_path = CACHE_DIR / f"digest-{args.date}.md"
    else:
        digest_path = most_recent_digest_path()
    if digest_path is None or not digest_path.exists():
        print("No digest file found.", file=sys.stderr)
        return 1
    sys.stdout.write(digest_path.read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan official Paralives sources for keyword matches and write a markdown digest."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser(
        "scan",
        help="Fetch enabled sources, filter by keywords, and write today's markdown digest.",
    )
    scan_parser.add_argument(
        "--source",
        choices=sorted(SOURCES.keys()),
        help="Only scan one configured source.",
    )
    scan_parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="Include posts on or after this date, ignoring last-seen state.",
    )
    scan_parser.add_argument(
        "--full",
        action="store_true",
        help="Ignore last-seen state and --since; include every item returned by each source.",
    )
    scan_parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Write markdown only (default) or markdown plus a sibling JSON digest.",
    )
    scan_parser.set_defaults(func=scan_sources)

    report_parser = subparsers.add_parser(
        "report",
        help="Print the most recent digest, or a specific digest by date.",
    )
    report_parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Print the digest file for a specific date.",
    )
    report_parser.set_defaults(func=report_digest)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
