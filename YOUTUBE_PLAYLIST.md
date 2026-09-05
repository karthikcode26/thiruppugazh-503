# Import the 503-song YouTube playlist

The complete song collection is available in this public playlist:

- Playlist: <https://www.youtube.com/playlist?list=PLFwcC0dtfDTiQSDIfbF9EJYEqTaA4iZ_6>
- Expected order: playlist position 1 maps to song 1, through position 503 maps to song 503.

Instead of searching 503 times, the import tool reads the playlist in pages of
50 through the official YouTube Data API. It stores each exact video ID and
checks whether YouTube currently allows that video in an embedded player.
A fetch normally needs about 22 inexpensive API requests: roughly 11 playlist
pages and 11 video-status batches.

The generated report is tied to the known playlist ID, importer version, and
UTC fetch time. It expires after seven days. Applying it makes another live API
check and stops if even one playlist position or video ID changed. The website
never chooses a song video from a mutable live playlist position.

## 1. Create an API key once

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. Go to **APIs & Services → Library**.
4. Enable **YouTube Data API v3**.
5. Go to **APIs & Services → Credentials**.
6. Select **Create credentials → API key**.
7. Restrict the key to **YouTube Data API v3**.

Do not add the key to source files, GitHub, or chat. Enter it only in your Mac
Terminal; this form does not place the key in shell history:

```bash
cd ~/workspace/thiruppugazh-503
read -s "YOUTUBE_API_KEY?Paste YouTube API key: "; export YOUTUBE_API_KEY; echo
```

## 2. Fetch and verify the playlist

```bash
python3 tools/import_youtube_playlist.py fetch
python3 tools/import_youtube_playlist.py inspect
```

`fetch` refuses to continue unless YouTube returns exactly 503 unique videos in
contiguous playlist positions 0–502. It creates the local file
`youtube_playlist.csv`, which is ignored by Git.

`inspect` validates the report provenance and every row, then prints the first,
middle, and last mappings plus warnings for videos that could not be embedded
at fetch time or whose YouTube title does not contain the Tamil song first
words. Open the printed links and confirm the sample positions match the master
list before applying.

If the count or ordering is incorrect, do not apply. Correct the playlist first,
then run `fetch` again. Also run `fetch` again if the report is over seven days
old.

## 3. Add all verified video IDs to the site

After confirming that playlist position equals song number:

```bash
python3 tools/import_youtube_playlist.py apply --confirm-order
git diff -- songs.json
```

`apply` requires the API key again. It re-fetches all 503 playlist positions,
compares every exact video ID with the reviewed report, and re-checks current
embeddability rather than trusting editable CSV status columns. It then writes
both fields for every song:

- `youtubeId`: the exact video, retained even when embedding is unavailable.
- `youtubeEmbeddable`: `true` only when the current YouTube status allows an iframe.

A non-embeddable or unavailable video is not loaded in an iframe. Its song page
instead offers the exact YouTube watch link and a separate search fallback.

Commit the verified mapping on a review branch:

```bash
git switch -c import-exact-youtube-ids
git add songs.json
git commit -m "Import exact videos from the 503-song playlist"
git push -u origin import-exact-youtube-ids
```

Then open a pull request for that branch on GitHub.

## 4. Deploy safely

Only public runtime files are uploaded. Local API keys and playlist reports are
not included:

```bash
bash deploy.sh --dry-run
bash deploy.sh
```

After deployment, test songs 1, 252, and 503 on a physical iPhone. Confirm that
an embeddable video plays inline and that any unavailable video shows the exact
YouTube-link fallback instead of a broken player.

## Tool reference

```bash
python3 tools/import_youtube_playlist.py fetch --help
python3 tools/import_youtube_playlist.py inspect --help
python3 tools/import_youtube_playlist.py apply --help
```

Official references:

- [Playlist items API](https://developers.google.com/youtube/v3/docs/playlistItems/list)
- [Videos API](https://developers.google.com/youtube/v3/docs/videos/list)
- [YouTube embedded players](https://developers.google.com/youtube/player_parameters)
