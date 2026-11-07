# unrecommended

Your own YouTube, without the algorithm.

You pick the channels. unrecommended turns them into a small website, hosted
for free on GitHub Pages, that shows only their videos: no comments, no
"up next" from YouTube, no home feed deciding what you watch.

## Plan

- `channels.yaml`: the channels you want, grouped however you like.
- A GitHub Action lists each channel's videos with yt-dlp (falling back to the
  channel's RSS feed if YouTube blocks GitHub's servers) and writes
  `videos.json`.
- A static page, with no build step, browses and plays them through YouTube's
  embedded player. When a video ends, the next one comes from your list.

Work in progress: none of this exists yet.
