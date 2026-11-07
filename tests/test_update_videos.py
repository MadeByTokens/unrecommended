import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import update_videos as uv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CID_A = "UCaaaaaaaaaaaaaaaaaaaaaa"
CID_B = "UCbbbbbbbbbbbbbbbbbbbbbb"
CID_C = "UCcccccccccccccccccccccc"


# ---------------------------------------------------------------- channels


@pytest.mark.parametrize(
    ("raw", "url", "cid"),
    [
        ("@veritasium", "https://www.youtube.com/@veritasium", None),
        ("https://www.youtube.com/@veritasium", "https://www.youtube.com/@veritasium", None),
        ("youtube.com/@veritasium/videos", "https://www.youtube.com/@veritasium", None),
        ("https://m.youtube.com/@veritasium?si=x", "https://www.youtube.com/@veritasium", None),
        (CID_A, f"https://www.youtube.com/channel/{CID_A}", CID_A),
        (f"youtube.com/channel/{CID_A}/videos", f"https://www.youtube.com/channel/{CID_A}", CID_A),
        ("https://www.youtube.com/c/Numberphile", "https://www.youtube.com/c/Numberphile", None),
        ("https://www.youtube.com/user/numberphile", "https://www.youtube.com/user/numberphile", None),
        ("https://www.youtube.com/numberphile", "https://www.youtube.com/numberphile", None),
    ],
)
def test_parse_channel_forms(raw, url, cid):
    ref = uv.parse_channel(raw, "here")
    assert ref.url == url
    assert ref.channel_id == cid


def test_parse_channel_with_name():
    ref = uv.parse_channel({"url": "@x", "name": "Shown name"}, "here")
    assert (ref.url, ref.name) == ("https://www.youtube.com/@x", "Shown name")


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "link to a video"),
        ("https://youtu.be/dQw4w9WgXcQ", "not a YouTube channel link"),
        ("https://vimeo.com/someone", "not a YouTube channel link"),
        ("https://www.youtube.com/", "home page"),
        ("https://www.youtube.com/playlist?list=PL123", "not a channel link"),
        (42, "expected a channel link"),
        ({"name": "no url"}, "needs a `url:`"),
    ],
)
def test_parse_channel_errors(raw, message):
    with pytest.raises(uv.ConfigError, match=message):
        uv.parse_channel(raw, "here")


# ------------------------------------------------------------------ config


def test_demo_config_parses():
    config = uv.parse_config((ROOT / "channels.yaml").read_text())
    assert config.groups
    assert config.site["kid_safe"] is False
    assert config.includes == []


def test_config_yaml_error_has_line():
    text = "groups:\n  Science:\n    - @a\n   - @b\n"
    with pytest.raises(uv.ConfigError) as info:
        uv.parse_config(text)
    assert info.value.line is not None
    assert "line" in str(info.value)


def test_config_defaults_and_validation():
    config = uv.parse_config("groups:\n  G:\n    - '@a'\n")
    assert config.site["title"] == "unrecommended"
    assert config.videos_per_channel == uv.DEFAULT_VIDEOS_PER_CHANNEL
    with pytest.raises(uv.ConfigError, match="no channels"):
        uv.parse_config("site:\n  title: x\n")
    with pytest.raises(uv.ConfigError, match="whole number"):
        uv.parse_config("site:\n  videos_per_channel: many\ngroups:\n  G: ['@a']\n")
    with pytest.raises(uv.ConfigError, match="must be a list"):
        uv.parse_config("groups:\n  G: '@a'\n")


@pytest.mark.parametrize(
    ("raw", "key", "group"),
    [
        ("https://github.com/alice/unrecommended", "alice/unrecommended", None),
        ("https://github.com/alice/my-list.git", "alice/my-list", None),
        ("github.com/alice/unrecommended#Science", "alice/unrecommended", "Science"),
        ("alice/unrecommended#Making things", "alice/unrecommended", "Making things"),
    ],
)
def test_parse_include(raw, key, group):
    inc = uv.parse_include(raw, "here")
    assert (inc.key, inc.group) == (key, group)
    assert inc.raw_url == f"https://raw.githubusercontent.com/{key}/HEAD/channels.yaml"


def test_parse_include_error():
    with pytest.raises(uv.ConfigError, match="not a GitHub repo link"):
        uv.parse_include("https://gitlab.com/alice/x", "here")


# ---------------------------------------------------------------- includes

ALICE = """
groups:
  Science:
    - "@shared"
    - "@alicesci"
  Cooking:
    - "@chef"
include:
  - https://github.com/carol/unrecommended
"""


def fake_fetch_factory(pages):
    def fetch(url, attempts=6):
        if url in pages:
            value = pages[url]
            if isinstance(value, Exception):
                raise value
            return value.encode() if isinstance(value, str) else value
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    return fetch


ALICE_URL = "https://raw.githubusercontent.com/alice/unrecommended/HEAD/channels.yaml"


def test_includes_one_group_and_cache():
    config = uv.parse_config("include:\n  - https://github.com/alice/unrecommended#science\n")
    cache = {}
    groups = uv.resolve_includes(config, cache, fake_fetch_factory({ALICE_URL: ALICE}))
    assert [g[0] for g in groups] == ["Science"]
    assert [r.url for r in groups[0][1]] == [
        "https://www.youtube.com/@shared",
        "https://www.youtube.com/@alicesci",
    ]
    assert all(r.origin == "alice/unrecommended" for r in groups[0][1])
    assert cache["alice/unrecommended"] == ALICE


def test_include_uses_saved_copy_when_gone():
    config = uv.parse_config("include:\n  - alice/unrecommended\n")
    cache = {"alice/unrecommended": ALICE}
    groups = uv.resolve_includes(config, cache, fake_fetch_factory({}))
    assert [g[0] for g in groups] == ["Science", "Cooking"]


def test_include_missing_without_copy_is_skipped():
    config = uv.parse_config("include:\n  - alice/unrecommended\n")
    assert uv.resolve_includes(config, {}, fake_fetch_factory({})) == []


def test_merge_groups_by_name():
    local = [("Science", ["a"]), ("Mine", ["b"])]
    included = [("science", ["c"]), ("Cooking", ["d"])]
    assert uv.merge_groups(local, included) == [
        ("Science", ["a", "c"]),
        ("Mine", ["b"]),
        ("Cooking", ["d"]),
    ]


# ------------------------------------------------------------------ videos


def vid(n):
    return f"vid{n:08d}"


def test_merge_prefers_ytdlp_list_and_best_dates():
    fresh = uv.Listing(
        CID_A,
        "A",
        None,
        [
            uv.Video(vid(3), "three", "2026-11-01", 60),
            uv.Video(vid(2), "two new title", "2026-01-01", None),
        ],
    )
    rss = uv.Listing(CID_A, "A", None, [uv.Video(vid(3), "three", "2026-11-03")])
    old = [
        {"id": vid(2), "title": "two", "date": "2025-12-25", "seconds": 30},
        {"id": vid(1), "title": "deleted", "date": "2025-01-01"},
    ]
    out = uv.merge_videos(fresh, rss, old, 10)
    assert [(v.id, v.title, v.date, v.seconds) for v in out] == [
        (vid(3), "three", "2026-11-03", 60),
        (vid(2), "two new title", "2025-12-25", 30),
    ]


def test_merge_without_ytdlp_keeps_old_and_adds_rss():
    rss = uv.Listing(CID_A, "A", None, [uv.Video(vid(3), "three", "2026-11-03")])
    old = [
        {"id": vid(2), "title": "two", "date": "2025-12-25", "seconds": 30},
        {"id": vid(1), "title": "one", "date": "2025-01-01"},
    ]
    out = uv.merge_videos(None, rss, old, 2)
    assert [v.id for v in out] == [vid(3), vid(2)]


def test_parse_rss_skips_shorts():
    xml = f"""<?xml version="1.0"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
 <title>Chan</title>
 <entry><yt:videoId>{vid(1)}</yt:videoId><title>Short</title>
  <link rel="alternate" href="https://www.youtube.com/shorts/{vid(1)}"/>
  <published>2026-10-25T14:30:46+00:00</published></entry>
 <entry><yt:videoId>{vid(2)}</yt:videoId><title>Long</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v={vid(2)}"/>
  <published>2026-10-20T14:30:46+00:00</published></entry>
</feed>"""
    listing = uv.parse_rss(xml.encode())
    assert listing.name == "Chan"
    assert [(v.id, v.date) for v in listing.videos] == [(vid(2), "2026-10-20")]


def test_parse_ytdlp_skips_upcoming_and_bad_ids():
    data = {
        "channel_id": CID_A,
        "channel": "A",
        "uploader_id": "@a",
        "entries": [
            {"id": vid(1), "title": "ok", "timestamp": 1792281600, "duration": 61.0},
            {"id": vid(2), "title": "soon", "live_status": "is_upcoming"},
            {"id": "bad", "title": "bad id"},
        ],
    }
    listing = uv.parse_ytdlp(data)
    assert (listing.channel_id, listing.handle) == (CID_A, "@a")
    assert [(v.id, v.seconds) for v in listing.videos] == [(vid(1), 61)]
    assert listing.videos[0].date == "2026-10-18"


# ------------------------------------------------------------- end to end


def rss_xml(name, videos):
    entries = "".join(
        f"<entry><yt:videoId>{v}</yt:videoId><title>{v}</title>"
        f"<published>{d}T00:00:00+00:00</published></entry>"
        for v, d in videos
    )
    return (
        '<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
        f'xmlns="http://www.w3.org/2005/Atom"><title>{name}</title>{entries}</feed>'
    )


def feed(cid):
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"


def test_build_end_to_end():
    config = uv.parse_config(
        """
site: {title: Test, kid_safe: true}
groups:
  Science:
    - "@a"
    - url: "@b"
      name: Bee
include:
  - alice/unrecommended
"""
    )
    alice = 'groups:\n  Science:\n    - "@b"\n  Cooking:\n    - "@c"\n    - "@blocked"\n'
    channels = {
        "https://www.youtube.com/@a": (CID_A, "Ay", [vid(1)]),
        "https://www.youtube.com/@b": (CID_B, "B", [vid(2)]),
    }

    def ytdlp(url, limit):
        if url not in channels:
            raise RuntimeError("ERROR: Sign in to confirm you're not a bot")
        cid, name, ids = channels[url]
        return {
            "channel_id": cid,
            "channel": name,
            "uploader_id": url.rsplit("/", 1)[1],
            "entries": [{"id": i, "title": i, "timestamp": 1792281600} for i in ids],
        }

    pages = {
        ALICE_URL: alice,
        # @c: yt-dlp blocked, ID known from the previous run, RSS works.
        feed(CID_C): rss_xml("Cee", [(vid(3), "2026-11-02")]),
        # @blocked: yt-dlp blocked, no ID anywhere.
        "https://www.youtube.com/@blocked": "<html></html>",
    }
    previous = uv.Previous()
    previous.add(
        {
            "videos": [{"id": vid(4), "channel": CID_C, "title": "old c", "date": "2020-01-01"}],
            "cache": {"ids": {"https://www.youtube.com/@c": CID_C}},
        }
    )
    data, results = uv.build(config, previous, True, fake_fetch_factory(pages), ytdlp, workers=1)

    assert data["site"]["kid_safe"] is True
    # @b is both local and included: it stays in the local group only.
    assert data["groups"] == [
        {"name": "Science", "channels": [CID_A, CID_B]},
        {"name": "Cooking", "channels": [CID_C]},
    ]
    assert data["channels"][CID_B]["name"] == "Bee"
    assert data["channels"][CID_A]["url"] == "https://www.youtube.com/@a"
    assert data["channels"][CID_C]["source"] == "rss"
    assert [v["id"] for v in data["videos"]] == [vid(3), vid(1), vid(2), vid(4)]
    assert data["cache"]["includes"]["alice/unrecommended"] == alice
    blocked = [r for r in results if r.ref.raw == "@blocked"][0]
    assert blocked.source == "none" and "ID" in blocked.problem
    json.dumps(data)  # serialisable


def test_build_drops_saved_copies_of_removed_includes():
    config = uv.parse_config("groups:\n  G:\n    - '@a'\n")
    previous = uv.Previous(includes={"gone/list": ALICE})

    def ytdlp(url, limit):
        return {"channel_id": CID_A, "channel": "A", "entries": [{"id": vid(1), "title": "x"}]}

    data, _ = uv.build(config, previous, True, fake_fetch_factory({}), ytdlp, workers=1)
    assert data["cache"]["includes"] == {}


def test_main_refuses_to_write_empty_site(tmp_path, monkeypatch):
    cfg = tmp_path / "channels.yaml"
    cfg.write_text("groups:\n  G:\n    - '@nobody'\n")
    out = tmp_path / "videos.json"
    monkeypatch.setattr(uv, "http_get", fake_fetch_factory({}))
    assert uv.main(["--config", str(cfg), "--out", str(out), "--no-ytdlp"]) == 1
    assert not out.exists()


def test_main_reports_yaml_error(tmp_path, capsys):
    cfg = tmp_path / "channels.yaml"
    cfg.write_text("groups:\n  G:\n    - '@a'\n   - '@b'\n")
    assert uv.main(["--config", str(cfg), "--out", str(tmp_path / "v.json")]) == 1
    # stderr locally; stdout as an ::error annotation on GitHub Actions.
    captured = capsys.readouterr()
    assert "not valid YAML" in captured.out + captured.err
