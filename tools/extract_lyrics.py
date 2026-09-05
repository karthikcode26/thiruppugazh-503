#!/usr/bin/env python3
"""Extract Thiruppugazh lyrics from a text-based (selectable) PDF book.

The book is public domain and prints the song number at the top of each song's
page. This tool maps each page to a song by that printed number, not by page
position, so extra pages (covers, dividers, blanks) are simply skipped and the
mapping stays correct even when songs are not on consecutive pages.

Because the PDF is large and lives on your own machine, run this on your Mac:

  python3 -m pip install --user pdfplumber
  python3 tools/extract_lyrics.py inspect --pdf "Thiruppugazh.pdf"
  python3 tools/extract_lyrics.py extract --pdf "Thiruppugazh.pdf"
  python3 tools/extract_lyrics.py verify

Workflow:
  1. `inspect` prints the page count and, for every page, the song number it
     detects. It reports how many distinct 1..503 numbers were found and which
     song numbers are missing, so you can confirm the number detection works
     before extracting.
  2. `extract` writes lyrics/<num>.txt for each detected song and
     lyrics/manifest.json. A page's leading number decides its song; pages with
     no valid number are skipped. If one song number appears on several pages,
     their text is joined in page order (multi-page songs).
  3. `verify` re-checks that produced files are non-empty and match songs.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SONGS = ROOT / "songs.json"
DEFAULT_LYRICS_DIR = ROOT / "lyrics"
EXPECTED_SONG_COUNT = 503
MANIFEST_NAME = "manifest.json"
# A leading song number (e.g. "16", "16.", "16 -") at the very start of the
# first non-empty line. The Tamil title follows; only the number is used.
LEADING_NUMBER_RE = re.compile(r"^\s*(\d{1,3})\b")


def load_songs(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        songs = json.load(handle)
    if not isinstance(songs, list) or len(songs) != EXPECTED_SONG_COUNT:
        raise ValueError(f"{path} must contain exactly {EXPECTED_SONG_COUNT} songs")
    if [song.get("num") for song in songs] != list(range(1, EXPECTED_SONG_COUNT + 1)):
        raise ValueError("songs.json numbers must be contiguous from 1")
    return songs


def load_pdf(pdf_path: Path):
    try:
        import pdfplumber  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "pdfplumber is required. Install it with:\n"
            "  python3 -m pip install --user pdfplumber"
        ) from exc
    import pdfplumber

    if not pdf_path.exists():
        raise ValueError(f"PDF not found: {pdf_path}")
    return pdfplumber.open(str(pdf_path))


def clean_text(raw: str) -> str:
    """Normalize whitespace while keeping Tamil characters and line breaks."""
    normalized = unicodedata.normalize("NFC", raw)
    lines = [line.rstrip() for line in normalized.splitlines()]
    cleaned: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip():
            blank_run = 0
            cleaned.append(line.strip())
        else:
            blank_run += 1
            if blank_run == 1:
                cleaned.append("")
    while cleaned and cleaned[0] == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return "\n".join(cleaned)


def leading_number(page_text: str) -> Optional[int]:
    """Return the song number printed at the start of the first non-empty line."""
    for line in page_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = LEADING_NUMBER_RE.match(stripped)
        if match:
            value = int(match.group(1))
            if 1 <= value <= EXPECTED_SONG_COUNT:
                return value
        return None
    return None


def collect_pages(pdf) -> list[dict[str, Any]]:
    """Return per-page cleaned text and detected song number."""
    pages: list[dict[str, Any]] = []
    for page_index in range(len(pdf.pages)):
        text = clean_text(pdf.pages[page_index].extract_text() or "")
        pages.append(
            {
                "page_index": page_index,
                "text": text,
                "number": leading_number(text),
            }
        )
    return pages


def build_mapping(pages: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """Group pages by the song number they declare, preserving page order."""
    by_song: dict[int, list[dict[str, Any]]] = {}
    for page in pages:
        number = page["number"]
        if number is None:
            continue
        by_song.setdefault(number, []).append(page)
    return by_song


def inspect_command(args: argparse.Namespace) -> int:
    songs = load_songs(args.songs)
    with load_pdf(args.pdf) as pdf:
        total_pages = len(pdf.pages)
        pages = collect_pages(pdf)

    by_song = build_mapping(pages)
    numbered_pages = sum(1 for page in pages if page["number"] is not None)
    unnumbered_pages = total_pages - numbered_pages
    missing = [num for num in range(1, EXPECTED_SONG_COUNT + 1) if num not in by_song]
    multi = {num: len(pgs) for num, pgs in by_song.items() if len(pgs) > 1}

    print(f"PDF pages: {total_pages}")
    print(f"Pages with a detected song number: {numbered_pages}")
    print(f"Pages skipped (no valid number): {unnumbered_pages}")
    print(f"Distinct songs detected: {len(by_song)}/{EXPECTED_SONG_COUNT}")
    print(f"Missing song numbers: {missing[:30] or 'none'}"
          + (" ..." if len(missing) > 30 else ""))
    print(f"Songs spanning multiple pages: {len(multi)}"
          + (f" (e.g. {dict(list(multi.items())[:5])})" if multi else ""))
    print()
    print("First few detected pages (0-based index -> number / first line):")
    shown = 0
    for page in pages:
        if page["number"] is None:
            continue
        first_line = (page["text"].splitlines() or [""])[0]
        print(f"  page {page['page_index']}: song {page['number']} | {first_line[:80]}")
        shown += 1
        if shown >= 6:
            break
    print()
    if len(by_song) == 0:
        print("No numbers detected. The number may not be at the very start of the line;")
        print("share one page's first line and I can adjust the pattern.")
    else:
        print("If the detected numbers look right, run: extract  (no page offset needed).")
    return 0


def extract_command(args: argparse.Namespace) -> int:
    songs = load_songs(args.songs)
    args.lyrics_dir.mkdir(parents=True, exist_ok=True)

    with load_pdf(args.pdf) as pdf:
        pages = collect_pages(pdf)

    by_song = build_mapping(pages)
    if len(by_song) < args.min_songs:
        raise ValueError(
            f"Only {len(by_song)} distinct song numbers were detected; at least "
            f"{args.min_songs} expected. Run inspect and confirm the page numbers "
            "are being read before extracting."
        )

    # Remove any stale lyrics files so a re-run cannot leave old data behind.
    for existing in args.lyrics_dir.glob("*.txt"):
        existing.unlink()

    written = 0
    multi_page: list[int] = []
    empty: list[int] = []
    for song_num in sorted(by_song):
        page_group = by_song[song_num]
        if len(page_group) > 1:
            multi_page.append(song_num)
        text = "\n\n".join(page["text"] for page in page_group).strip()
        if not text:
            empty.append(song_num)
            continue
        (args.lyrics_dir / f"{song_num}.txt").write_text(text + "\n", encoding="utf-8")
        written += 1

    produced = sorted(
        int(path.stem) for path in args.lyrics_dir.glob("*.txt") if path.stem.isdigit()
    )
    missing = [num for num in range(1, EXPECTED_SONG_COUNT + 1) if num not in produced]
    manifest = {
        "count": written,
        "songs": produced,
        "missing": missing,
        "multi_page": multi_page,
    }
    (args.lyrics_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Wrote {written} lyrics files to {args.lyrics_dir}")
    print(f"Songs spanning multiple pages (joined): {multi_page[:20] or 'none'}")
    if empty:
        print(f"Warning: {len(empty)} detected songs had empty text: {empty[:20]}")
    print(f"Songs without lyrics: {missing[:30] or 'none'}"
          + (" ..." if len(missing) > 30 else ""))
    print(f"Manifest: {args.lyrics_dir / MANIFEST_NAME}")
    print("Next: run verify, then review a few files before committing.")
    return 0


def verify_command(args: argparse.Namespace) -> int:
    songs = load_songs(args.songs)
    manifest_path = args.lyrics_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise ValueError(f"Manifest not found: {manifest_path}. Run extract first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    present: list[int] = []
    empty: list[int] = []
    for song in songs:
        path = args.lyrics_dir / f"{song['num']}.txt"
        if not path.exists():
            continue
        if path.read_text(encoding="utf-8").strip():
            present.append(song["num"])
        else:
            empty.append(song["num"])

    missing = [song["num"] for song in songs if song["num"] not in present]
    print(f"Lyrics files with content: {len(present)}/{EXPECTED_SONG_COUNT}")
    print(f"Empty files: {empty[:20] or 'none'}")
    print(f"Songs without lyrics: {missing[:30] or 'none'}"
          + (" ..." if len(missing) > 30 else ""))
    if manifest.get("count") != len(present):
        print("Warning: manifest count does not match files on disk. Re-run extract.")
    print("Review a few files by hand, then commit lyrics/ and the site changes.")
    return 0


def path_arg(value: str) -> Path:
    return Path(value).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="Show page count and detected song numbers"
    )
    inspect_parser.add_argument("--pdf", type=path_arg, required=True)
    inspect_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    inspect_parser.set_defaults(func=inspect_command)

    extract_parser = subparsers.add_parser(
        "extract", help="Write one lyrics file per detected song number"
    )
    extract_parser.add_argument("--pdf", type=path_arg, required=True)
    extract_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    extract_parser.add_argument("--lyrics-dir", type=path_arg, default=DEFAULT_LYRICS_DIR)
    extract_parser.add_argument(
        "--min-songs",
        type=int,
        default=450,
        help="Refuse to extract if fewer distinct songs are detected (default: 450)",
    )
    extract_parser.set_defaults(func=extract_command)

    verify_parser = subparsers.add_parser("verify", help="Check produced lyrics files")
    verify_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    verify_parser.add_argument("--lyrics-dir", type=path_arg, default=DEFAULT_LYRICS_DIR)
    verify_parser.set_defaults(func=verify_command)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
