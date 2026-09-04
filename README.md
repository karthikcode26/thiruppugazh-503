# திருப்புகழ் 503 — Thiruppugazh 503 Songs

A simple, mobile-first website listing all **503 Thiruppugazh songs** of Arunagirinathar.
Each song links to its lyrics on [kaumaram.com](https://kaumaram.com), a YouTube search,
and (optionally) an audio player.

## Features (Version 1)

- 📜 All 503 songs, numbered 1–503 (the popular ordering).
- 🔎 Search by **song number** or by **first word** — in Tamil *or* typed in English.
- 📖 **Lyrics** link opens the correct page on kaumaram.com.
- ▶️ **YouTube** link searches for the song.
- 🎵 **Audio player** appears automatically if an audio file exists at `audio/<number>.mp3`.
- 📱 Designed to fit an iPhone / phone browser.

## Files

| File | Purpose |
|------|---------|
| `index.html` | The searchable song list (home page). |
| `song.html`  | A single song's page (lyrics / YouTube / audio). |
| `app.js`     | Loads data, powers search + transliteration. |
| `styles.css` | Mobile-first styling. |
| `songs.json` | The 503-song data (number + Tamil first words + kaumaram catalog number). |
| `audio/`     | (Optional) Put `1.mp3`, `2.mp3`, … here to enable playback. |

## Run locally

You need a local web server (opening the file directly will block `fetch`).

```bash
# Python (already installed on most machines)
python3 -m http.server 8000
# then open http://localhost:8000
```

## Data format

`songs.json` is an array; each entry:

```json
{ "num": 16, "t": "அனைவருமருண்டு", "k": 431 }
```

- `num` — the song number shown to users (1–503).
- `t`   — Tamil first words (title / for search).
- `k`   — kaumaram catalog number, used to build the lyrics URL
          `https://kaumaram.com/thiru/nnt<k padded to 4 digits>_u.html`.

## Roadmap

- Add lyric images from the book.
- Add real audio files and specific YouTube video links.
- Favourites, recently viewed, offline support.

---

*Lyrics and audio are the property of kaumaram.com; this site only links to their pages.*
