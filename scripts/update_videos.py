#!/usr/bin/env python3
"""Build videos.json from channels.yaml.

For every channel listed in channels.yaml (and in the lists it includes from
other repos), list the channel's regular videos (no Shorts, no livestreams)
with yt-dlp. When yt-dlp fails, for example because YouTube blocks the
machine running this, fall back to the channel's RSS feed (newest 15 videos)
merged with the previous videos.json, so a bad day never wipes the site.

Usage:
    python scripts/update_videos.py [--config channels.yaml]
        [--previous FILE_OR_URL ...] [--out site/videos.json]

Needs PyYAML, and yt-dlp on the PATH (without yt-dlp only RSS is used).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import yaml

FORMAT_VERSION = 1
DEFAULT_VIDEOS_PER_CHANNEL = 200
USER_AGENT = "unrecommended (+https://github.com/topics/unrecommended)"
HTTP_TIMEOUT = 30
YTDLP_TIMEOUT = 600
WORKERS = 4

CHANNEL_ID_RE = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
VIDEO_ID_RE = re.compile(r"^[0-9A-Za-z_-]{11}$")
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
}
# Paths that are YouTube pages, not legacy custom channel URLs.
NOT_CHANNEL_PATHS = {
    "watch",
    "shorts",
    "playlist",
    "results",
    "feed",
    "live",
    "embed",
    "redirect",
    "premium",
    "account",
    "hashtag",
    "post",
}
GITHUB_REPO_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/"
    r"(?P<owner>[A-Za-z0-9-]+)/(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?/?"
    r"(?:#(?P<group>.+))?$"
)
SHORT_REPO_RE = re.compile(r"^(?P<owner>[A-Za-z0-9-]+)/(?P<repo>[A-Za-z0-9._-]+)(?:#(?P<group>.+))?$")


class ConfigError(Exception):
    """A problem in channels.yaml that the user has to fix."""


# --------------------------------------------------------------------------
# Logging: plain text locally, annotations + a summary page on GitHub Actions.

ON_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"::warning::{msg}" if ON_ACTIONS else f"WARNING: {msg}", flush=True)


def error(msg: str, line: int | None = None, file: str | None = None) -> None:
    if ON_ACTIONS:
        where = ""
        if file:
            where = f" file={file}" + (f",line={line}" if line else "")
        print(f"::error{where}::{msg}", flush=True)
    else:
        loc = f"{file}:{line}: " if file and line else ""
        print(f"ERROR: {loc}{msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# Channel references: turn whatever the user pasted into something usable.


@dataclass
class ChannelRef:
    """One channel entry as written in a channels.yaml."""

    raw: str
    url: str  # canonical https://www.youtube.com/... page of the channel
    channel_id: str | None  # known when the user gave a /channel/UC... link
    name: str | None = None  # optional display name override
    origin: str = "local"  # "local" or "owner/repo" for included lists


def parse_channel(entry, where: str) -> ChannelRef:
    """Parse one entry of a group: a string, or a mapping with url/name."""
    name = None
    if isinstance(entry, dict):
        raw = entry.get("url") or entry.get("channel")
        name = entry.get("name")
        if not isinstance(raw, str):
            raise ConfigError(f"{where}: an entry needs a `url:` with the channel link")
        if name is not None and not isinstance(name, str):
            raise ConfigError(f"{where}: `name:` must be text")
    elif isinstance(entry, str):
        raw = entry
    else:
        raise ConfigError(f"{where}: expected a channel link, got {entry!r}")

    raw = raw.strip()
    if not raw:
        raise ConfigError(f"{where}: empty channel entry")

    if CHANNEL_ID_RE.match(raw):
        return ChannelRef(raw, f"https://www.youtube.com/channel/{raw}", raw, name)
    if raw.startswith("@"):
        handle = raw[1:].split("/")[0]
        return ChannelRef(raw, f"https://www.youtube.com/@{handle}", None, name)

    text = raw if "://" in raw else "https://" + raw
    try:
        parsed = urllib.parse.urlsplit(text)
    except ValueError:
        parsed = None
    if not parsed or parsed.hostname not in YOUTUBE_HOSTS:
        raise ConfigError(
            f"{where}: {raw!r} is not a YouTube channel link. Use a link like "
            "https://www.youtube.com/@name or just @name"
        )

    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        raise ConfigError(f"{where}: {raw!r} is the YouTube home page, not a channel")
    first = parts[0]
    if first.startswith("@"):
        return ChannelRef(raw, f"https://www.youtube.com/{first}", None, name)
    if first == "channel" and len(parts) > 1 and CHANNEL_ID_RE.match(parts[1]):
        cid = parts[1]
        return ChannelRef(raw, f"https://www.youtube.com/channel/{cid}", cid, name)
    if first in ("c", "user") and len(parts) > 1:
        return ChannelRef(raw, f"https://www.youtube.com/{first}/{parts[1]}", None, name)
    if first in ("watch", "shorts", "live", "embed") or parsed.hostname == "youtu.be":
        raise ConfigError(
            f"{where}: {raw!r} is a link to a video. Open the video, click the "
            "channel's name under it, and use that page's link instead"
        )
    if first in NOT_CHANNEL_PATHS:
        raise ConfigError(f"{where}: {raw!r} is not a channel link")
    # Legacy custom URL: youtube.com/SomeName
    return ChannelRef(raw, f"https://www.youtube.com/{first}", None, name)


# --------------------------------------------------------------------------
# Config: channels.yaml, plus the lists it includes.


@dataclass
class Include:
    raw: str
    owner: str
    repo: str
    group: str | None

    @property
    def key(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def raw_url(self) -> str:
        return f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/HEAD/channels.yaml"


@dataclass
class Config:
    site: dict
    videos_per_channel: int
    groups: list[tuple[str, list[ChannelRef]]]
    includes: list[Include] = field(default_factory=list)


def parse_include(entry, where: str) -> Include:
    if not isinstance(entry, str):
        raise ConfigError(f"{where}: expected a GitHub repo link, got {entry!r}")
    text = entry.strip()
    m = GITHUB_REPO_RE.match(text) or SHORT_REPO_RE.match(text)
    if not m:
        raise ConfigError(
            f"{where}: {entry!r} is not a GitHub repo link. Use a link like "
            "https://github.com/alice/unrecommended (add #group for one group)"
        )
    group = m.group("group")
    return Include(text, m.group("owner"), m.group("repo"), group.strip() if group else None)


def load_yaml_text(text: str, filename: str):
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        problem = getattr(exc, "problem", None) or str(exc)
        where = f"{filename} line {line}" if line else filename
        err = ConfigError(
            f"{where}: not valid YAML ({problem}). Check the indentation and "
            "that every channel line starts with '- '"
        )
        err.line = line
        raise err from exc


def parse_groups(data, filename: str, origin: str) -> list[tuple[str, list[ChannelRef]]]:
    groups_data = data.get("groups")
    if groups_data is None:
        return []
    if not isinstance(groups_data, dict):
        raise ConfigError(
            f"{filename}: `groups:` must hold group names, each followed by its list of channels"
        )
    groups = []
    for raw_name, raw_entries in groups_data.items():
        gname = str(raw_name).strip()
        entries = [] if raw_entries is None else raw_entries
        if not isinstance(entries, list):
            raise ConfigError(
                f"{filename}: group {gname!r} must be a list of channels, one "
                "per line, each starting with '- '"
            )
        refs = []
        for i, entry in enumerate(entries, 1):
            ref = parse_channel(entry, f"{filename}, group {gname!r}, entry {i}")
            ref.origin = origin
            refs.append(ref)
        groups.append((gname, refs))
    return groups


IMAGE_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(svg|png|jpe?g|gif|webp|ico)$", re.IGNORECASE)
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def parse_image(site_data: dict, key: str, default: str, filename: str) -> str:
    """A picture setting: a file name in the site/ folder, an https:// link,
    or "none" (only sensible for the logo). Returns "" for none."""
    value = site_data.get(key, default)
    if value is None or value is False or (isinstance(value, str) and value.strip().lower() in ("", "none")):
        return ""
    if not isinstance(value, str):
        raise ConfigError(f"{filename}: `{key}:` must be a file name such as {default}")
    value = value.strip()
    if value.startswith("site/"):
        value = value[len("site/") :]
    if IMAGE_FILE_RE.match(value) or re.match(r"^https://[^\s\"'<>]+$", value):
        return value
    raise ConfigError(
        f"{filename}: `{key}: {value}` should be the name of a picture you uploaded to the "
        f"site folder (like my-{key}.png), a link starting with https://, or none"
    )


def parse_color(site_data: dict, key: str, filename: str) -> str:
    value = site_data.get(key)
    if value is None or value == "":
        return ""
    if isinstance(value, str) and COLOR_RE.match(value.strip()):
        return value.strip().lower()
    raise ConfigError(f'{filename}: `{key}:` must be a colour written like "#b4462b" (with the quotes)')


def parse_config(text: str, filename: str = "channels.yaml") -> Config:
    data = load_yaml_text(text, filename)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{filename} must have `site:` and `groups:` sections")

    known = {"site", "groups", "include"}
    for key in data:
        if key not in known:
            warn(f"{filename}: unknown section {key!r} ignored (known: site, groups, include)")

    site_data = data.get("site") or {}
    if not isinstance(site_data, dict):
        raise ConfigError(f"{filename}: `site:` must hold settings such as `title:`")
    site = {
        "title": str(site_data.get("title") or "unrecommended"),
        "description": str(site_data.get("description") or ""),
        "about": str(site_data.get("about") or "").strip(),
        "kid_safe": bool(site_data.get("kid_safe", False)),
        "logo": parse_image(site_data, "logo", "logo.svg", filename),
        "favicon": parse_image(site_data, "favicon", "favicon.svg", filename),
        "accent": parse_color(site_data, "accent", filename),
    }
    vpc = site_data.get("videos_per_channel", DEFAULT_VIDEOS_PER_CHANNEL)
    if not isinstance(vpc, int) or isinstance(vpc, bool) or vpc < 1:
        raise ConfigError(f"{filename}: `videos_per_channel:` must be a whole number above 0")

    groups = parse_groups(data, filename, "local")

    includes_data = data.get("include") or []
    if not isinstance(includes_data, list):
        raise ConfigError(f"{filename}: `include:` must be a list of GitHub repo links")
    includes = [parse_include(e, f"{filename}, include {i}") for i, e in enumerate(includes_data, 1)]

    if not groups and not includes:
        raise ConfigError(f"{filename} lists no channels: add some under `groups:`")
    return Config(site, vpc, groups, includes)


def http_get(url: str, attempts: int = 6) -> bytes:
    """GET a URL. Retries, because YouTube's feeds often answer 404 or 500
    for a request that works a second later."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if attempt == attempts or exc.code not in (404, 429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, OSError):
            if attempt == attempts:
                raise
        time.sleep(min(attempt, 3))
    raise AssertionError("unreachable")


def resolve_includes(config: Config, cache: dict, fetch=http_get) -> list[tuple[str, list[ChannelRef]]]:
    """Fetch the included lists. Returns their groups; updates `cache`.

    Includes are followed one level deep: an included list's own `include:`
    is ignored. A list that can't be fetched or parsed falls back to the copy
    saved in the previous videos.json.
    """
    result = []
    for inc in config.includes:
        text = None
        try:
            text = fetch(inc.raw_url).decode("utf-8")
        except (urllib.error.URLError, OSError, UnicodeDecodeError) as exc:
            warn(f"include {inc.raw}: could not download it ({exc}); using the last saved copy")
        groups = None
        if text is not None:
            try:
                groups = parse_groups(load_yaml_text(text, inc.key) or {}, inc.key, inc.key)
                cache[inc.key] = text
            except ConfigError as exc:
                warn(f"include {inc.raw}: {exc}; using the last saved copy")
            else:
                data = yaml.safe_load(text) or {}
                if data.get("include"):
                    log(f"include {inc.raw}: its own `include:` list is not followed (one level only)")
        if groups is None:
            saved = cache.get(inc.key)
            if saved is None:
                warn(f"include {inc.raw}: no saved copy either, skipping it")
                continue
            try:
                groups = parse_groups(yaml.safe_load(saved) or {}, inc.key, inc.key)
            except (ConfigError, yaml.YAMLError):
                warn(f"include {inc.raw}: the saved copy is broken too, skipping it")
                continue
        if inc.group is not None:
            picked = [g for g in groups if g[0].casefold() == inc.group.casefold()]
            if not picked:
                names = ", ".join(g[0] for g in groups) or "none"
                warn(f"include {inc.raw}: no group named {inc.group!r} (groups: {names})")
            groups = picked
        result.extend(groups)
    return result


def merge_groups(local, included) -> list[tuple[str, list[ChannelRef]]]:
    """Local groups first, then included ones; groups with the same name merge."""
    merged: dict[str, list[ChannelRef]] = {}
    keys: dict[str, str] = {}  # casefolded name -> name as first written
    for gname, refs in list(local) + list(included):
        key = gname.casefold()
        if key not in keys:
            keys[key] = gname
            merged[gname] = []
        merged[keys[key]].extend(refs)
    return list(merged.items())


# --------------------------------------------------------------------------
# Fetching videos.


@dataclass
class Video:
    id: str
    title: str
    date: str | None  # YYYY-MM-DD
    seconds: int | None = None

    def to_json(self, channel_id: str) -> dict:
        out = {"id": self.id, "channel": channel_id, "title": self.title, "date": self.date}
        if self.seconds:
            out["seconds"] = self.seconds
        return out


@dataclass
class Listing:
    channel_id: str | None
    name: str | None
    handle: str | None
    videos: list[Video]


def _date_from_timestamp(ts) -> str | None:
    if not isinstance(ts, (int, float)):
        return None
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")


def run_ytdlp(url: str, limit: int) -> dict:
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
        "--force-ipv4",
        "--playlist-end",
        str(limit),
        "--extractor-args",
        "youtubetab:approximate_date",
        url.rstrip("/") + "/videos",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=YTDLP_TIMEOUT, check=False)
    if proc.returncode != 0:
        lines = [ln for ln in proc.stderr.strip().splitlines() if ln.strip()]
        raise RuntimeError(lines[-1] if lines else f"yt-dlp exited with {proc.returncode}")
    return json.loads(proc.stdout)


def parse_ytdlp(data: dict) -> Listing:
    videos = []
    for entry in data.get("entries") or []:
        vid = entry.get("id")
        if not isinstance(vid, str) or not VIDEO_ID_RE.match(vid):
            continue
        if entry.get("live_status") in ("is_upcoming", "is_live"):
            continue
        if entry.get("availability") in ("subscriber_only", "premium_only", "needs_auth"):
            continue
        duration = entry.get("duration")
        videos.append(
            Video(
                id=vid,
                title=str(entry.get("title") or ""),
                date=_date_from_timestamp(entry.get("timestamp")),
                seconds=int(duration) if isinstance(duration, (int, float)) else None,
            )
        )
    cid = data.get("channel_id") or data.get("id")
    if not (isinstance(cid, str) and CHANNEL_ID_RE.match(cid)):
        cid = None
    handle = data.get("uploader_id")
    return Listing(
        channel_id=cid,
        name=data.get("channel") or data.get("uploader"),
        handle=handle if isinstance(handle, str) and handle.startswith("@") else None,
        videos=videos,
    )


ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"


def parse_rss(xml_bytes: bytes) -> Listing:
    root = ET.fromstring(xml_bytes)
    name = root.findtext(f"{ATOM}title")
    videos = []
    for entry in root.findall(f"{ATOM}entry"):
        vid = entry.findtext(f"{YT}videoId")
        if not vid or not VIDEO_ID_RE.match(vid):
            continue
        link = entry.find(f"{ATOM}link[@rel='alternate']")
        if link is not None and "/shorts/" in (link.get("href") or ""):
            continue
        published = entry.findtext(f"{ATOM}published") or ""
        videos.append(
            Video(
                id=vid,
                title=entry.findtext(f"{ATOM}title") or "",
                date=published[:10] if re.match(r"\d{4}-\d{2}-\d{2}", published) else None,
            )
        )
    return Listing(channel_id=None, name=name, handle=None, videos=videos)


def fetch_rss(channel_id: str, fetch=http_get, attempts: int = 6) -> Listing:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    listing = parse_rss(fetch(url, attempts=attempts))
    listing.channel_id = channel_id
    return listing


def find_channel_id(url: str, fetch=http_get) -> str | None:
    """Last resort: read the channel ID from the channel's web page."""
    html = fetch(url).decode("utf-8", "replace")
    for pattern in (
        r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[0-9A-Za-z_-]{22})"',
        r'"externalId":"(UC[0-9A-Za-z_-]{22})"',
        r'"channelId":"(UC[0-9A-Za-z_-]{22})"',
    ):
        m = re.search(pattern, html)
        if m:
            return m.group(1)
    return None


@dataclass
class ChannelResult:
    ref: ChannelRef
    channel_id: str | None
    name: str | None
    handle: str | None
    videos: list[Video]
    source: str  # "yt-dlp", "rss", "previous" or "none"
    problem: str | None = None


def update_channel(
    ref: ChannelRef, limit: int, previous: Previous, use_ytdlp: bool, fetch=http_get, ytdlp=run_ytdlp
) -> ChannelResult:
    cid = ref.channel_id or previous.ids.get(ref.url)
    problems = []

    fresh = None
    if use_ytdlp:
        try:
            fresh = parse_ytdlp(ytdlp(ref.url, limit))
            cid = fresh.channel_id or cid
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
            msg = str(exc)
            if "confirm you" in msg and "bot" in msg:
                msg = "YouTube asked to confirm this is not a bot (it blocks some servers)"
            problems.append(f"yt-dlp: {msg}")

    if cid is None:
        try:
            cid = find_channel_id(ref.url, fetch)
        except (urllib.error.URLError, OSError) as exc:
            problems.append(f"channel page: {exc}")
    if cid is None:
        problems.append("could not find the channel's ID")
        return ChannelResult(ref, None, ref.name, None, [], "none", "; ".join(problems))

    # With yt-dlp's list, the feed only adds exact dates for the newest
    # videos, so a quick try is enough and a failure doesn't matter.
    rss = None
    try:
        rss = fetch_rss(cid, fetch, attempts=2 if fresh is not None else 6)
    except (urllib.error.URLError, OSError, ET.ParseError) as exc:
        if fresh is None:
            problems.append(f"RSS: {exc}")

    old = previous.videos_by_channel.get(cid, [])
    old_channel = previous.channels.get(cid, {})
    videos = merge_videos(fresh, rss, old, limit)
    if fresh is not None:
        source = "yt-dlp"
    elif rss is not None:
        source = "rss"
    elif old:
        source = "previous"
    else:
        source = "none"

    name = ref.name or (fresh and fresh.name) or (rss and rss.name) or old_channel.get("name") or ref.raw
    handle = (fresh and fresh.handle) or old_channel.get("handle")
    problem = "; ".join(problems) if (problems and fresh is None) else None
    return ChannelResult(ref, cid, name, handle, videos, source, problem)


def merge_videos(fresh: Listing | None, rss: Listing | None, old: list[dict], limit: int) -> list[Video]:
    """Combine the three sources for one channel.

    yt-dlp's list, when there is one, decides which videos exist (so deleted
    videos go away). Dates: the RSS feed's exact date wins, then the date
    already saved, then yt-dlp's approximate one ("3 weeks ago").
    """
    rss_by_id = {v.id: v for v in (rss.videos if rss else [])}
    old_by_id = {v["id"]: v for v in old if isinstance(v, dict) and isinstance(v.get("id"), str)}

    def best_date(vid: str, fallback: str | None) -> str | None:
        if vid in rss_by_id and rss_by_id[vid].date:
            return rss_by_id[vid].date
        return old_by_id.get(vid, {}).get("date") or fallback

    if fresh is not None:
        out = []
        for v in fresh.videos:
            seconds = v.seconds or old_by_id.get(v.id, {}).get("seconds")
            out.append(Video(v.id, v.title, best_date(v.id, v.date), seconds))
        return out[:limit]

    combined: dict[str, Video] = {}
    for vid, o in old_by_id.items():
        if VIDEO_ID_RE.match(vid):
            combined[vid] = Video(vid, str(o.get("title") or ""), o.get("date"), o.get("seconds"))
    for v in rss_by_id.values():
        seconds = combined[v.id].seconds if v.id in combined else None
        combined[v.id] = Video(v.id, v.title or combined.get(v.id, v).title, best_date(v.id, None), seconds)
    ordered = sorted(combined.values(), key=lambda v: v.date or "", reverse=True)
    return ordered[:limit]


# --------------------------------------------------------------------------
# Previous output, so a failed fetch keeps what we had.


@dataclass
class Previous:
    videos_by_channel: dict[str, list[dict]] = field(default_factory=dict)
    channels: dict[str, dict] = field(default_factory=dict)
    ids: dict[str, str] = field(default_factory=dict)  # channel URL -> UC id
    includes: dict[str, str] = field(default_factory=dict)  # owner/repo -> yaml text

    def add(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        seen = {v["id"] for vs in self.videos_by_channel.values() for v in vs}
        for v in data.get("videos") or []:
            if isinstance(v, dict) and isinstance(v.get("channel"), str) and v.get("id") not in seen:
                self.videos_by_channel.setdefault(v["channel"], []).append(v)
                seen.add(v.get("id"))
        for cid, ch in (data.get("channels") or {}).items():
            if isinstance(ch, dict):
                self.channels.setdefault(cid, ch)
        cache = data.get("cache") or {}
        for url, cid in (cache.get("ids") or {}).items():
            if isinstance(cid, str) and CHANNEL_ID_RE.match(cid):
                self.ids.setdefault(url, cid)
        for key, text in (cache.get("includes") or {}).items():
            if isinstance(text, str):
                self.includes.setdefault(key, text)


def load_previous(sources: list[str]) -> Previous:
    prev = Previous()
    for src in sources:
        try:
            if re.match(r"https?://", src):
                raw = http_get(src)
            else:
                path = Path(src)
                if not path.exists():
                    continue
                raw = path.read_bytes()
            prev.add(json.loads(raw))
            log(f"previous videos loaded from {src}")
        except (urllib.error.URLError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            log(f"no previous videos from {src} ({exc})")
    return prev


# --------------------------------------------------------------------------
# Main.


def build(
    config: Config,
    previous: Previous,
    use_ytdlp: bool,
    fetch=None,
    ytdlp=None,
    workers: int = WORKERS,
) -> tuple[dict, list[ChannelResult]]:
    fetch = fetch or http_get
    ytdlp = ytdlp or run_ytdlp
    include_cache = dict(previous.includes)
    included = resolve_includes(config, include_cache, fetch)
    # Keep saved copies only of the lists still included.
    wanted = {inc.key for inc in config.includes}
    include_cache = {k: v for k, v in include_cache.items() if k in wanted}
    groups = merge_groups(config.groups, included)

    # One fetch per distinct channel URL.
    refs: dict[str, ChannelRef] = {}
    for _, grefs in groups:
        for ref in grefs:
            if ref.url not in refs or (ref.origin == "local" and refs[ref.url].origin != "local"):
                refs[ref.url] = ref

    log(f"updating {len(refs)} channels")
    results: dict[str, ChannelResult] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                update_channel, ref, config.videos_per_channel, previous, use_ytdlp, fetch, ytdlp
            ): url
            for url, ref in refs.items()
        }
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            results[futures[fut]] = res
            label = res.name or res.ref.raw
            log(f"  {label}: {len(res.videos)} videos ({res.source})")
            if res.problem:
                warn(f"{res.ref.raw}: {res.problem}")

    # Channels listed locally win over the same channel in an included list.
    local_ids = {
        results[r.url].channel_id
        for _, grefs in groups
        for r in grefs
        if r.origin == "local" and results[r.url].channel_id
    }
    out_groups = []
    for gname, grefs in groups:
        ids = []
        for r in grefs:
            cid = results[r.url].channel_id
            if cid is None or cid in ids:
                continue
            if r.origin != "local" and cid in local_ids:
                continue
            ids.append(cid)
        if ids:
            out_groups.append({"name": gname, "channels": ids})

    used = {cid for g in out_groups for cid in g["channels"]}
    channels = {}
    videos = []
    seen_videos = set()
    for res in results.values():
        cid = res.channel_id
        if cid not in used or cid in channels:
            continue
        url = (
            f"https://www.youtube.com/{res.handle}"
            if res.handle
            else f"https://www.youtube.com/channel/{cid}"
        )
        channels[cid] = {"name": res.name, "url": url, "source": res.source}
        if res.handle:
            channels[cid]["handle"] = res.handle
        for v in res.videos:
            if v.id not in seen_videos:
                seen_videos.add(v.id)
                videos.append(v.to_json(cid))
    videos.sort(key=lambda v: v["date"] or "", reverse=True)

    ids_cache = {url: res.channel_id for url, res in results.items() if res.channel_id}
    data = {
        "version": FORMAT_VERSION,
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site": config.site,
        "groups": out_groups,
        "channels": channels,
        "videos": videos,
        "cache": {"ids": ids_cache, "includes": include_cache},
    }
    return data, list(results.values())


def write_summary(results: list[ChannelResult], total: int) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [
        f"## {total} videos from {len(results)} channels",
        "",
        "| Channel | Videos | Source | Problem |",
        "|---|---:|---|---|",
    ]
    for res in sorted(results, key=lambda r: (r.name or r.ref.raw).casefold()):
        problem = (res.problem or "").replace("|", "\\|")
        lines.append(f"| {res.name or res.ref.raw} | {len(res.videos)} | {res.source} | {problem} |")
    lines += [
        "",
        (
            "Source: `yt-dlp` = full list; `rss` = YouTube blocked yt-dlp, so only "
            "the newest 15 videos were added to what the site already had; "
            "`previous` = nothing could be fetched, the site keeps its old list; "
            "`none` = no videos at all."
        ),
    ]
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", default="channels.yaml")
    parser.add_argument("--out", default="site/videos.json")
    parser.add_argument(
        "--previous",
        action="append",
        default=None,
        help="earlier videos.json (file or URL) to keep videos from; "
        "can be given more than once (default: the --out file)",
    )
    parser.add_argument("--no-ytdlp", action="store_true", help="use only the RSS feeds")
    args = parser.parse_args(argv)

    try:
        text = Path(args.config).read_text(encoding="utf-8")
    except OSError as exc:
        error(f"cannot read {args.config}: {exc}")
        return 1
    try:
        config = parse_config(text, Path(args.config).name)
    except ConfigError as exc:
        error(str(exc), getattr(exc, "line", None), args.config)
        return 1

    use_ytdlp = not args.no_ytdlp
    if use_ytdlp and shutil.which("yt-dlp") is None:
        warn("yt-dlp is not installed; using RSS feeds only (newest 15 videos per channel)")
        use_ytdlp = False

    previous = load_previous(args.previous if args.previous is not None else [args.out])
    data, results = build(config, previous, use_ytdlp)

    total = len(data["videos"])
    write_summary(results, total)
    if total == 0:
        error("no videos found for any channel; not writing an empty site")
        return 1

    out = Path(args.out)
    for key in ("logo", "favicon"):
        name = config.site[key]
        if name and not name.startswith("https://") and not (out.parent / name).exists():
            warn(f"site {key} {name!r} is not in the site folder; upload it there or fix the name")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(out)
    log(f"wrote {total} videos from {len(data['channels'])} channels to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
