# Import the numbered YouTube playlist

The available recordings are in this public playlist:

- Playlist: <https://www.youtube.com/playlist?list=PLFwcC0dtfDTiQSDIfbF9EJYEqTaA4iZ_6>
- Mapping rule: the number at the beginning of a video title identifies the
  public song number. For example, `017 Iyalisaiyil` maps to song 17.

The playlist is **not** ordered from song 1 through 503. The import tool does not
map by playlist position. It reads every entry through the official YouTube Data
API, parses each title's numeric prefix, stores the exact video ID, and checks
whether YouTube currently permits embedding.

At the time this workflow was designed, YouTube returned 504 raw entries:

- 501 distinct numbered songs;
- repeated identical entries for songs 113 and 375;
- one unavailable private entry without a visible number;
- no numbered videos for songs 158 and 314.

The importer safely collapses a repeated entry only when both copies have the
same song number and exact video ID. It ignores an unnumbered entry only when
YouTube reports it private or unavailable. Songs 158 and 314 retain the site's
full-playlist and song-search fallback until exact videos are found.

The generated report is tied to the known playlist ID, importer version, and
UTC fetch time. It expires after seven days. Applying it re-fetches the complete
playlist and stops if any reviewed position, video ID, or title changed. Runtime
song pages use persisted exact IDs—not mutable playlist positions.

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

`fetch` creates `youtube_playlist.csv`, which is ignored by Git. It validates
all title numbers and refuses unsafe conditions, including:

- fewer than 501 distinct numbered songs;
- a visible playlist entry without a number;
- two different video IDs claiming the same song number;
- one video ID claiming two song numbers;
- an out-of-range title number.

`inspect` validates every report row and prints representative mappings,
missing song numbers, repeated identical entries, and ignored private entries.
Open several printed links and check that the title number and Tamil song title
refer to the same song.

Run `fetch` again if the playlist changes or the report is more than seven days
old.

## 3. Apply the reviewed exact IDs

After reviewing the number-based mappings:

```bash
python3 tools/import_youtube_playlist.py apply --confirm-mapping
git diff -- songs.json
```

`apply` requires the API key again. It downloads the complete playlist and
compares every current position, exact video ID, and title with the reviewed
report. It also re-checks current embeddability instead of trusting editable CSV
status columns.

For each numbered video it writes:

- `youtubeId`: the exact video, retained even when embedding is unavailable;
- `youtubeEmbeddable`: `true` only when the current YouTube status allows an iframe.

A non-embeddable video is not loaded in an iframe; the page offers its exact
YouTube watch link and a separate search. A song missing from the playlist gets
neither field and retains the full-playlist/search fallback.

Commit the verified mapping on a review branch:

```bash
git switch -c import-exact-youtube-ids
git add songs.json
git commit -m "Import numbered videos from the YouTube playlist"
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

After deployment, test songs 1, 252, and 503 on a physical iPhone. Also test
songs 158 and 314 to confirm that each shows the safe playlist/search fallback.

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
