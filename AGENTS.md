# AGENTS.md

Instructions for AI coding agents working with this repository. People
usually come here wanting **their own unrecommended site**: they tell you
what they like (or who the site is for) and you build it. That is task 1.
Task 2 is changing the template itself.

unrecommended turns a list of YouTube channels into a static website on
GitHub Pages that shows only those channels' videos: no comments, no
recommendations, no algorithm. The list lives in one file, `channels.yaml`.
A daily GitHub Action lists the videos with yt-dlp and publishes the site.

## Task 1: make a new unrecommended site for someone

### 1. Find out what they want

Ask briefly, then get going; a good first version beats a long interview.

- **What it's about**: interests, topics, favourite channels, things to avoid.
- **Who it's for**: themselves, a child, a parent, a friend, a class, a
  club. A gift, a joke, a critique or a statement are all fine uses (see
  "Rules" below).
- **Kid-safe?** Ask whenever a child may use it. `kid_safe: true` plays
  everything in a covered, full-screen player and removes links out.
- **Name**: the site title, and the repository name (lowercase with
  hyphens, for example `dad-tv`). The site will be at
  `https://<owner>.github.io/<repository>/`.
- **Where**: their GitHub account or an organisation they belong to.

Tell them early: **the repository and the site are public** (free GitHub
Pages), so the list is visible to anyone. Don't put a child's full name,
an address, a school or other personal details in it.

### 2. Create the repository from the template

```sh
gh repo create <owner>/<repository> --template MadeByTokens/unrecommended --public --clone
cd <repository>
python -m pip install -r requirements.txt     # yt-dlp and PyYAML
```

If `gh` can't use the template, fork MadeByTokens/unrecommended instead, or
ask the user to click **Use this template** on GitHub and give you the new
repository's name. Without `gh` or git at all, the README's "Make your own in
5 steps" is the manual path; you can still write `channels.yaml` for them to
paste.

### 3. Find real channels

**Never guess channel names or handles from memory.** Search, look at what
the channels actually post, then choose:

```sh
python scripts/find_channels.py "steam trains" "jazz piano" --limit 8 --recent 3
```

It prints each channel's address (paste that into `channels.yaml`), its
subscriber count, the start of its description and, with `--recent`, its
newest videos with dates. Use `--json` to read it programmatically.

Choosing well:
- Prefer channels that post regular videos (Shorts and livestreams are never
  listed) and are still active, unless an archive is the point.
- Read the recent titles: do they fit the brief and the audience? For a
  kid-safe site be conservative: skip channels with shock thumbnails,
  pranks, gambling, horror, mature language or heavy sponsorship.
- A good list has 2 to 6 groups of 2 to 8 channels each. Quality over
  quantity: every channel should be one the person would pick themselves.
- If the user named channels, still search for them to get the right
  address.

### 4. Write `channels.yaml`

It is the only file a new site needs. Its comments explain every setting,
and `channels.schema.json` describes it formally. Replace the demo content
entirely: the demo groups, channels, title, description and `about` text.

```yaml
site:
  title: Dad TV
  description: Trains, jazz and sawdust.
  about: |
    A birthday present for Dad: channels about steam railways, jazz piano and
    woodworking, and nothing else. Happy birthday!
  kid_safe: false
  videos_per_channel: 200
groups:
  Steam:
    - https://www.youtube.com/@SomeRealHandle   # from find_channels.py
  Jazz piano:
    - https://www.youtube.com/@AnotherRealHandle
```

- `about` is shown on the site's About page, like a channel description.
  Say what the list is and who it is for; for a joke or a critique, say so
  plainly there.
- Keep `logo`, `favicon` and `accent` as they are unless the user wants
  their own look (step 6).
- Keep the explanatory comments in the file: the user may edit it later in
  the GitHub website.

### 5. Check it

```sh
python scripts/update_videos.py --check     # every channel must say "ok"
```

It must end with `all N channels work`. Replace any channel it reports.
To preview the site on your machine:

```sh
python scripts/update_videos.py            # writes site/videos.json (git-ignored)
python -m http.server -d site 8000         # open http://localhost:8000
```

### 6. Optional: give it its own look

- **Logo and favicon**: put pictures in `site/` and name them in
  `channels.yaml` (`logo: dad-tv.svg`, `favicon: dad-tv-icon.svg`). You
  can draw simple SVGs yourself: the favicon must still read at 16 px, so
  use solid shapes, no text and no thin lines. Never use another brand's
  logo or anything resembling YouTube's.
- **Colour**: `accent: "#2b6cb4"`, a dark, saturated colour, so white text
  on it stays readable.
- **README**: it is the template's README. Replace its first line (the
  banner image) and add a short paragraph at the top saying what this list
  is and linking to the site; keep the rest, which documents the template.

### 7. Publish

```sh
git add channels.yaml site/ README.md
git commit -m "Dad TV: trains, jazz piano and woodworking"
git push
gh api -X POST repos/<owner>/<repository>/pages -f build_type=workflow
gh workflow run build.yml
gh run watch "$(gh run list --workflow build.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
gh repo edit --add-topic unrecommended --homepage "https://<owner>.github.io/<repository>/" \
  --description "<one line about the list>"
```

- A build that ran before Pages was turned on fails with "Not Found" in the
  deploy step. That is expected; the `gh workflow run` above fixes it.
- The build's summary page lists each channel, its video count and any
  problem. Read it with `gh run view <id> --log` if something is missing.
- Use the owner in **lowercase** in the site address.
- Open the site and check it shows the groups and plays a video.

### 8. Report back

Give the site address and repository address, the channels you chose and
why (one line each), and the things to know: the list is public, YouTube may
show ads, videos stream from YouTube, and GitHub pauses the daily update
after 60 days without a commit (any small edit resumes it).

## Rules

- **Real channels only.** Every entry must come from a search or a check you
  ran. `--check` must pass before you publish.
- **Public by default.** Ask before putting anything personal in the list,
  the `about` text or the repository: names, places, schools, health.
- **Jokes, critique and statements are welcome**, and so are lists with a
  political point of view. The site only shows each channel's own videos,
  unaltered. Keep the framing honest in `about`. Don't present the site as
  made by, or as the official channel of, a real person or organisation, and
  don't build a list meant to mock or target a private individual.
- **Don't change code to make a list.** A new site only needs
  `channels.yaml`, optionally pictures in `site/` and the README. If the user
  asks for code changes, see task 2.
- **No secrets.** The site needs no API keys; don't add any.
- **Kid-safe is not a lock.** It removes links and covers YouTube's buttons,
  but YouTube may still play ads and a determined child can type another
  address. Say so when building a child's site.

## Task 2: working on the template itself

- `scripts/update_videos.py`: reads `channels.yaml`, lists videos with
  yt-dlp, falls back to RSS and the previous `videos.json`, writes
  `videos.json`. Also `--check` / `--check --offline`.
- `scripts/find_channels.py`: channel search (above).
- `scripts/make_art.py`: draws the default logo, favicon and README banner.
- `site/`: the static page (`index.html`, `style.css`, `app.js`), plain
  browser JavaScript, no build step, relative URLs only.
- `.github/workflows/build.yml`: builds and deploys on push, daily and on
  demand. `checks.yml`: lint and tests.
- `channels.schema.json`: keep it in step with `parse_config` (a test checks
  that the demo file and some edge cases agree).

Before committing, run what `checks.yml` runs:

```sh
pip install -r requirements.txt pytest ruff jsonschema
ruff check . && ruff format --check . && pytest -q
node --check site/app.js
python scripts/update_videos.py --check --offline
```

Conventions: docs and comments describe the current state (history goes in
commit messages); everything user-facing is written for non-programmers;
any value from `videos.json` or the URL that reaches the page is escaped or
validated (see `esc()` and the ID checks in `app.js`); the page must work on
phones, tablets and desktops, in light and dark mode, and in kid-safe mode
must show no links out.
