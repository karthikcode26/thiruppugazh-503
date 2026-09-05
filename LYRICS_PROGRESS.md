# Lyrics feature — progress & resume notes

_Last updated: 2026-09-05 (session 2). Approach finalized: lyrics as page images._

## Goal
Show each song's lyrics **inline, above the YouTube video**, so the user can
read along while the video plays without leaving the page.

## PDF facts (confirmed)
- File: `ThiruppugazhTamil.pdf`, **589 pages**, public domain.
- One song per page; **extra pages** exist (13 pages of front matter — song 1 is
  on page 14 / 0-based index 13 — plus section dividers).
- Fonts: **TSCu_SaiIndira / TSCInaimathi** (legacy TSCII-family). The rendered
  page looks correct, but the **extractable text is scrambled** (visual-order
  vowel reordering) and PyMuPDF exposes **no glyph IDs** (`glyph=None`), so
  clean text cannot be recovered reliably. OCR and hand-reversal both rejected
  as too risky for scripture.
- The song **number** prints in a clean numeric header (`பாடல் N` — the Tamil
  word is garbled but the digit N is clean ASCII), so we map pages by that.

## Chosen solution: render pages to images
Render each song's page(s) to `lyrics/<num>.png`; the site shows the image above
the video. Perfect visual fidelity, no OCR, no font reversal. Tradeoff: image is
not selectable/searchable and needs pinch-zoom on mobile (fine for read-along).

## What is built (branch `lyrics-as-images`, PR #7)
- `tools/render_lyric_images.py` — `inspect` / `render` / `verify`.
  - Reads song number from the header window (first ~4 non-"Home" lines).
  - Groups pages by number; a numberless page attaches as a continuation ONLY
    if the immediately preceding page was part of the current song.
  - **Refuses** to render if <450 songs detected or any song maps to
    **non-consecutive pages** (guards against a divider being misread).
  - Stacks multi-page songs into one image.
- `song.html` — lyrics `<img lyrics/<num>.png>` shown ABOVE the video; hides
  itself if the image 404s.
- `styles.css` — `.lyrics-image` full-width responsive style.
- `deploy.sh` — uploads `lyrics/*.png` (image/png) and still `*.txt`.
- Tested end-to-end with a fake `fitz`: clean 503-page book renders all 503
  (song 200 stacked); a book with a stray-number divider is correctly refused.

## User's next steps (on the Mac with the PDF)
1. Merge PR #7.
2. `git switch main && git pull`
3. `python3 -m pip install --user pymupdf`
4. `python3 tools/render_lyric_images.py inspect --pdf "ThiruppugazhTamil.pdf"`
   - Expect: ~503 songs detected, **no non-consecutive songs**.
   - Paste the output here before rendering.
5. If clean: `render`, then `verify`, open a few PNGs, then:
   `git switch -c add-lyrics-images && git add lyrics && commit && push`, open a
   data PR, merge, deploy, and check on iPhone (lyrics image sits above video).

## Fallback if inspect shows problems
- If some pages don't yield a number (header rule needs tuning), share those
  pages' first lines and tighten `detect_song_number`.
- `--dpi` (default 150) trades sharpness vs. size; expect tens of MB total.

## Everything else is DONE and live
- 503-song mobile site on S3; 501 embedded videos; 158 & 314 on fallback.
- Related-videos search and "Open on YouTube" button removed.
