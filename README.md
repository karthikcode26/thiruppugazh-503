# திருப்புகழ் 503 — Thiruppugazh 503 Songs

A dependency-free, mobile-first website listing all **503 Thiruppugazh songs**
of Arunagirinathar. It is designed for an iPhone-sized browser and can embed a
manually confirmed YouTube video for each song.

## Current features

- All 503 songs in the book's 1–503 ordering.
- Search by song number, Tamil first words, or approximate English transliteration.
- Responsive song detail pages that fit phone browsers.
- Embedded YouTube player when a song has a confirmed `youtubeId`.
- YouTube search remains available for every song, including if a confirmed video later disappears.
- Static files only: no application server or database is required.

## Project files

| File | Purpose |
|---|---|
| `index.html` | Searchable song list. |
| `song.html` | Song detail page and responsive YouTube player. |
| `app.js` | List loading, search, and Tamil-to-Roman search normalization. |
| `styles.css` | Mobile-first presentation. |
| `songs.json` | Production song data. |
| `tools/youtube_candidates.py` | Bulk YouTube discovery, review-page generation, and approval application. |
| `YOUTUBE_WORKFLOW.md` | Step-by-step bulk matching instructions. |
| `deploy.sh` | Safely deploys only public runtime files to the existing S3 bucket. |
| `tools/extract_links.py` / `links.csv` | Historical Google Drive link extraction artifacts; not used by the live site. |

## Run locally

Serve the directory over HTTP because browsers do not allow `fetch()` from a
plain `file://` page:

```bash
python3 -m http.server 8000
```

Then open <http://localhost:8000>.

## Song data

A basic record:

```json
{"num":16,"t":"அனைவருமருண்டு","k":431,"v":"legacy-drive-file-id"}
```

A record with an approved YouTube video:

```json
{"num":16,"t":"அனைவருமருண்டு","k":431,"v":"legacy-drive-file-id","youtubeId":"dQw4w9WgXcQ"}
```

- `num`: public song number, 1–503.
- `t`: Tamil first words/title.
- `youtubeId`: optional, manually confirmed 11-character YouTube video ID.
- `k`: historical book catalog number; not currently used by the site.
- `v`: historical Google Drive ID; not currently used by the site.

Never put an automatically selected search result directly into `youtubeId`.
Use the review workflow so the embedded video is known to be the correct song.

## Bulk YouTube matching

See **[YOUTUBE_WORKFLOW.md](YOUTUBE_WORKFLOW.md)**. In summary:

```bash
# API key remains in this Terminal session only
read -s "YOUTUBE_API_KEY?Paste YouTube API key: "; export YOUTUBE_API_KEY; echo

# Discover up to 90 songs in today's API batch
python3 tools/youtube_candidates.py discover --limit 90

# Generate and open a fast local review page
python3 tools/youtube_candidates.py review
open youtube_review.html

# After downloading youtube_approvals.csv from the review page
python3 tools/youtube_candidates.py apply
```

## Deploy to the existing S3 website

The deployment script uploads only the five public runtime assets. It does not
publish ignored API keys, candidate metadata, review pages, or approvals.
Preview the upload first, then deploy:

```bash
bash deploy.sh --dry-run
bash deploy.sh
```

## Roadmap

- Confirm and embed YouTube videos in resumable batches.
- Add lyric images from the user's book where publication rights allow it.
- Add favourites, recently viewed songs, and offline support.
