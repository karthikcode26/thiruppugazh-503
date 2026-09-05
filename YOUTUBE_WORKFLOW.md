# Bulk YouTube matching workflow

The site can embed a confirmed YouTube video directly on each song page. The
challenge is choosing the correct video for each of 503 songs. This workflow
uses the official YouTube Data API to find candidates automatically, then gives
you a fast local review screen so incorrect search results are never published.

## Why review is required

A search result is not proof that a video is the correct song. Titles can use
Tamil, English transliteration, old/new numbering, or different recordings.
The discovery tool therefore writes candidates to a local CSV. Only a candidate
you approve is copied to `songs.json` as `youtubeId`.

The production site behaves safely during this process:

- A song with a confirmed `youtubeId` gets a responsive YouTube player, an
  “Open on YouTube” button, and a separate search for alternate recordings.
- A song without one keeps a YouTube search button.
- The player uses YouTube privacy-enhanced mode (`youtube-nocookie.com`).

## 1. Create a YouTube Data API key

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. Open **APIs & Services → Library**.
4. Enable **YouTube Data API v3**.
5. Open **APIs & Services → Credentials**.
6. Choose **Create credentials → API key**.
7. Edit the key and restrict its API access to **YouTube Data API v3**.

Do not paste the key into source files, commit it, or send it in chat.

In macOS Terminal, read it without putting the key in shell history:

```bash
cd ~/workspace/thiruppugazh-503
read -s "YOUTUBE_API_KEY?Paste YouTube API key: "; export YOUTUBE_API_KEY; echo
```

The environment variable lasts only for that Terminal session.

## 2. Discover candidates in resumable batches

Run:

```bash
python3 tools/youtube_candidates.py discover --limit 90
```

The command searches for three embeddable candidates per song and appends them
to `youtube_candidates.csv`. It skips songs already searched and songs that
already have a confirmed `youtubeId`, so it is safe to rerun.

The official API's default search allowance is currently 100 `search.list`
calls per day. The default batch size is 90 to leave some room. Searching all
503 songs therefore normally takes six daily runs:

```bash
python3 tools/youtube_candidates.py discover --limit 90
```

If the API reports that the daily quota is exhausted, stop and run the same
command after the quota resets. Progress is already saved.

Useful options:

```bash
# Search only a range
python3 tools/youtube_candidates.py discover --start 1 --end 100 --limit 90

# Show progress
python3 tools/youtube_candidates.py status
```

Generated discovery and review files are ignored by git. Your API key is never
written by the tool.

## 3. Review candidates quickly

Generate the local review page:

```bash
python3 tools/youtube_candidates.py review
open youtube_review.html
```

For each song:

1. Open promising candidates on YouTube to listen and verify.
2. Click **Approve this video** for the correct one, or **No suitable video**.
3. Use **Next** to continue. Decisions are saved in that browser's local storage.
4. Click **Download approvals CSV** when ready.

You can review one batch at a time; you do not have to finish all 503 at once.
Move the downloaded file into the repository root:

```bash
mv ~/Downloads/youtube_approvals.csv ~/workspace/thiruppugazh-503/
```

If Safari added a number to the filename, use that exact filename as the source.

## 4. Apply only approved videos

From the repository root:

```bash
python3 tools/youtube_candidates.py apply
python3 tools/youtube_candidates.py status
```

The apply command rejects malformed video IDs, unknown song numbers, duplicate
approval rows, and IDs that were not candidates for that song. It updates only
approved records and removes an existing ID only when a song is explicitly
marked `none`.

Review the data change:

```bash
git diff -- songs.json
```

Then commit and deploy. The deployment script has an explicit allow-list and
will not upload the local API key, candidate metadata, review page, or approval
file. Always inspect the dry run first:

```bash
git add songs.json
git commit -m "Add confirmed YouTube videos"
git push origin main
bash deploy.sh --dry-run
bash deploy.sh
```

## Commands reference

```bash
python3 tools/youtube_candidates.py discover --help
python3 tools/youtube_candidates.py review --help
python3 tools/youtube_candidates.py apply --help
python3 tools/youtube_candidates.py status --help
```

## Official references

- [YouTube Data API `search.list`](https://developers.google.com/youtube/v3/docs/search/list)
- [YouTube API quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost)
- [YouTube embedded-player parameters](https://developers.google.com/youtube/player_parameters)
