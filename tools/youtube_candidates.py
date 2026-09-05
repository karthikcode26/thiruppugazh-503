#!/usr/bin/env python3
"""Discover, review, and apply YouTube videos for the 503-song list.

This tool intentionally keeps automatically discovered candidates separate from
production data. A video is embedded by the website only after a person approves
it and the ``apply`` command writes its 11-character ID to ``songs.json``.

Typical workflow:

  export YOUTUBE_API_KEY="..."       # never commit the key
  python3 tools/youtube_candidates.py discover --limit 90
  python3 tools/youtube_candidates.py review
  open youtube_review.html
  # Review candidates and download youtube_approvals.csv in the browser.
  python3 tools/youtube_candidates.py apply

Run ``python3 tools/youtube_candidates.py COMMAND --help`` for options.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SONGS = ROOT / "songs.json"
DEFAULT_CANDIDATES = ROOT / "youtube_candidates.csv"
DEFAULT_APPROVALS = ROOT / "youtube_approvals.csv"
DEFAULT_REVIEW = ROOT / "youtube_review.html"
SEARCH_ENDPOINT = "https://www.googleapis.com/youtube/v3/search"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
CANDIDATE_FIELDS = [
    "num",
    "song_title",
    "query",
    "rank",
    "video_id",
    "video_title",
    "channel",
    "published_at",
    "watch_url",
]


def load_songs(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        songs = json.load(handle)
    if not isinstance(songs, list):
        raise ValueError(f"{path} must contain a JSON array")
    nums = [song.get("num") for song in songs]
    if nums != list(range(1, len(songs) + 1)):
        raise ValueError("songs.json numbers must be unique and contiguous from 1")
    return songs


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def youtube_search(api_key: str, query: str, max_results: int) -> list[dict[str, str]]:
    params = urllib.parse.urlencode(
        {
            "part": "snippet",
            "type": "video",
            "videoEmbeddable": "true",
            "maxResults": max_results,
            "q": query,
            "key": api_key,
        }
    )
    request = urllib.request.Request(
        f"{SEARCH_ENDPOINT}?{params}",
        headers={"Accept": "application/json", "User-Agent": "thiruppugazh-503/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(body)["error"]["message"]
        except (KeyError, TypeError, json.JSONDecodeError):
            message = body[:500] or str(exc)
        raise RuntimeError(f"YouTube API HTTP {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach the YouTube API: {exc.reason}") from exc

    results: list[dict[str, str]] = []
    for item in payload.get("items", []):
        video_id = item.get("id", {}).get("videoId", "")
        snippet = item.get("snippet", {})
        if VIDEO_ID_RE.fullmatch(video_id):
            results.append(
                {
                    "video_id": video_id,
                    "video_title": snippet.get("title", ""),
                    "channel": snippet.get("channelTitle", ""),
                    "published_at": snippet.get("publishedAt", ""),
                }
            )
    return results


def discover(args: argparse.Namespace) -> int:
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        print("Set YOUTUBE_API_KEY in your terminal before running discover.", file=sys.stderr)
        print('Example: export YOUTUBE_API_KEY="your-key"', file=sys.stderr)
        return 2

    songs = load_songs(args.songs)
    existing = read_csv(args.output)
    searched = {int(row["num"]) for row in existing if row.get("num", "").isdigit()}
    confirmed = {
        int(song["num"])
        for song in songs
        if VIDEO_ID_RE.fullmatch(str(song.get("youtubeId", "")))
    }

    selected = [
        song
        for song in songs
        if args.start <= song["num"] <= args.end
        and song["num"] not in searched
        and song["num"] not in confirmed
    ][: args.limit]

    if not selected:
        print("No unsearched songs in the selected range.")
        return 0

    new_file = not args.output.exists() or args.output.stat().st_size == 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    with args.output.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANDIDATE_FIELDS)
        if new_file:
            writer.writeheader()

        for song in selected:
            num = int(song["num"])
            title = str(song["t"])
            query = f'Thiruppugazh "{title}" திருப்புகழ்'
            print(f"[{completed + 1}/{len(selected)}] Song {num}: {title}", flush=True)
            try:
                results = youtube_search(api_key, query, args.max_results)
            except RuntimeError as exc:
                print(f"Stopped after {completed} songs. {exc}", file=sys.stderr)
                print("Progress already written to the candidate CSV; rerun later to resume.", file=sys.stderr)
                return 1

            if not results:
                writer.writerow(
                    {
                        "num": num,
                        "song_title": title,
                        "query": query,
                        "rank": 0,
                        "video_id": "",
                        "video_title": "No results",
                        "channel": "",
                        "published_at": "",
                        "watch_url": "",
                    }
                )
            else:
                for rank, result in enumerate(results, start=1):
                    writer.writerow(
                        {
                            "num": num,
                            "song_title": title,
                            "query": query,
                            "rank": rank,
                            **result,
                            "watch_url": f'https://www.youtube.com/watch?v={result["video_id"]}',
                        }
                    )
            handle.flush()
            completed += 1
            if args.delay:
                time.sleep(args.delay)

    print(f"Added candidates for {completed} songs to {args.output}")
    remaining = len(
        [
            song
            for song in songs
            if song["num"] not in searched
            and song["num"] not in confirmed
            and song not in selected
        ]
    )
    print(f"Run discover again on a later day to continue. Remaining before recount: {remaining}")
    return 0


def candidate_groups(path: Path) -> list[dict[str, Any]]:
    rows = read_csv(path)
    if not rows:
        raise ValueError(f"No candidates found in {path}. Run discover first.")

    grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
    titles: dict[int, str] = {}
    for row in rows:
        raw_num = row.get("num", "")
        if not raw_num.isdigit():
            raise ValueError(f"Invalid song number in {path}: {raw_num!r}")
        num = int(raw_num)
        song_title = row.get("song_title", "")
        if num in titles and titles[num] != song_title:
            raise ValueError(
                f"Mixed candidate titles for song {num}: "
                f"{titles[num]!r} and {song_title!r}. "
                "Delete those rows and discover the song again."
            )
        titles[num] = song_title
        video_id = row.get("video_id", "")
        if video_id:
            if not VIDEO_ID_RE.fullmatch(video_id):
                raise ValueError(f"Invalid YouTube ID for song {num}: {video_id!r}")
            grouped[num].append(
                {
                    "videoId": video_id,
                    "title": row.get("video_title", ""),
                    "channel": row.get("channel", ""),
                    "publishedAt": row.get("published_at", ""),
                    "url": row.get("watch_url", "")
                    or f"https://www.youtube.com/watch?v={video_id}",
                }
            )
        else:
            grouped[num]  # retain songs for which search returned no results

    return [
        {"num": num, "title": titles[num], "candidates": grouped[num]}
        for num in sorted(grouped)
    ]


def review(args: argparse.Namespace) -> int:
    groups = candidate_groups(args.candidates)
    data_json = json.dumps(groups, ensure_ascii=False).replace("<", "\\u003c")
    page = REVIEW_HTML.replace("__CANDIDATE_DATA__", data_json)
    args.output.write_text(page, encoding="utf-8")
    print(f"Created {args.output} with {len(groups)} songs ready for review.")
    print(f"Open it in a browser: open {args.output}")
    return 0


def apply_approvals(args: argparse.Namespace) -> int:
    songs = load_songs(args.songs)
    by_num = {int(song["num"]): song for song in songs}
    groups = candidate_groups(args.candidates)
    allowed = {
        int(group["num"]): {candidate["videoId"] for candidate in group["candidates"]}
        for group in groups
    }
    for group in groups:
        num = int(group["num"])
        if num not in by_num:
            raise ValueError(f"Candidate data refers to unknown song {num}")
        current_title = str(by_num[num].get("t", ""))
        if group["title"] != current_title:
            raise ValueError(
                f"Candidate data for song {num} is stale: "
                f"expected title {current_title!r}, found {group['title']!r}. "
                "Delete its candidate rows and discover it again."
            )
    approvals = read_csv(args.approvals)
    if not approvals:
        raise ValueError(f"No approvals found in {args.approvals}")

    seen: set[int] = set()
    approved = removed = ignored = 0
    for row in approvals:
        raw_num = row.get("num", "")
        if not raw_num.isdigit():
            raise ValueError(f"Invalid approval song number: {raw_num!r}")
        num = int(raw_num)
        if num in seen:
            raise ValueError(f"Duplicate approval row for song {num}")
        seen.add(num)
        if num not in by_num:
            raise ValueError(f"Approval refers to unknown song {num}")

        decision = row.get("decision", "").strip().lower()
        video_id = row.get("video_id", "").strip()
        if decision == "approved":
            if not VIDEO_ID_RE.fullmatch(video_id):
                raise ValueError(f"Invalid approved YouTube ID for song {num}: {video_id!r}")
            if video_id not in allowed.get(num, set()):
                raise ValueError(
                    f"Song {num} approval {video_id} was not one of its discovered candidates"
                )
            by_num[num]["youtubeId"] = video_id
            approved += 1
        elif decision == "none":
            if "youtubeId" in by_num[num]:
                del by_num[num]["youtubeId"]
                removed += 1
        elif not decision:
            ignored += 1
        else:
            raise ValueError(f"Unknown decision for song {num}: {decision!r}")

    formatted = "[\n" + ",\n".join(json.dumps(song, ensure_ascii=False, separators=(",", ":")) for song in songs) + "\n]\n"
    args.songs.write_text(formatted, encoding="utf-8")
    print(f"Applied {approved} approved videos; removed {removed}; ignored {ignored} undecided rows.")
    print(f"Updated {args.songs}")
    return 0


def status(args: argparse.Namespace) -> int:
    songs = load_songs(args.songs)
    confirmed = sum(
        1 for song in songs if VIDEO_ID_RE.fullmatch(str(song.get("youtubeId", "")))
    )
    rows = read_csv(args.candidates)
    searched = {int(row["num"]) for row in rows if row.get("num", "").isdigit()}
    approvals = read_csv(args.approvals)
    decided = sum(1 for row in approvals if row.get("decision", "").strip())
    print(f"Confirmed in songs.json: {confirmed}/{len(songs)}")
    print(f"Candidate searches completed: {len(searched)}/{len(songs)}")
    print(f"Review decisions downloaded: {decided}/{len(searched)}")
    return 0


def path_arg(value: str) -> Path:
    return Path(value).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="Search YouTube and append candidates")
    discover_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    discover_parser.add_argument("--output", type=path_arg, default=DEFAULT_CANDIDATES)
    discover_parser.add_argument("--start", type=int, default=1)
    discover_parser.add_argument("--end", type=int, default=503)
    discover_parser.add_argument(
        "--limit",
        type=int,
        default=90,
        help="Maximum new songs this run (default 90, leaving room under daily API search quota)",
    )
    discover_parser.add_argument("--max-results", type=int, choices=range(1, 6), default=3)
    discover_parser.add_argument("--delay", type=float, default=0.1)
    discover_parser.set_defaults(func=discover)

    review_parser = subparsers.add_parser("review", help="Generate a local candidate review page")
    review_parser.add_argument("--candidates", type=path_arg, default=DEFAULT_CANDIDATES)
    review_parser.add_argument("--output", type=path_arg, default=DEFAULT_REVIEW)
    review_parser.set_defaults(func=review)

    apply_parser = subparsers.add_parser("apply", help="Apply downloaded review decisions to songs.json")
    apply_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    apply_parser.add_argument("--candidates", type=path_arg, default=DEFAULT_CANDIDATES)
    apply_parser.add_argument("--approvals", type=path_arg, default=DEFAULT_APPROVALS)
    apply_parser.set_defaults(func=apply_approvals)

    status_parser = subparsers.add_parser("status", help="Show discovery/review/application progress")
    status_parser.add_argument("--songs", type=path_arg, default=DEFAULT_SONGS)
    status_parser.add_argument("--candidates", type=path_arg, default=DEFAULT_CANDIDATES)
    status_parser.add_argument("--approvals", type=path_arg, default=DEFAULT_APPROVALS)
    status_parser.set_defaults(func=status)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "start") and (args.start < 1 or args.end < args.start):
        parser.error("--start/--end range is invalid")
    if hasattr(args, "limit") and args.limit < 1:
        parser.error("--limit must be at least 1")
    try:
        return int(args.func(args))
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


REVIEW_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review Thiruppugazh YouTube candidates</title>
<style>
:root{font-family:system-ui,-apple-system,sans-serif;color:#241c15;background:#f8f1e7}
*{box-sizing:border-box}body{margin:0}.app{max-width:920px;margin:auto;padding:16px}
header{position:sticky;top:0;z-index:2;background:#f8f1e7;padding:10px 0;border-bottom:1px solid #ddcfbd}
h1{font-size:22px;margin:0 0 8px}.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
button{min-height:44px;border:0;border-radius:10px;padding:9px 14px;font-weight:700;cursor:pointer}
.primary{background:#b52d23;color:white}.secondary{background:#e7dac8;color:#241c15}.none{background:#555;color:white}
.progress{font-size:14px;color:#6e6050}.song{background:white;border:1px solid #ddcfbd;border-radius:14px;padding:16px;margin-top:16px}
.song h2{margin:0 0 4px;font-size:22px}.state{color:#6e6050;margin-bottom:14px}.candidates{display:grid;gap:12px}
.card{display:grid;grid-template-columns:180px 1fr;gap:12px;border:2px solid #eee2d2;border-radius:12px;padding:10px}
.card.chosen{border-color:#2e7d32;background:#f0faf0}.card img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:8px;background:#111}
.card h3{font-size:16px;margin:0 0 4px}.meta{font-size:13px;color:#6e6050;margin-bottom:8px}.card a{color:#b52d23}
.empty{padding:22px;text-align:center;color:#6e6050}.download{margin-left:auto}
@media(max-width:600px){.card{grid-template-columns:1fr}.card img{max-width:none}.app{padding:10px}header{top:0}}
</style>
</head>
<body><div class="app">
<header><h1>YouTube candidate review</h1><div class="toolbar">
<button class="secondary" id="prev">← Previous</button><button class="secondary" id="next">Next →</button>
<span class="progress" id="progress"></span>
<button class="primary download" id="download">Download approvals CSV</button>
</div></header><main id="main"></main></div>
<script>
const groups=__CANDIDATE_DATA__;
const storageKey="thiruppugazh-youtube-approvals-v1";
const mainElement=document.getElementById('main');
const progressElement=document.getElementById('progress');
const previousButton=document.getElementById('prev');
const nextButton=document.getElementById('next');
const downloadButton=document.getElementById('download');
let choices=JSON.parse(localStorage.getItem(storageKey)||"{}");let index=0;
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function save(){localStorage.setItem(storageKey,JSON.stringify(choices));}
function choose(num,videoId){choices[num]=videoId?{decision:"approved",video_id:videoId}:{decision:"none",video_id:""};save();render();}
function render(){if(!groups.length){mainElement.innerHTML='<p class="empty">No candidates.</p>';return}const g=groups[index];const choice=choices[g.num];
progressElement.textContent=`Song ${index+1} of ${groups.length} · ${Object.keys(choices).length} decided`;
const cards=g.candidates.length?g.candidates.map(c=>`<article class="card ${choice?.video_id===c.videoId?'chosen':''}"><img loading="lazy" src="https://i.ytimg.com/vi/${encodeURIComponent(c.videoId)}/hqdefault.jpg" alt=""><div><h3>${esc(c.title)}</h3><div class="meta">${esc(c.channel)} · ${esc((c.publishedAt||'').slice(0,10))}</div><p><a href="${esc(c.url)}" target="_blank" rel="noopener">Open on YouTube ↗</a></p><button class="primary" data-id="${esc(c.videoId)}">${choice?.video_id===c.videoId?'✓ Approved':'Approve this video'}</button></div></article>`).join(''):'<p class="empty">Search returned no embeddable candidates.</p>';
mainElement.innerHTML=`<section class="song"><h2>${g.num}. ${esc(g.title)}</h2><div class="state">${choice?choice.decision==='approved'?'Approved '+esc(choice.video_id):'Marked: no suitable video':'Not reviewed'}</div><div class="candidates">${cards}</div><p><button class="none" id="markNone">No suitable video</button></p></section>`;
mainElement.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>choose(g.num,b.dataset.id));document.getElementById('markNone').onclick=()=>choose(g.num,'');previousButton.disabled=index===0;nextButton.disabled=index===groups.length-1;window.scrollTo(0,0)}
previousButton.onclick=()=>{if(index>0){index--;render()}};nextButton.onclick=()=>{if(index<groups.length-1){index++;render()}};
downloadButton.onclick=()=>{const lines=['num,decision,video_id'];for(const g of groups){const c=choices[g.num]||{decision:'',video_id:''};lines.push([g.num,c.decision,c.video_id].join(','))}const blob=new Blob([lines.join('\n')+'\n'],{type:'text/csv'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='youtube_approvals.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
render();
</script></body></html>'''


if __name__ == "__main__":
    raise SystemExit(main())
