#!/usr/bin/env python3
"""Render each Thiruppugazh song's page to an image using a fixed page map.

The PDF displays correctly but its Tamil text layer uses a broken legacy (TSCu)
font, so extracting selectable text is unreliable and the printed song numbers
cannot be trusted from the text layer. Instead, this tool uses an explicit,
human-verified page-to-song map: rendering each mapped page to an image captures
the lyrics exactly as printed, with no OCR and no dependence on the text layer.

The map below was established by manual inspection of the book. Songs 502 and
503 were placed early in the book; every other song runs in sequence:

    PDF pages 14-125  -> songs 1-112     (song = page - 13)
    PDF page  126     -> song 502
    PDF pages 127-311 -> songs 113-297   (song = page - 14)
    PDF page  312     -> song 503
    PDF pages 313-516 -> songs 298-501   (song = page - 15)

(PDF page numbers here are 1-based, as shown in a PDF viewer.)

Run on the machine that has the PDF:

  python3 -m pip install --user pymupdf
  python3 tools/render_lyric_images.py check  --pdf "ThiruppugazhTamil.pdf"
  python3 tools/render_lyric_images.py render --pdf "ThiruppugazhTamil.pdf"
  python3 tools/render_lyric_images.py verify
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SONGS = ROOT / "songs.json"
DEFAULT_LYRICS_DIR = ROOT / "lyrics"
EXPECTED_SONG_COUNT = 503
MANIFEST_NAME = "manifest.json"
DEFAULT_DPI = 200

# Human-verified ranges. Each entry maps an inclusive 1-based PDF page range to
# an inclusive song-number range. Sizes must match within each entry. Edit only
# this table if a spot-check shows a page is off.
PAGE_MAP_RANGES = [
    # (pdf_page_start, pdf_page_end, song_start, song_end)
    (14, 125, 1, 112),
    (126, 126, 502, 502),
    (127, 311, 113, 297),
    (312, 312, 503, 503),
    (313, 516, 298, 501),
]


def build_song_to_page() -> dict[int, int]:
    """Expand PAGE_MAP_RANGES into an exact song_number -> 1-based PDF page map."""
    song_to_page: dict[int, int] = {}
    for page_start, page_end, song_start, song_end in PAGE_MAP_RANGES:
        page_span = page_end - page_start + 1
        song_span = song_end - song_start + 1
        if page_span != song_span:
            raise ValueError(
                f"Map range pages {page_start}-{page_end} ({page_span}) does not match "
                f"songs {song_start}-{song_end} ({song_span})"
            )
        for offset in range(page_span):
            song = song_start + offset
            page = page_start + offset
            if song in song_to_page:
                raise ValueError(f"Song {song} is mapped by more than one range")
            song_to_page[song] = page
    return song_to_page


def make_cropper(margin: int = 24, white_threshold: int = 245):
    """Return a function that trims near-white margins around a saved PNG.

    Uses Pillow. The image is converted to grayscale to find the bounding box of
    any pixel darker than white_threshold (the printed text), then cropped to
    that box plus a small uniform margin so the lyrics fill the frame.
    """
    try:
        from PIL import Image, ImageChops, ImageOps  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Pillow is required for cropping. Install it with:\n"
            "  python3 -m pip install --user pillow\n"
            "Or run render with --no-crop to skip trimming."
        ) from exc
    from PIL import Image, ImageChops

    def crop(path: Path) -> None:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            gray = rgb.convert("L")
            # Anything darker than the threshold counts as content.
            mask = gray.point(lambda value: 0 if value >= white_threshold else 255)
            bbox = mask.getbbox()
            if not bbox:
                return  # blank page; leave as-is
            left = max(bbox[0] - margin, 0)
            top = max(bbox[1] - margin, 0)
            right = min(bbox[2] + margin, rgb.width)
            bottom = min(bbox[3] + margin, rgb.height)
            rgb.crop((left, top, right, bottom)).save(path, optimize=True)

    return crop


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


def validate_map(total_pages: int) -> dict[int, int]:
    """Return the song->page map, ensuring it is complete and within the PDF."""
    song_to_page = build_song_to_page()
    missing = [n for n in range(1, EXPECTED_SONG_COUNT + 1) if n not in song_to_page]
    if missing:
        raise ValueError(f"Page map does not cover songs: {missing[:20]}")
    if len(song_to_page) != EXPECTED_SONG_COUNT:
        raise ValueError("Page map does not cover exactly 503 songs")
    max_page = max(song_to_page.values())
    if max_page > total_pages:
        raise ValueError(
            f"Page map references PDF page {max_page} but the PDF has {total_pages} pages"
        )
    return song_to_page


def check_command(args: argparse.Namespace) -> int:
    load_songs(args.songs)
    with load_doc(args.pdf) as doc:
        total = len(doc)
    song_to_page = validate_map(total)
    print(f"PDF pages: {total}")
    print(f"Songs mapped: {len(song_to_page)}/{EXPECTED_SONG_COUNT}")
    print("Sample song -> 1-based PDF page (spot-check these in your PDF viewer):")
    for song in (1, 112, 113, 297, 298, 501, 502, 503):
        print(f"  song {song:>3} -> page {song_to_page[song]}")
    print()
    print("If those pages show the right songs, run: render")
    return 0


def render_command(args: argparse.Namespace) -> int:
    import fitz

    load_songs(args.songs)
    args.lyrics_dir.mkdir(parents=True, exist_ok=True)

    with load_doc(args.pdf) as doc:
        total = len(doc)
        song_to_page = validate_map(total)

        for existing in args.lyrics_dir.glob("*.png"):
            existing.unlink()

        zoom = args.dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        written = 0
        cropper = make_cropper(margin=args.margin) if not args.no_crop else None
        for song in range(1, EXPECTED_SONG_COUNT + 1):
            page_index = song_to_page[song] - 1  # 1-based map -> 0-based index
            pixmap = doc[page_index].get_pixmap(matrix=matrix, alpha=False)
            out_path = args.lyrics_dir / f"{song}.png"
            pixmap.save(str(out_path))
            if cropper is not None:
                cropper(out_path)
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
        "page_map": {str(s): p for s, p in build_song_to_page().items()},
    }
    (args.lyrics_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Rendered {written} song images to {args.lyrics_dir} at {args.dpi} DPI")
    print(f"Songs without an image: {missing[:30] or 'none'}")
    print(f"Manifest: {args.lyrics_dir / MANIFEST_NAME}")
    print("Next: run verify, then spot-check songs 1, 112, 113, 297, 298, 501, 502, 503.")
    return 0


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
    total_bytes = sum(p.stat().st_size for p in args.lyrics_dir.glob("*.png"))
    print(f"Song images present: {len(present)}/{EXPECTED_SONG_COUNT}")
    print(f"Empty images: {empty[:20] or 'none'}")
    print(f"Songs without an image: {missing[:30] or 'none'}")
    print(f"Total image size: {total_bytes / 1_000_000:.1f} MB")
    print("Spot-check several images against the book, then commit lyrics/ and deploy.")
    return 0


def path_arg(value: str) -> Path:
    return Path(value).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Validate the page map against the PDF")
    check_parser.add_argument("--pdf", type=path_arg, required=True)
    check_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    check_parser.set_defaults(func=check_command)

    render_parser = subparsers.add_parser("render", help="Render one image per song")
    render_parser.add_argument("--pdf", type=path_arg, required=True)
    render_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    render_parser.add_argument("--lyrics-dir", type=path_arg, default=DEFAULT_LYRICS_DIR)
    render_parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    render_parser.add_argument(
        "--margin", type=int, default=24,
        help="White-space margin (pixels) kept around the cropped lyrics",
    )
    render_parser.add_argument(
        "--no-crop", action="store_true",
        help="Skip auto-cropping the white margins (keeps the full page)",
    )
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
