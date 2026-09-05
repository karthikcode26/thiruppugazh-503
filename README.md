# திருப்புகழ் 503 — Thiruppugazh 503 Songs

A dependency-free, mobile-first website listing all **503 Thiruppugazh songs**
of Arunagirinathar. It is designed for an iPhone-sized browser and embeds the
corresponding video from the complete public YouTube playlist.

## Current features

- All 503 songs in the attached master list's 1–503 ordering.
- Search by song number, Tamil first words, or approximate English transliteration.
- Responsive exact-ID YouTube player after the one-time playlist import.
- Safe full-playlist/search links before import, and exact-video/search fallbacks if
  an imported video cannot be embedded.
- Static files only: no application server or database is required.

## Project files

| File | Purpose |
|---|---|
| `index.html` | Searchable song list. |
| `song.html` | Song detail page and responsive YouTube player. |
| `app.js` | List loading, search, and Tamil-to-Roman search normalization. |
| `styles.css` | Mobile-first presentation. |
| `songs.json` | Production song data, including imported YouTube IDs. |
| `tools/import_youtube_playlist.py` | Maps playlist videos from numeric title prefixes to exact song IDs. |
| `YOUTUBE_PLAYLIST.md` | One-time playlist import instructions. |
| `deploy.sh` | Safely deploys only public runtime files to the existing S3 bucket. |
| `tools/extract_links.py` / `links.csv` | Historical Google Drive artifacts; not used by the live site. |

## Run locally

Serve the directory over HTTP because browsers do not allow `fetch()` from a
plain `file://` page:

```bash
python3 -m http.server 8000
```

Then open <http://localhost:8000>.

## Song data

```json
{"num":16,"t":"அனைவருமருண்டு","k":431,"v":"legacy-drive-file-id","youtubeId":"dQw4w9WgXcQ","youtubeEmbeddable":true}
```

- `num`: public song number, 1–503.
- `t`: Tamil first words/title.
- `youtubeId`: exact YouTube ID imported from the song number at the start of the video title.
- `youtubeEmbeddable`: whether YouTube currently allows that exact video in an iframe.
- `k`: historical book catalog number; not currently used by the site.
- `v`: historical Google Drive ID; not currently used by the site.

## Import the complete YouTube playlist

The playlist removes the need for 503 individual searches. See
**[YOUTUBE_PLAYLIST.md](YOUTUBE_PLAYLIST.md)**. The short version is:

```bash
# Keep the API key in this Terminal session only
read -s "YOUTUBE_API_KEY?Paste YouTube API key: "; export YOUTUBE_API_KEY; echo

# Fetch and validate every numbered playlist entry
python3 tools/import_youtube_playlist.py fetch
python3 tools/import_youtube_playlist.py inspect

# After reviewing the title-number mappings
python3 tools/import_youtube_playlist.py apply --confirm-mapping
```

The importer creates a versioned, timestamped snapshot tied to the known
playlist. It maps each video from the number at the beginning of its title—not
from playlist order—and re-fetches the complete playlist and current video
statuses at apply time. It safely accepts the observed 501 distinct numbered
songs, collapses only identical duplicate entries, and ignores only unnumbered
private/unavailable entries. Songs 158 and 314 currently have no numbered video
and retain the full-playlist/search fallback.

Every mapped song keeps its exact video ID. A video is embedded only when
YouTube currently marks it embeddable; otherwise the page offers its exact
YouTube link and a separate search fallback. The live site never maps songs by
a mutable playlist position.

Until the networked import is run and its `songs.json` change is reviewed, the
base dataset intentionally shows the full-playlist and search options instead
of guessing or embedding an unverified video.

## Deploy to the existing S3 website

The deployment script uploads only the five public runtime assets. It does not
publish API keys or local playlist reports:

```bash
bash deploy.sh --dry-run
bash deploy.sh
```

## Roadmap

- Add lyric images from the user's book where publication rights allow it.
- Add favourites, recently viewed songs, and offline support.
