# Lyrics feature — progress & resume notes

_Last updated: 2026-09-05 (session 2). Approach FINALIZED: images via fixed page map._

## Goal
Show each song's lyrics inline, ABOVE the YouTube video, so the user reads along
while the video plays without leaving the page.

## Why images (not text)
The PDF (`ThiruppugazhTamil.pdf`, 589 pages, public domain) uses a legacy TSCu
font (TSCu_SaiIndira / TSCInaimathi). The extractable text is scrambled, no glyph
IDs are exposed, and even the printed `பாடல் N` header cannot be trusted from the
text layer (marker/number mis-extracts on many pages). OCR and font-reversal were
rejected as too risky for scripture. Rendering pages to images reproduces the
lyrics exactly as printed.

## The verified page map (from the user's manual inspection)
Songs 502 and 503 were placed early; everything else is sequential, one page per
song, no multi-page songs:

    PDF pages 14-125  -> songs 1-112
    PDF page  126     -> song 502
    PDF pages 127-311 -> songs 113-297
    PDF page  312     -> song 503
    PDF pages 313-516 -> songs 298-501

Anchors confirmed by the user: p14=1, p125=112, p126=502, p127=113, p311=297,
p312=503, p313=298, p516=501. Arithmetic checks out to exactly 503 unique songs.
This lives in `PAGE_MAP_RANGES` at the top of tools/render_lyric_images.py.

## What is built
- `tools/render_lyric_images.py` — commands `check` / `render` / `verify`.
  - `check`: validates the map (503 unique songs, within PDF page count) and
    prints sample song->page pairs for spot-checking.
  - `render`: renders each mapped page to `lyrics/<num>.png` + manifest.
  - `verify`: confirms 503 images and reports total size.
  - No dependence on the broken text layer.
- `song.html` / `styles.css` / `deploy.sh` (already merged via PR #7): lyrics
  image shown ABOVE the video; `lyrics/*.png` uploaded on deploy; hides if 404.
- Fully tested with a mock fitz: 503 images, correct anchors, short-PDF refused.

## Current PR
- Branch `lyrics-page-map`, PR #9 (page-map renderer + README/progress).
  (PR #7 = image display; PR #8 = earlier marker attempt, now superseded by the
  page map.)

## User's next steps (on the Mac)
1. Merge PR #9, then `git switch main && git pull`.
2. `python3 -m pip install --user pymupdf`  (if not already)
3. `python3 tools/render_lyric_images.py check --pdf "ThiruppugazhTamil.pdf"`
   - Open the printed sample pages in a viewer; confirm songs 1,112,113,297,
     298,501,502,503 look right.
4. `render`, then `verify`, then spot-check several images.
5. If any page is off, edit `PAGE_MAP_RANGES` and re-render (no other changes).
6. `git switch -c add-lyrics-images && git add lyrics && commit && push`, open a
   data PR, merge, `bash deploy.sh --dry-run && bash deploy.sh`.
7. On iPhone: lyrics image appears above the video on each song page.
   Expect ~tens of MB total; lower `--dpi` if you want smaller files.

## Everything else is DONE and live
- 503-song mobile site on S3; 501 embedded videos; songs 158 & 314 on fallback.
- Related-videos search and "Open on YouTube" button removed.
