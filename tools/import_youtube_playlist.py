#!/usr/bin/env python3
"""Import numbered videos from the known Thiruppugazh YouTube playlist.

The playlist is not ordered by song number. This tool maps a video from the
numeric prefix in its title (for example, ``017 Iyalisaiyil`` maps to song 17),
writes a reviewable CSV, and re-fetches the complete playlist plus current
video statuses before changing songs.json.

Examples:

  read -s "YOUTUBE_API_KEY?Paste API key: "; export YOUTUBE_API_KEY; echo
  python3 tools/import_youtube_playlist.py fetch
  python3 tools/import_youtube_playlist.py inspect
  python3 tools/import_youtube_playlist.py apply --confirm-mapping
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SONGS = ROOT / "songs.json"
DEFAULT_OUTPUT = ROOT / "youtube_playlist.csv"
PLAYLIST_ID = "PLFwcC0dtfDTiQSDIfbF9EJYEqTaA4iZ_6"
EXPECTED_SONG_COUNT = 503
MINIMUM_MAPPED_SONGS = 501
REPORT_VERSION = "2"
REPORT_MAX_AGE = timedelta(days=7)
FUTURE_CLOCK_SKEW = timedelta(minutes=5)
PLAYLIST_ITEMS_ENDPOINT = "https://www.googleapis.com/youtube/v3/playlistItems"
VIDEOS_ENDPOINT = "https://www.googleapis.com/youtube/v3/videos"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
TITLE_NUMBER_RE = re.compile(r"^\s*(\d{1,3})(?=\s|[-_.])")
PRIVACY_STATUSES = {"public", "private", "unlisted", "unavailable", "unknown"}
IGNORABLE_PRIVACY_STATUSES = {"private", "unavailable"}
MAPPING_STATUSES = {"mapped", "duplicate", "ignored_unnumbered"}
FIELDS = [
    "report_version",
    "playlist_id",
    "fetched_at",
    "position",
    "parsed_song_num",
    "song_title",
    "video_id",
    "video_title",
    "channel",
    "embeddable",
    "privacy_status",
    "mapping_status",
    "watch_url",
]


def load_songs(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        songs = json.load(handle)
    if not isinstance(songs, list):
        raise ValueError(f"{path} must contain a JSON array")
    if len(songs) != EXPECTED_SONG_COUNT:
        raise ValueError(
            f"{path} has {len(songs)} records; exactly {EXPECTED_SONG_COUNT} are required"
        )
    if [song.get("num") for song in songs] != list(range(1, EXPECTED_SONG_COUNT + 1)):
        raise ValueError(
            f"{path} song numbers must be unique and contiguous from 1 to "
            f"{EXPECTED_SONG_COUNT}"
        )
    for song in songs:
        if not isinstance(song.get("t"), str) or not song["t"].strip():
            raise ValueError(f"Song {song['num']} must have a non-empty Tamil title")
    return songs


def api_get(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{endpoint}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "thiruppugazh-503/2.0"},
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


def unique_ordered(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def parse_song_number(video_title: str) -> Optional[int]:
    match = TITLE_NUMBER_RE.match(video_title)
    if not match:
        return None
    song_num = int(match.group(1))
    if not 1 <= song_num <= EXPECTED_SONG_COUNT:
        raise ValueError(
            f"Playlist title has an out-of-range song number {song_num}: {video_title!r}"
        )
    return song_num


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
    validate_playlist_structure(items)
    return items


def fetch_video_statuses(api_key: str, video_ids: list[str]) -> dict[str, dict[str, str]]:
    statuses: dict[str, dict[str, str]] = {}
    for batch in chunks(unique_ordered(video_ids), 50):
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
        for video_id in unique_ordered(video_ids)
    }


def validate_playlist_structure(items: list[dict[str, Any]]) -> None:
    if not items:
        raise ValueError("YouTube returned an empty playlist")
    positions = [item["position"] for item in items]
    if positions != list(range(len(items))):
        raise ValueError("Playlist positions are missing, duplicated, or not contiguous from 0")
    for item in items:
        if not VIDEO_ID_RE.fullmatch(str(item.get("video_id", ""))):
            raise ValueError(f"Playlist contains an invalid video ID: {item.get('video_id')!r}")
        if not isinstance(item.get("video_title"), str):
            raise ValueError("Playlist contains an invalid video title")
        if not isinstance(item.get("channel"), str):
            raise ValueError("Playlist contains an invalid channel title")


def analyze_mapping(
    items: list[dict[str, Any]], statuses: dict[str, dict[str, str]]
) -> dict[str, Any]:
    """Validate title-number mappings and classify every playlist entry."""
    validate_playlist_structure(items)
    entries_by_song: dict[int, list[dict[str, Any]]] = defaultdict(list)
    unnumbered: list[dict[str, Any]] = []

    for item in items:
        song_num = parse_song_number(item["video_title"])
        if song_num is None:
            status = statuses[item["video_id"]]
            if status["privacy_status"] not in IGNORABLE_PRIVACY_STATUSES:
                raise ValueError(
                    "Refusing to ignore an unnumbered visible playlist entry at position "
                    f"{item['position'] + 1}: {item['video_title']!r}"
                )
            unnumbered.append(item)
        else:
            entries_by_song[song_num].append(item)

    mapping: dict[int, str] = {}
    classifications: dict[int, str] = {}
    used_video_ids: dict[str, int] = {}
    duplicate_entries: list[dict[str, Any]] = []

    for song_num in sorted(entries_by_song):
        entries = entries_by_song[song_num]
        video_ids = {entry["video_id"] for entry in entries}
        if len(video_ids) != 1:
            choices = ", ".join(
                f"position {entry['position'] + 1} ({entry['video_id']})" for entry in entries
            )
            raise ValueError(
                f"Song {song_num} has different candidate videos in the playlist: {choices}"
            )
        video_id = entries[0]["video_id"]
        if video_id in used_video_ids and used_video_ids[video_id] != song_num:
            raise ValueError(
                f"Video {video_id} is numbered as both song {used_video_ids[video_id]} "
                f"and song {song_num}"
            )
        used_video_ids[video_id] = song_num
        mapping[song_num] = video_id
        for index, entry in enumerate(entries):
            classifications[entry["position"]] = "mapped" if index == 0 else "duplicate"
            if index:
                duplicate_entries.append(entry)

    for item in unnumbered:
        classifications[item["position"]] = "ignored_unnumbered"

    if len(mapping) < MINIMUM_MAPPED_SONGS:
        raise ValueError(
            f"Only {len(mapping)} distinct numbered songs were found; at least "
            f"{MINIMUM_MAPPED_SONGS} are required. Review the playlist before applying."
        )

    missing = [
        song_num
        for song_num in range(1, EXPECTED_SONG_COUNT + 1)
        if song_num not in mapping
    ]
    return {
        "mapping": mapping,
        "missing": missing,
        "duplicates": duplicate_entries,
        "unnumbered": unnumbered,
        "classifications": classifications,
    }


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


def make_rows(
    items: list[dict[str, Any]],
    songs: list[dict[str, Any]],
    statuses: dict[str, dict[str, str]],
    fetched_at: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    analysis = analyze_mapping(items, statuses)
    rows: list[dict[str, Any]] = []
    for item in items:
        song_num = parse_song_number(item["video_title"])
        rows.append(
            {
                "report_version": REPORT_VERSION,
                "playlist_id": PLAYLIST_ID,
                "fetched_at": fetched_at,
                "position": item["position"],
                "parsed_song_num": "" if song_num is None else song_num,
                "song_title": "" if song_num is None else songs[song_num - 1]["t"],
                "video_id": item["video_id"],
                "video_title": item["video_title"],
                "channel": item["channel"],
                **statuses[item["video_id"]],
                "mapping_status": analysis["classifications"][item["position"]],
                "watch_url": (
                    f"https://www.youtube.com/watch?v={item['video_id']}"
                    f"&list={PLAYLIST_ID}&index={item['position'] + 1}"
                ),
            }
        )
    return rows, analysis


def fetch_command(args: argparse.Namespace) -> int:
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        print("Set YOUTUBE_API_KEY in your Terminal before running fetch.", file=sys.stderr)
        return 2

    songs = load_songs(args.songs)
    print(f"Fetching playlist {PLAYLIST_ID} ...", flush=True)
    items = fetch_playlist(api_key)
    video_ids = [item["video_id"] for item in items]
    print(f"Checking status for {len(unique_ordered(video_ids))} unique videos ...", flush=True)
    statuses = complete_statuses(fetch_video_statuses(api_key, video_ids), video_ids)
    fetched_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rows, analysis = make_rows(items, songs, statuses, fetched_at)

    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    embeddable = sum(
        statuses[video_id]["embeddable"] == "true"
        for video_id in analysis["mapping"].values()
    )
    print(f"Wrote {len(rows)} playlist entries to {args.output}")
    print(f"Distinct numbered songs mapped: {len(analysis['mapping'])}/{EXPECTED_SONG_COUNT}")
    print(f"Embeddable mapped videos: {embeddable}/{len(analysis['mapping'])}")
    print(f"Repeated identical entries ignored: {len(analysis['duplicates'])}")
    print(f"Unnumbered private/unavailable entries ignored: {len(analysis['unnumbered'])}")
    print(f"Missing song numbers: {analysis['missing'] or 'none'}")
    print("Run inspect, then apply --confirm-mapping after reviewing the report.")
    return 0


def validate_csv(
    rows: list[dict[str, str]], songs: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(songs) != EXPECTED_SONG_COUNT or not rows:
        raise ValueError(
            f"Exactly {EXPECTED_SONG_COUNT} songs and a non-empty playlist report are required"
        )

    report_versions = {row["report_version"] for row in rows}
    playlist_ids = {row["playlist_id"] for row in rows}
    fetched_values = {row["fetched_at"] for row in rows}
    if report_versions != {REPORT_VERSION}:
        raise ValueError("Playlist report version is invalid or mixed. Run fetch again.")
    if playlist_ids != {PLAYLIST_ID}:
        raise ValueError("Playlist report does not belong to the expected playlist")
    if len(fetched_values) != 1:
        raise ValueError("Playlist report contains mixed fetch timestamps")
    parse_fetched_at(next(iter(fetched_values)))

    items: list[dict[str, Any]] = []
    statuses: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows):
        try:
            position = int(row["position"])
        except ValueError as exc:
            raise ValueError(f"Invalid position at CSV row {index + 2}") from exc
        if position != index:
            raise ValueError(f"Invalid playlist position at CSV row {index + 2}")
        video_id = row["video_id"]
        if not VIDEO_ID_RE.fullmatch(video_id):
            raise ValueError(f"Invalid YouTube ID at CSV row {index + 2}: {video_id!r}")
        if row["embeddable"] not in {"true", "false"}:
            raise ValueError(f"Invalid embeddable status at CSV row {index + 2}")
        if row["privacy_status"] not in PRIVACY_STATUSES:
            raise ValueError(f"Invalid privacy status at CSV row {index + 2}")
        if row["mapping_status"] not in MAPPING_STATUSES:
            raise ValueError(f"Invalid mapping status at CSV row {index + 2}")
        item = {
            "position": position,
            "video_id": video_id,
            "video_title": row["video_title"],
            "channel": row["channel"],
        }
        items.append(item)
        new_status = {
            "embeddable": row["embeddable"],
            "privacy_status": row["privacy_status"],
        }
        if video_id in statuses and statuses[video_id] != new_status:
            raise ValueError(
                f"Conflicting statuses for repeated video {video_id} at CSV row {index + 2}"
            )
        statuses[video_id] = new_status

    analysis = analyze_mapping(items, statuses)
    for index, (row, item) in enumerate(zip(rows, items)):
        song_num = parse_song_number(item["video_title"])
        expected_num = "" if song_num is None else str(song_num)
        expected_title = "" if song_num is None else songs[song_num - 1]["t"]
        expected_status = analysis["classifications"][index]
        expected_url = (
            f"https://www.youtube.com/watch?v={item['video_id']}"
            f"&list={PLAYLIST_ID}&index={index + 1}"
        )
        if row["parsed_song_num"] != expected_num:
            raise ValueError(f"Invalid parsed song number at CSV row {index + 2}")
        if row["song_title"] != expected_title:
            raise ValueError(f"Stale or invalid song title at CSV row {index + 2}")
        if row["mapping_status"] != expected_status:
            raise ValueError(f"Invalid mapping classification at CSV row {index + 2}")
        if row["watch_url"] != expected_url:
            raise ValueError(f"Invalid watch URL at CSV row {index + 2}")
        if "\x00" in row["video_title"] or "\x00" in row["channel"]:
            raise ValueError(f"Invalid video metadata at CSV row {index + 2}")
    return items, analysis


def inspect_command(args: argparse.Namespace) -> int:
    songs = load_songs(args.songs)
    rows = read_rows(args.input)
    _, analysis = validate_csv(rows, songs)
    by_song = {
        int(row["parsed_song_num"]): row
        for row in rows
        if row["mapping_status"] == "mapped"
    }
    samples = [
        song_num
        for song_num in (1, 2, 3, 113, 188, 251, 375, 501, 502, 503)
        if song_num in by_song
    ]
    print(f"Playlist: {PLAYLIST_ID}")
    print(f"Fetched: {rows[0]['fetched_at']}")
    print(f"Raw playlist entries: {len(rows)}")
    print(f"Distinct numbered songs mapped: {len(analysis['mapping'])}/{EXPECTED_SONG_COUNT}")
    print(f"Missing song numbers: {analysis['missing'] or 'none'}")
    print("Representative number-based mappings:")
    for song_num in samples:
        row = by_song[song_num]
        print(
            f"  {song_num:>3}. {row['song_title']} -> {row['video_title']} "
            f"({row['watch_url']})"
        )
    print("Repeated identical entries ignored:")
    if analysis["duplicates"]:
        for item in analysis["duplicates"]:
            print(
                f"  Position {item['position'] + 1}: {item['video_title']} "
                f"({item['video_id']})"
            )
    else:
        print("  none")
    print("Unnumbered private/unavailable entries ignored:")
    if analysis["unnumbered"]:
        for item in analysis["unnumbered"]:
            print(
                f"  Position {item['position'] + 1}: {item['video_title']} "
                f"({item['video_id']})"
            )
    else:
        print("  none")
    return 0


def apply_command(args: argparse.Namespace) -> int:
    if not args.confirm_mapping:
        raise ValueError("Refusing to update songs.json without --confirm-mapping")
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        print("Set YOUTUBE_API_KEY in your Terminal before running apply.", file=sys.stderr)
        return 2

    songs = load_songs(args.songs)
    rows = read_rows(args.input)
    report_items, _ = validate_csv(rows, songs)

    print("Re-fetching the complete playlist before applying ...", flush=True)
    current_items = fetch_playlist(api_key)
    report_snapshot = [
        (item["position"], item["video_id"], item["video_title"])
        for item in report_items
    ]
    current_snapshot = [
        (item["position"], item["video_id"], item["video_title"])
        for item in current_items
    ]
    if current_snapshot != report_snapshot:
        raise ValueError(
            "The playlist changed after this report was fetched. Run fetch and inspect again."
        )

    video_ids = [item["video_id"] for item in current_items]
    print("Re-checking current video status ...", flush=True)
    statuses = complete_statuses(fetch_video_statuses(api_key, video_ids), video_ids)
    current_analysis = analyze_mapping(current_items, statuses)

    embeddable_count = 0
    mapping: dict[int, str] = current_analysis["mapping"]
    for song in songs:
        video_id = mapping.get(song["num"])
        if video_id:
            is_embeddable = statuses[video_id]["embeddable"] == "true"
            song["youtubeId"] = video_id
            song["youtubeEmbeddable"] = is_embeddable
            embeddable_count += int(is_embeddable)
        else:
            song.pop("youtubeId", None)
            song.pop("youtubeEmbeddable", None)

    formatted = "[\n" + ",\n".join(
        json.dumps(song, ensure_ascii=False, separators=(",", ":")) for song in songs
    ) + "\n]\n"
    args.songs.write_text(formatted, encoding="utf-8")
    exact_link_count = len(mapping) - embeddable_count
    print(
        f"Updated {args.songs}: {len(mapping)} exact video IDs; "
        f"{embeddable_count} embeddable, {exact_link_count} exact-link fallbacks"
    )
    print(
        f"Songs without a numbered playlist video retain playlist/search fallbacks: "
        f"{current_analysis['missing'] or 'none'}"
    )
    return 0


def path_arg(value: str) -> Path:
    return Path(value).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch", help="Fetch and classify the complete playlist snapshot"
    )
    fetch_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    fetch_parser.add_argument("--output", type=path_arg, default=DEFAULT_OUTPUT)
    fetch_parser.set_defaults(func=fetch_command)

    inspect_parser = subparsers.add_parser("inspect", help="Show mappings and exclusions")
    inspect_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    inspect_parser.add_argument("--input", type=path_arg, default=DEFAULT_OUTPUT)
    inspect_parser.set_defaults(func=inspect_command)

    apply_parser = subparsers.add_parser(
        "apply", help="Revalidate and apply title-number mappings to songs.json"
    )
    apply_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    apply_parser.add_argument("--input", type=path_arg, default=DEFAULT_OUTPUT)
    apply_parser.add_argument(
        "--confirm-mapping",
        "--confirm-order",
        dest="confirm_mapping",
        action="store_true",
        help="Confirm the reviewed number-based mapping (--confirm-order is an alias)",
    )
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
