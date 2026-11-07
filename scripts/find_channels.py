#!/usr/bin/env python3
"""Search YouTube for channels about a topic, to pick ones for channels.yaml.

Usage:
    python scripts/find_channels.py "steam trains" ["jazz piano" ...]
        [--limit 10] [--recent 3] [--json]

For each search it prints the channels YouTube finds, most relevant first:
the address to paste into channels.yaml, subscriber count, name and the
start of the channel's description. --recent N also lists each channel's N
newest regular videos (one extra request per channel), which shows whether
the channel is still active and what it actually posts.

Made for people and AI agents building a list: check the results instead of
guessing channel names from memory. Needs yt-dlp on the PATH.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.parse

from update_videos import CHANNEL_ID_RE, parse_ytdlp, run_ytdlp

CHANNEL_FILTER = "EgIQAg%3D%3D"  # YouTube's "type: channel" search filter


def search(query: str, limit: int) -> list[dict]:
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}&sp={CHANNEL_FILTER}"
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
        "--force-ipv4",
        "--playlist-end",
        str(limit),
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    if proc.returncode != 0:
        lines = [ln for ln in proc.stderr.splitlines() if ln.strip()]
        raise RuntimeError(lines[-1] if lines else f"yt-dlp exited with {proc.returncode}")
    found = []
    for e in json.loads(proc.stdout).get("entries") or []:
        cid = e.get("channel_id") or e.get("id")
        if not (isinstance(cid, str) and CHANNEL_ID_RE.match(cid)):
            continue
        handle = e.get("uploader_id") if str(e.get("uploader_id") or "").startswith("@") else None
        found.append(
            {
                "name": e.get("title") or e.get("channel") or "",
                "url": f"https://www.youtube.com/{handle}"
                if handle
                else f"https://www.youtube.com/channel/{cid}",
                "channel_id": cid,
                "subscribers": e.get("channel_follower_count"),
                "description": " ".join(str(e.get("description") or "").split()),
            }
        )
    return found


def recent_videos(url: str, n: int) -> list[dict]:
    listing = parse_ytdlp(run_ytdlp(url, n))
    return [{"title": v.title, "date": v.date} for v in listing.videos[:n]]


def subs(n) -> str:
    if not isinstance(n, int):
        return "?"
    for size, unit in ((1_000_000, "M"), (1_000, "k")):
        if n >= size:
            return f"{n / size:.1f}".rstrip("0").rstrip(".") + unit
    return str(n)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("queries", nargs="+", help="what to search for, one or more")
    parser.add_argument("--limit", type=int, default=10, help="channels per search (default 10)")
    parser.add_argument(
        "--recent", type=int, default=0, metavar="N", help="also list each channel's N newest videos"
    )
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)

    results = {}
    status = 0
    for query in args.queries:
        try:
            channels = search(query, args.limit)
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
            print(f"search {query!r} failed: {exc}", file=sys.stderr)
            status = 1
            continue
        if args.recent:
            for ch in channels:
                try:
                    ch["recent"] = recent_videos(ch["url"], args.recent)
                except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
                    ch["recent"] = []
                    ch["recent_error"] = str(exc)
        results[query] = channels

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return status
    for query, channels in results.items():
        print(f"\n# {query}")
        if not channels:
            print("  (no channels found)")
        for ch in channels:
            print(f"  - {ch['url']}   {subs(ch['subscribers'])} subscribers   {ch['name']}")
            if ch["description"]:
                print(f"      {ch['description'][:140]}")
            for v in ch.get("recent", []):
                print(f"      {v['date'] or '????-??-??'}  {v['title']}")
            if ch.get("recent_error"):
                print(f"      (could not list videos: {ch['recent_error']})")
    return status


if __name__ == "__main__":
    sys.exit(main())
