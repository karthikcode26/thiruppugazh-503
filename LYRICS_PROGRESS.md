# Lyrics feature — progress & resume notes

_Last updated: 2026-09-05. Paused mid-task (diagnosing PDF number detection)._

## Goal
Add public-domain lyrics for all 503 songs, extracted from a text-based
(selectable) PDF book, displayed on each song page.

## Confirmed facts about the PDF
- Rights: **public domain** (safe to publish).
- Text is **selectable** (no OCR needed).
- One song per page, but there are **extra pages** (front matter, dividers).
- **589 total pages.**
- Song number is printed in the heading, and the **title is in Tamil font**, so
  we map by the **printed number**, not by page order or the English title.

## Where we got stuck
The current detector expects the song number at the **very start of the first
non-empty line**. Against the real book this found only **1/503** pages, and the
single match (`8. புய வகுப்பு` on page 569) looks like a **table-of-contents /
index entry**, not a lyrics page.

Conclusion: the number is NOT at the start of the first line on real song pages.
We need to see the true page layout before fixing the pattern.

## Next step (do this first tomorrow, on the Mac with the PDF)
Run the raw page dump and share the output:

```bash
cd ~/workspace/thiruppugazh-503
cat > dump_pages.py <<'PY'
import sys
import pdfplumber
pdf_path = sys.argv[1] if len(sys.argv) > 1 else "book.pdf"
targets = [13, 14, 15, 20, 30, 569]
with pdfplumber.open(pdf_path) as pdf:
    total = len(pdf.pages)
    for i in targets:
        if i >= total:
            continue
        text = pdf.pages[i].extract_text() or ""
        print("===== PAGE", i, "(0-based) =====")
        for line in text.splitlines()[:8]:
            print(repr(line))
        print()
PY
python3 dump_pages.py "YOUR_BOOK.pdf"
```

`repr(line)` reveals exact characters/spaces and where the number sits.

## Decision pending on that output
Depending on where the number appears, adjust `tools/extract_lyrics.py`:
- If the number is elsewhere on the line/heading → widen `LEADING_NUMBER_RE` /
  change the anchor.
- If lyrics pages carry **no** number (only the index does) → switch to matching
  each page's **Tamil first-word title against `songs.json` `t`** instead.
- Skip index/TOC pages (e.g. page ~569) so they don't hijack a song number.

## State of the work
- Branch: `add-lyrics-from-pdf` (commit `0b0673f`), pushed.
- Open PR: **#6** — https://github.com/karthikcode26/thiruppugazh-503/pull/6
  - `tools/extract_lyrics.py` — by-number extractor (`inspect`/`extract`/`verify`)
  - `song.html` + `styles.css` — on-demand lyrics section (loads `lyrics/<num>.txt`)
  - `deploy.sh` — uploads `lyrics/*.txt`
  - README — lyrics workflow docs
- **Do not merge PR #6 yet** — the extractor's number detection still needs the
  fix above. Once `inspect` reports ~503 detected songs, then extract, verify,
  review, commit `lyrics/`, and deploy.

## Everything else is DONE and live
- 503-song mobile site on S3, code on GitHub.
- 501 embedded YouTube videos (mapped by title number); songs 158 & 314 on
  playlist/search fallback.
- Related-videos search and the "Open on YouTube" button both removed.
