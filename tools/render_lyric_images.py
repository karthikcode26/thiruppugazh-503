#!/usr/bin/env python3
"""Render each Thiruppugazh song's page(s) to an image.

The PDF displays correctly but its Tamil text layer is a broken legacy (TSCu)
font, so extracting selectable text produces scrambled characters. Rendering the
page to an image captures the lyrics exactly as printed, with no OCR or font
reversal needed.

Each song page prints its number on an early line as "பாடல் N" (the Tamil word
is garbled by the font, but the digits N are clean ASCII). This tool reads that
number to name each image lyrics/<N>.png, so extra pages (front matter, section
dividers) are skipped and pages that are out of song order are still placed
correctly. Consecutive pages that repeat the same number are stacked into one
image (multi-page songs).

Run on the machine that has the PDF:

  python3 -m pip install --user pymupdf
  python3 tools/render_lyric_images.py inspect --pdf "ThiruppugazhTamil.pdf"
  python3 tools/render_lyric_images.py render  --pdf "ThiruppugazhTamil.pdf"
  python3 tools/render_lyric_images.py verify
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SONGS = ROOT / "songs.json"
DEFAULT_LYRICS_DIR = ROOT / "lyrics"
EXPECTED_SONG_COUNT = 503
MANIFEST_NAME = "manifest.json"
DEFAULT_DPI = 150
# The Tamil word "பாடல்" (song) is rendered by the broken TSCu font as a fixed,
# consistent byte sequence that PyMuPDF surfaces as these code points:
#   0xC0 0xA1 0xBC 0xF8  ("À¡¼ø")
# The real song number is the integer immediately following it. Anchoring on
# this marker avoids picking up raga/tala/rhythm numbers elsewhere on the page.
PADAL_MARKER = "\u00c0\u00a1\u00bc\u00f8"
SONG_NUMBER_RE = re.compile(re.escape(PADAL_MARKER) + r"\s*(\d{1,3})\b")


def load_songs(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        songs = json.load(handle)
    if not isinstance(songs, list) or len(songs) != EXPECTED_SONG_COUNT:
        raise ValueError(f"{path} must contain exactly {EXPECTED_SONG_COUNT} songs")
    if [song.get("num") for song in songs] != list(range(1, EXPECTED_SONG_COUNT + 1)):
        raise ValueError("songs.json numbers must be contiguous from 1")
    return songs


def load_doc(pdf_path: Path):
    try:
        import fitz  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "PyMuPDF is required. Install it with:\n"
            "  python3 -m pip install --user pymupdf"
        ) from exc
    import fitz

    if not pdf_path.exists():
        raise ValueError(f"PDF not found: {pdf_path}")
    return fitz.open(str(pdf_path))


def detect_song_number(page_text: str) -> Optional[int]:
    """Read the song number that follows the garbled "பாடல்" marker.

    The number is only accepted when it directly follows the fixed marker byte
    sequence, so raga/tala/rhythm numbers elsewhere on the page are ignored. A
    page without the marker (front matter, dividers, continuations) returns
    None.
    """
    match = SONG_NUMBER_RE.search(page_text)
    if not match:
        return None
    value = int(match.group(1))
    return value if 1 <= value <= EXPECTED_SONG_COUNT else None


def collect_page_numbers(doc) -> list[Optional[int]]:
    return [detect_song_number(doc[i].get_text("text") or "") for i in range(len(doc))]


def group_pages(page_numbers: list[Optional[int]]) -> dict[int, list[int]]:
    """Map song number -> list of 0-based page indices, in document order.

    A numbered page always starts (or extends) that song's group. A page with no
    detected number is treated as a continuation only when the page directly
    before it was part of a song group, so wrapped lyrics without a repeated
    header stay with the correct song. A gap of one or more unnumbered pages
    ends the current song, so a later stray page cannot attach to it.
    """
    groups: dict[int, list[int]] = {}
    current: Optional[int] = None
    previous_was_song_page = False
    for index, number in enumerate(page_numbers):
        if number is not None:
            current = number
            groups.setdefault(number, []).append(index)
            previous_was_song_page = True
        elif current is not None and previous_was_song_page:
            # continuation page immediately after a page of the current song
            groups[current].append(index)
            previous_was_song_page = True
        else:
            current = None
            previous_was_song_page = False
    return groups


def find_noncontiguous(groups: dict[int, list[int]]) -> list[int]:
    """Song numbers whose pages are not consecutive in the document."""
    bad: list[int] = []
    for number, pages in groups.items():
        if pages != list(range(pages[0], pages[0] + len(pages))):
            bad.append(number)
    return sorted(bad)


def inspect_command(args: argparse.Namespace) -> int:
    load_songs(args.songs)
    with load_doc(args.pdf) as doc:
        total = len(doc)
        numbers = collect_page_numbers(doc)
    groups = group_pages(numbers)
    detected = sorted(groups)
    missing = [n for n in range(1, EXPECTED_SONG_COUNT + 1) if n not in groups]
    multi = {n: len(p) for n, p in groups.items() if len(p) > 1}

    print(f"PDF pages: {total}")
    print(f"Pages with a detected song number: {sum(1 for n in numbers if n)}")
    print(f"Distinct songs detected: {len(detected)}/{EXPECTED_SONG_COUNT}")
    print(f"Missing song numbers: {missing[:30] or 'none'}"
          + (" ..." if len(missing) > 30 else ""))
    print(f"Songs spanning multiple pages: {len(multi)}"
          + (f" (e.g. {dict(list(multi.items())[:5])})" if multi else ""))
    noncontiguous = find_noncontiguous(groups)
    print(f"Songs with NON-CONSECUTIVE pages (must be fixed): {noncontiguous[:20] or 'none'}")
    print()
    print("First detected songs (song -> 0-based page indices):")
    for number in detected[:8]:
        print(f"  song {number}: pages {groups[number]}")
    print()
    if noncontiguous:
        print("A song maps to pages that are not next to each other. This usually means a")
        print("divider/extra page was read as a song number. Share those pages and we will")
        print("tighten detection before rendering.")
    elif len(detected) >= EXPECTED_SONG_COUNT - 10:
        print("Detection looks good. Run: render")
    else:
        print("Detection is low. Share one page's first lines so the header rule can be tuned.")
    return 0


def render_command(args: argparse.Namespace) -> int:
    import fitz

    load_songs(args.songs)
    args.lyrics_dir.mkdir(parents=True, exist_ok=True)

    with load_doc(args.pdf) as doc:
        numbers = collect_page_numbers(doc)
        groups = group_pages(numbers)
        if len(groups) < args.min_songs:
            raise ValueError(
                f"Only {len(groups)} songs detected; at least {args.min_songs} expected. "
                "Run inspect and confirm the header numbers are read before rendering."
            )
        noncontiguous = find_noncontiguous(groups)
        if noncontiguous:
            raise ValueError(
                "These songs map to non-consecutive pages, which usually means an extra "
                f"page was read as a song number: {noncontiguous[:20]}. Run inspect and "
                "share those pages so detection can be tightened before rendering."
            )

        for existing in args.lyrics_dir.glob("*.png"):
            existing.unlink()

        zoom = args.dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        written = 0
        multi_page: list[int] = []
        for number in sorted(groups):
            page_indices = groups[number]
            if len(page_indices) > 1:
                multi_page.append(number)
            pixmaps = [doc[i].get_pixmap(matrix=matrix, alpha=False) for i in page_indices]
            if len(pixmaps) == 1:
                combined = pixmaps[0]
            else:
                combined = stack_pixmaps(fitz, pixmaps)
            out_path = args.lyrics_dir / f"{number}.png"
            combined.save(str(out_path))
            written += 1

    produced = sorted(
        int(p.stem) for p in args.lyrics_dir.glob("*.png") if p.stem.isdigit()
    )
    missing = [n for n in range(1, EXPECTED_SONG_COUNT + 1) if n not in produced]
    manifest = {
        "type": "image",
        "ext": "png",
        "count": written,
        "songs": produced,
        "missing": missing,
        "multi_page": multi_page,
    }
    (args.lyrics_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Rendered {written} song images to {args.lyrics_dir} at {args.dpi} DPI")
    print(f"Songs spanning multiple pages (stacked): {multi_page[:20] or 'none'}")
    print(f"Songs without an image: {missing[:30] or 'none'}"
          + (" ..." if len(missing) > 30 else ""))
    print(f"Manifest: {args.lyrics_dir / MANIFEST_NAME}")
    print("Next: run verify, then open a few images before committing.")
    return 0


def stack_pixmaps(fitz, pixmaps):
    """Vertically stack page pixmaps into one image."""
    width = max(pixmap.width for pixmap in pixmaps)
    height = sum(pixmap.height for pixmap in pixmaps)
    canvas = fitz.Pixmap(pixmaps[0].colorspace, fitz.IRect(0, 0, width, height), False)
    canvas.clear_with(255)
    y = 0
    for pixmap in pixmaps:
        canvas.copy(pixmap, fitz.IRect(0, y, pixmap.width, y + pixmap.height))
        y += pixmap.height
    return canvas


def verify_command(args: argparse.Namespace) -> int:
    songs = load_songs(args.songs)
    manifest_path = args.lyrics_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise ValueError(f"Manifest not found: {manifest_path}. Run render first.")

    present: list[int] = []
    empty: list[int] = []
    for song in songs:
        path = args.lyrics_dir / f"{song['num']}.png"
        if not path.exists():
            continue
        if path.stat().st_size > 0:
            present.append(song["num"])
        else:
            empty.append(song["num"])

    missing = [song["num"] for song in songs if song["num"] not in present]
    total_bytes = sum(
        p.stat().st_size for p in args.lyrics_dir.glob("*.png")
    )
    print(f"Song images present: {len(present)}/{EXPECTED_SONG_COUNT}")
    print(f"Empty images: {empty[:20] or 'none'}")
    print(f"Songs without an image: {missing[:30] or 'none'}"
          + (" ..." if len(missing) > 30 else ""))
    print(f"Total image size: {total_bytes / 1_000_000:.1f} MB")
    print("Open a few images by hand, then commit lyrics/ and the site changes.")
    return 0


def path_arg(value: str) -> Path:
    return Path(value).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Show detected song pages")
    inspect_parser.add_argument("--pdf", type=path_arg, required=True)
    inspect_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    inspect_parser.set_defaults(func=inspect_command)

    render_parser = subparsers.add_parser("render", help="Render one image per song")
    render_parser.add_argument("--pdf", type=path_arg, required=True)
    render_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    render_parser.add_argument("--lyrics-dir", type=path_arg, default=DEFAULT_LYRICS_DIR)
    render_parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    render_parser.add_argument("--min-songs", type=int, default=450)
    render_parser.set_defaults(func=render_command)

    verify_parser = subparsers.add_parser("verify", help="Check produced images")
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
