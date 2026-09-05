#!/usr/bin/env python3
"""Import the known 503-song YouTube playlist into songs.json.

The playlist is ordered to match the book's song numbers. This tool uses the
YouTube Data API to fetch an exact-ID snapshot, writes a reviewable CSV, and
re-fetches the playlist and current video statuses before changing songs.json.

Examples:

  read -s "YOUTUBE_API_KEY?Paste API key: "; export YOUTUBE_API_KEY; echo
  python3 tools/import_youtube_playlist.py fetch
  python3 tools/import_youtube_playlist.py inspect
  python3 tools/import_youtube_playlist.py apply --confirm-order
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SONGS = ROOT / "songs.json"
DEFAULT_OUTPUT = ROOT / "youtube_playlist.csv"
PLAYLIST_ID = "PLFwcC0dtfDTiQSDIfbF9EJYEqTaA4iZ_6"
EXPECTED_COUNT = 503
REPORT_VERSION = "1"
REPORT_MAX_AGE = timedelta(days=7)
FUTURE_CLOCK_SKEW = timedelta(minutes=5)
PLAYLIST_ITEMS_ENDPOINT = "https://www.googleapis.com/youtube/v3/playlistItems"
VIDEOS_ENDPOINT = "https://www.googleapis.com/youtube/v3/videos"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
PRIVACY_STATUSES = {"public", "private", "unlisted", "unavailable", "unknown"}
FIELDS = [
    "report_version",
    "playlist_id",
    "fetched_at",
    "position",
    "song_num",
    "song_title",
    "video_id",
    "video_title",
    "channel",
    "embeddable",
    "privacy_status",
    "title_contains_song",
    "watch_url",
]


def load_songs(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        songs = json.load(handle)
    if not isinstance(songs, list):
        raise ValueError(f"{path} must contain a JSON array")
    if len(songs) != EXPECTED_COUNT:
        raise ValueError(
            f"{path} has {len(songs)} records; exactly {EXPECTED_COUNT} are required"
        )
    if [song.get("num") for song in songs] != list(range(1, EXPECTED_COUNT + 1)):
        raise ValueError(
            f"{path} song numbers must be unique and contiguous from 1 to "
            f"{EXPECTED_COUNT}"
        )
    for song in songs:
        if not isinstance(song.get("t"), str) or not song["t"].strip():
            raise ValueError(f"Song {song['num']} must have a non-empty Tamil title")
    return songs


def api_get(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{endpoint}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "thiruppugazh-503/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(body)["error"]["message"]
        except (KeyError, TypeError, json.JSONDecodeError):
            message = body[:500] or str(exc)
        raise RuntimeError(f"YouTube API HTTP {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach the YouTube API: {exc.reason}") from exc


def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def normalized(value: str) -> str:
    return "".join(
        character.casefold()
        for character in unicodedata.normalize("NFKC", value)
        if character.isalnum()
    )


def fetch_playlist(api_key: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token = ""
    while True:
        params: dict[str, Any] = {
            "part": "snippet,contentDetails",
            "playlistId": PLAYLIST_ID,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        payload = api_get(PLAYLIST_ITEMS_ENDPOINT, params)
        for item in payload.get("items", []):
            snippet = item.get("snippet", {})
            video_id = item.get("contentDetails", {}).get("videoId", "")
            if not VIDEO_ID_RE.fullmatch(video_id):
                raise ValueError(f"Playlist contains an invalid video ID: {video_id!r}")
            try:
                position = int(snippet.get("position", -1))
            except (TypeError, ValueError) as exc:
                raise ValueError("Playlist contains an invalid position") from exc
            items.append(
                {
                    "position": position,
                    "video_id": video_id,
                    "video_title": str(snippet.get("title", "")),
                    "channel": str(
                        snippet.get("videoOwnerChannelTitle", "")
                        or snippet.get("channelTitle", "")
                    ),
                }
            )
        page_token = str(payload.get("nextPageToken", ""))
        if not page_token:
            break
    items.sort(key=lambda item: item["position"])
    return items


def fetch_video_statuses(api_key: str, video_ids: list[str]) -> dict[str, dict[str, str]]:
    statuses: dict[str, dict[str, str]] = {}
    for batch in chunks(video_ids, 50):
        payload = api_get(
            VIDEOS_ENDPOINT,
            {
                "part": "status",
                "id": ",".join(batch),
                "maxResults": 50,
                "key": api_key,
            },
        )
        for item in payload.get("items", []):
            video_id = str(item.get("id", ""))
            if video_id not in batch:
                raise ValueError(f"YouTube returned an unexpected video ID: {video_id!r}")
            status = item.get("status", {})
            privacy_status = str(status.get("privacyStatus", "unknown"))
            if privacy_status not in PRIVACY_STATUSES:
                privacy_status = "unknown"
            statuses[video_id] = {
                "embeddable": "true" if status.get("embeddable") is True else "false",
                "privacy_status": privacy_status,
            }
    return statuses


def complete_statuses(
    statuses: dict[str, dict[str, str]], video_ids: list[str]
) -> dict[str, dict[str, str]]:
    return {
        video_id: statuses.get(
            video_id,
            {"embeddable": "false", "privacy_status": "unavailable"},
        )
        for video_id in video_ids
    }


def validate_positions(items: list[dict[str, Any]]) -> None:
    if len(items) != EXPECTED_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_COUNT} playlist items but YouTube returned {len(items)}. "
            "Do not apply until the playlist count and order are corrected."
        )
    positions = [item["position"] for item in items]
    if positions != list(range(EXPECTED_COUNT)):
        raise ValueError("Playlist positions are missing, duplicated, or not contiguous from 0")
    video_ids = [item["video_id"] for item in items]
    if len(set(video_ids)) != EXPECTED_COUNT:
        raise ValueError("Playlist contains duplicate video IDs; review its order before applying")


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ValueError(f"Playlist CSV not found: {path}. Run fetch first.")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise ValueError(
                "Playlist CSV columns do not match this importer version. Run fetch again."
            )
        return list(reader)


def parse_fetched_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid report timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError("Report timestamp must include a UTC offset")
    fetched_at = parsed.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if fetched_at > now + FUTURE_CLOCK_SKEW:
        raise ValueError("Playlist report timestamp is in the future")
    if now - fetched_at > REPORT_MAX_AGE:
        raise ValueError("Playlist report is older than 7 days. Run fetch again.")
    return fetched_at


def fetch_command(args: argparse.Namespace) -> int:
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        print("Set YOUTUBE_API_KEY in your Terminal before running fetch.", file=sys.stderr)
        return 2

    songs = load_songs(args.songs)
    print(f"Fetching playlist {PLAYLIST_ID} ...", flush=True)
    items = fetch_playlist(api_key)
    validate_positions(items)

    video_ids = [item["video_id"] for item in items]
    print(f"Checking embeddability for {len(items)} videos ...", flush=True)
    statuses = complete_statuses(fetch_video_statuses(api_key, video_ids), video_ids)
    fetched_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    rows: list[dict[str, Any]] = []
    for item, song in zip(items, songs):
        song_text = normalized(song["t"])
        video_text = normalized(item["video_title"])
        rows.append(
            {
                "report_version": REPORT_VERSION,
                "playlist_id": PLAYLIST_ID,
                "fetched_at": fetched_at,
                "position": item["position"],
                "song_num": song["num"],
                "song_title": song["t"],
                "video_id": item["video_id"],
                "video_title": item["video_title"],
                "channel": item["channel"],
                **statuses[item["video_id"]],
                "title_contains_song": (
                    "true" if song_text and song_text in video_text else "false"
                ),
                "watch_url": (
                    f"https://www.youtube.com/watch?v={item['video_id']}"
                    f"&list={PLAYLIST_ID}&index={song['num']}"
                ),
            }
        )

    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    embeddable = sum(row["embeddable"] == "true" for row in rows)
    title_matches = sum(row["title_contains_song"] == "true" for row in rows)
    print(f"Wrote {len(rows)} ordered playlist rows to {args.output}")
    print(f"Embeddable: {embeddable}/{len(rows)}")
    print(f"Video title contains the Tamil song title: {title_matches}/{len(rows)}")
    print("Run inspect, then apply --confirm-order after checking the sample rows.")
    return 0


def validate_csv(rows: list[dict[str, str]], songs: list[dict[str, Any]]) -> None:
    if len(songs) != EXPECTED_COUNT or len(rows) != EXPECTED_COUNT:
        raise ValueError(
            f"Exactly {EXPECTED_COUNT} songs and {EXPECTED_COUNT} CSV rows are required; "
            f"found {len(songs)} songs and {len(rows)} rows"
        )

    report_versions = {row["report_version"] for row in rows}
    playlist_ids = {row["playlist_id"] for row in rows}
    fetched_values = {row["fetched_at"] for row in rows}
    if report_versions != {REPORT_VERSION}:
        raise ValueError("Playlist report version is invalid or mixed. Run fetch again.")
    if playlist_ids != {PLAYLIST_ID}:
        raise ValueError("Playlist report does not belong to the expected 503-song playlist")
    if len(fetched_values) != 1:
        raise ValueError("Playlist report contains mixed fetch timestamps")
    parse_fetched_at(next(iter(fetched_values)))

    seen_ids: set[str] = set()
    for index, (row, song) in enumerate(zip(rows, songs)):
        expected_num = index + 1
        if row["position"] != str(index) or row["song_num"] != str(expected_num):
            raise ValueError(f"Invalid playlist position/song number at CSV row {index + 2}")
        if row["song_title"] != song["t"]:
            raise ValueError(
                f"Playlist CSV is stale for song {expected_num}: "
                f"expected {song['t']!r}, found {row['song_title']!r}"
            )
        video_id = row["video_id"]
        if not VIDEO_ID_RE.fullmatch(video_id):
            raise ValueError(f"Invalid YouTube ID for song {expected_num}: {video_id!r}")
        if video_id in seen_ids:
            raise ValueError(f"Duplicate YouTube ID at song {expected_num}: {video_id}")
        seen_ids.add(video_id)
        if row["embeddable"] not in {"true", "false"}:
            raise ValueError(f"Invalid embeddable status for song {expected_num}")
        if row["privacy_status"] not in PRIVACY_STATUSES:
            raise ValueError(f"Invalid privacy status for song {expected_num}")
        expected_title_match = (
            "true"
            if normalized(song["t"])
            and normalized(song["t"]) in normalized(row["video_title"])
            else "false"
        )
        if row["title_contains_song"] != expected_title_match:
            raise ValueError(f"Invalid title comparison flag for song {expected_num}")
        expected_url = (
            f"https://www.youtube.com/watch?v={video_id}"
            f"&list={PLAYLIST_ID}&index={expected_num}"
        )
        if row["watch_url"] != expected_url:
            raise ValueError(f"Invalid watch URL for song {expected_num}")
        if "\x00" in row["video_title"] or "\x00" in row["channel"]:
            raise ValueError(f"Invalid video metadata for song {expected_num}")


def inspect_command(args: argparse.Namespace) -> int:
    songs = load_songs(args.songs)
    rows = read_rows(args.input)
    validate_csv(rows, songs)
    sample_numbers = sorted({1, 2, 3, len(rows) // 2, len(rows) - 1, len(rows)})
    print(f"Playlist: {PLAYLIST_ID}")
    print(f"Fetched: {rows[0]['fetched_at']}")
    print(f"Playlist rows: {len(rows)}")
    print("Check these positions against YouTube before applying:")
    for num in sample_numbers:
        row = rows[num - 1]
        print(
            f"  {num:>3}. {row['song_title']} -> {row['video_title']} "
            f"({row['watch_url']})"
        )
    not_embeddable = [row for row in rows if row["embeddable"] != "true"]
    title_mismatches = [row for row in rows if row["title_contains_song"] != "true"]
    print(f"Not embeddable/unavailable at fetch time: {len(not_embeddable)}")
    print(f"Titles needing manual comparison: {len(title_mismatches)}")
    return 0


def apply_command(args: argparse.Namespace) -> int:
    if not args.confirm_order:
        raise ValueError(
            "Refusing to map playlist position to song number without --confirm-order"
        )
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        print("Set YOUTUBE_API_KEY in your Terminal before running apply.", file=sys.stderr)
        return 2

    songs = load_songs(args.songs)
    rows = read_rows(args.input)
    validate_csv(rows, songs)

    print("Re-fetching the playlist before applying ...", flush=True)
    current_items = fetch_playlist(api_key)
    validate_positions(current_items)
    report_mapping = [
        (int(row["position"]), row["video_id"])
        for row in rows
    ]
    current_mapping = [
        (item["position"], item["video_id"])
        for item in current_items
    ]
    if current_mapping != report_mapping:
        raise ValueError(
            "The playlist changed after this report was fetched. Run fetch and inspect again."
        )

    video_ids = [row["video_id"] for row in rows]
    print("Re-checking current video embeddability ...", flush=True)
    statuses = complete_statuses(fetch_video_statuses(api_key, video_ids), video_ids)

    embeddable_count = 0
    for song, row in zip(songs, rows):
        video_id = row["video_id"]
        is_embeddable = statuses[video_id]["embeddable"] == "true"
        song["youtubeId"] = video_id
        song["youtubeEmbeddable"] = is_embeddable
        embeddable_count += int(is_embeddable)

    formatted = "[\n" + ",\n".join(
        json.dumps(song, ensure_ascii=False, separators=(",", ":")) for song in songs
    ) + "\n]\n"
    args.songs.write_text(formatted, encoding="utf-8")
    unavailable_count = EXPECTED_COUNT - embeddable_count
    print(
        f"Updated {args.songs}: {EXPECTED_COUNT} exact video IDs; "
        f"{embeddable_count} embeddable, {unavailable_count} exact-link fallbacks"
    )
    return 0


def path_arg(value: str) -> Path:
    return Path(value).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch the exact playlist snapshot")
    fetch_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    fetch_parser.add_argument("--output", type=path_arg, default=DEFAULT_OUTPUT)
    fetch_parser.set_defaults(func=fetch_command)

    inspect_parser = subparsers.add_parser("inspect", help="Show sample mappings and warnings")
    inspect_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    inspect_parser.add_argument("--input", type=path_arg, default=DEFAULT_OUTPUT)
    inspect_parser.set_defaults(func=inspect_command)

    apply_parser = subparsers.add_parser(
        "apply", help="Revalidate and apply exact playlist IDs to songs.json"
    )
    apply_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    apply_parser.add_argument("--input", type=path_arg, default=DEFAULT_OUTPUT)
    apply_parser.add_argument("--confirm-order", action="store_true")
    apply_parser.set_defaults(func=apply_command)

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
