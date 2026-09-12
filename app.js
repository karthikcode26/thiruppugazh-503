/* ===== Thiruppugazh 503 — list page logic ===== */

// Build the kaumaram lyrics URL from the catalog ("old") number.
// Pattern confirmed: https://kaumaram.com/thiru/nnt0006_u.html  (4-digit, zero-padded)
function kaumaramUrl(oldNo) {
  const padded = String(oldNo).padStart(4, "0");
  return `https://kaumaram.com/thiru/nnt${padded}_u.html`;
}

// Tamil -> Roman transliteration so people can also search by typing in English.
// It's approximate (good enough for "search by first word"), not scholarly.
// Consonants carry an inherent "a" which is removed when followed by a vowel
// sign or by pulli (்). We handle that by processing base consonant + sign.
const VOWEL_SIGNS = {
  "ா":"aa","ி":"i","ீ":"ee","ு":"u","ூ":"oo","ெ":"e","ே":"e","ை":"ai","ொ":"o","ோ":"o","ௌ":"au","்":""
};
const CONSONANTS = {
  "க":"k","ங":"ng","ச":"s","ஜ":"j","ஞ":"ny","ட":"t","ண":"n","த":"th","ந":"n","ன":"n",
  "ப":"p","ம":"m","ய":"y","ர":"r","ற":"r","ல":"l","ள":"l","ழ":"zh","வ":"v","ஷ":"sh","ஸ":"s","ஹ":"h"
};
const VOWELS = {
  "அ":"a","ஆ":"aa","இ":"i","ஈ":"ee","உ":"u","ஊ":"oo","எ":"e","ஏ":"e","ஐ":"ai","ஒ":"o","ஓ":"o","ஔ":"au","ஃ":"h"
};
function translitRaw(tamil) {
  const chars = Array.from(tamil);
  let out = "";
  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i];
    if (CONSONANTS[ch] !== undefined) {
      const next = chars[i + 1];
      if (next !== undefined && VOWEL_SIGNS[next] !== undefined) {
        out += CONSONANTS[ch] + VOWEL_SIGNS[next]; // consonant + explicit vowel (or pulli => none)
        i++;
      } else {
        out += CONSONANTS[ch] + "a"; // inherent 'a'
      }
    } else if (VOWELS[ch] !== undefined) {
      out += VOWELS[ch];
    } else if (/\s/.test(ch)) {
      out += " ";
    }
  }
  return out.toLowerCase();
}
// Normalize so common spelling variants all match (th<->t, zh<->l, doubled vowels, etc.)
function normalizeRoman(s) {
  return s
    .replace(/th/g, "t")
    .replace(/zh/g, "l")
    .replace(/sh/g, "s")
    .replace(/aa/g, "a")
    .replace(/ee/g, "i")
    .replace(/oo/g, "u")
    .replace(/ng/g, "n")
    .replace(/ny/g, "n")
    // Tamil consonants have no hard/soft distinction; fold voiced spellings
    // to their unvoiced form so "g/k", "d/t", "b/p", "j/s" all match.
    .replace(/g/g, "k")
    .replace(/d/g, "t")
    .replace(/b/g, "p")
    .replace(/j/g, "s")
    .replace(/w/g, "v")
    .replace(/c/g, "s")     // c heard as s (e.g. "che"/"se")
    .replace(/f/g, "p")     // no native f sound; heard as p
    .replace(/x/g, "s")
    .replace(/y/g, "i")     // glide y often heard as i
    .replace(/h/g, "")      // aspiration is inconsistently written/heard
    .replace(/(.)\1+/g, "$1"); // collapse any remaining doubles
}
function translit(tamil) {
  return normalizeRoman(translitRaw(tamil));
}

// ---- Phonetic "sounds-like" search ----
// Turn any query (Tamil script OR Roman letters) into the same normalized sound
// key we store per song, so spoken/typed words match by sound, not by spelling.
function soundKey(text) {
  const raw = String(text || "").trim();
  if (!raw) return "";
  // If it contains Tamil letters, transliterate; otherwise treat as Roman.
  const hasTamil = /[\u0B80-\u0BFF]/.test(raw);
  const roman = hasTamil ? translitRaw(raw) : raw.toLowerCase();
  // strip anything that isn't a-z (spaces/punctuation/diacritics) then fold sounds
  return normalizeRoman(roman.replace(/[^a-z]/g, ""));
}

// Levenshtein edit distance (small strings only), for fuzzy tolerance.
function editDistance(a, b) {
  if (a === b) return 0;
  const m = a.length, n = b.length;
  if (!m) return n;
  if (!n) return m;
  let prev = new Array(n + 1);
  let curr = new Array(n + 1);
  for (let j = 0; j <= n; j++) prev[j] = j;
  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
    }
    [prev, curr] = [curr, prev];
  }
  return prev[n];
}

// Score a song's sound key against the query sound key. Lower = better match;
// returns null if it should not match at all. Ranks: exact < prefix < substring
// < close-by-edit-distance.
function phoneticScore(songKey, qKey) {
  if (!qKey) return null;
  if (songKey === qKey) return 0;
  if (songKey.startsWith(qKey)) return 1;
  // For very short queries, only match at the start (prefix) to avoid flooding
  // results with every song that happens to contain a common sound.
  if (qKey.length < 3) return null;
  if (songKey.includes(qKey)) return 2;
  // fuzzy: allow a small number of edits, scaled to query length
  const tolerance = qKey.length <= 5 ? 1 : (qKey.length <= 8 ? 2 : 3);
  // compare against the song key's leading segment of similar length
  const head = songKey.slice(0, qKey.length + tolerance);
  const dist = editDistance(qKey, head);
  if (dist <= tolerance) return 3 + dist;
  return null;
}

let SONGS = [];
let AUDIO = {};                 // audio.json manifest (song number -> { main, extra })
let AUDIO_READY = false;        // true once audio.json has finished loading

const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
const countEl = document.getElementById("count");
const rangeEl = document.getElementById("rangebar");
const toTopEl = document.getElementById("to-top");
const store = window.TPStore || null;
const RANGE_SIZE = 100;

// Build the range jump chips (1-50, 51-100, ... up to the number of songs).
function buildRangeBar() {
  if (!rangeEl || !SONGS.length) return;
  const total = SONGS.length;
  let html = "";
  for (let start = 1; start <= total; start += RANGE_SIZE) {
    const end = Math.min(start + RANGE_SIZE - 1, total);
    const isLast = start + RANGE_SIZE > total;
    const label = isLast ? `${start}+` : `${start}–${end}`;
    html += `<button class="range-chip" type="button" data-jump="${start}">${label}</button>`;
  }
  rangeEl.innerHTML = html;
}

// Smooth-scroll so a given song row sits just below the sticky search/range bars.
function jumpToSong(num) {
  const row = listEl.querySelector(`.song-row[data-num="${num}"]`);
  if (!row) return;
  const sticky = document.querySelector(".stickytop");
  const offset = (sticky ? sticky.offsetHeight : 0) + 8;
  const y = row.getBoundingClientRect().top + window.pageYOffset - offset;
  window.scrollTo({ top: Math.max(y, 0), behavior: "smooth" });
}

// One shared audio element so only one song plays at a time.
const player = new Audio();
let playingNum = null;
let queue = [];        // playlist of song numbers (favourites that have audio)
let queueIndex = -1;   // position in the queue; -1 = not in playlist mode

function mainSrcFor(num) {
  const info = window.TPAudio ? window.TPAudio.forSong(AUDIO, num) : null;
  return info && info.main ? info.main.src : "";
}

function stopAudio() {
  player.pause();
  const prev = playingNum;
  playingNum = null;
  queue = [];
  queueIndex = -1;
  if (prev != null) paintPlayBtn(prev, false);
  updateNowPlaying();
}

// Play a single song (from a row button). Leaves/clears any playlist.
function toggleAudio(num) {
  const src = mainSrcFor(num);
  if (!src) return;
  if (playingNum === num && !player.paused) {
    stopAudio();
    return;
  }
  queue = [];
  queueIndex = -1;
  playSong(num);
}

// Internal: load and play a song number, updating UI.
function playSong(num) {
  const src = mainSrcFor(num);
  if (!src) return;
  const prev = playingNum;
  if (prev != null && prev !== num) paintPlayBtn(prev, false);
  player.src = src;
  playingNum = num;
  player.play().then(() => paintPlayBtn(num, true)).catch(() => paintPlayBtn(num, false));
  updateNowPlaying();
  updateSeek();
}

// Start a playlist from a list of song numbers (skips those without audio).
function playQueue(nums) {
  const playable = nums.filter((n) => !!mainSrcFor(n));
  if (!playable.length) return false;
  queue = playable;
  queueIndex = 0;
  playSong(queue[0]);
  return true;
}

function playNext() {
  if (queueIndex < 0 || queueIndex + 1 >= queue.length) { stopAudio(); return; }
  queueIndex += 1;
  playSong(queue[queueIndex]);
}

function playPrev() {
  if (queueIndex <= 0) return;
  queueIndex -= 1;
  playSong(queue[queueIndex]);
}

function togglePausePlay() {
  if (playingNum == null) return;
  if (player.paused) {
    player.play().then(() => { paintPlayBtn(playingNum, true); updateNowPlaying(); });
  } else {
    player.pause();
    paintPlayBtn(playingNum, false);
    updateNowPlaying();
  }
}

function paintPlayBtn(num, playing) {
  const btn = listEl.querySelector(`.play-btn[data-num="${num}"]`);
  if (!btn) return;
  btn.classList.toggle("on", playing);
  btn.textContent = playing ? "⏸" : "▶";
  btn.setAttribute("aria-label", (playing ? "Pause" : "Play") + ` audio for song ${num}`);
}

// When a track ends: advance the playlist, or clear single-play state.
player.addEventListener("ended", () => {
  const n = playingNum;
  if (n != null) paintPlayBtn(n, false);
  if (queueIndex >= 0) {
    playNext();
  } else {
    playingNum = null;
    updateNowPlaying();
  }
});

// ---- Now-playing bar ----
let seeking = false;   // true while the user is dragging the seek slider

function formatTime(sec) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

function updateNowPlaying() {
  const bar = document.getElementById("nowplaying");
  if (!bar) return;
  if (playingNum == null) { bar.hidden = true; return; }
  const song = songByNum(playingNum);
  const title = song ? `${song.num}. ${song.t}` : `Song ${playingNum}`;
  const inQueue = queueIndex >= 0;
  bar.querySelector(".np-title").textContent = title;
  bar.querySelector(".np-pos").textContent = inQueue ? `${queueIndex + 1} / ${queue.length}` : "";
  bar.querySelector(".np-play").textContent = player.paused ? "▶" : "⏸";
  bar.querySelector(".np-prev").hidden = !inQueue;
  bar.querySelector(".np-next").hidden = !inQueue;
  bar.hidden = false;
}

// Refresh the seek slider + time labels from the audio element.
function updateSeek() {
  const bar = document.getElementById("nowplaying");
  if (!bar || bar.hidden) return;
  const seek = bar.querySelector(".np-seek");
  const cur = bar.querySelector(".np-cur");
  const dur = bar.querySelector(".np-dur");
  const total = player.duration;
  cur.textContent = formatTime(player.currentTime);
  dur.textContent = isFinite(total) ? formatTime(total) : "0:00";
  if (!seeking && isFinite(total) && total > 0) {
    seek.value = String(Math.round((player.currentTime / total) * 1000));
  }
}

// Keep the seek bar in sync as the track plays / loads.
player.addEventListener("timeupdate", updateSeek);
player.addEventListener("loadedmetadata", updateSeek);
player.addEventListener("durationchange", updateSeek);

function render(items) {
  if (!items.length) {
    listEl.innerHTML = `<li class="empty">பாடல் இல்லை · No matching songs</li>`;
    countEl.textContent = "";
    return;
  }
  const html = items.map((s) => {
    const fav = store && store.isFavourite(s.num);
    const hasAudio = !!mainSrcFor(s.num);
    const playing = hasAudio && playingNum === s.num && !player.paused;
    const playBtn = hasAudio ? `
      <button class="play-btn${playing ? " on" : ""}" type="button"
              data-num="${s.num}"
              aria-label="${playing ? "Pause" : "Play"} audio for song ${s.num}">${playing ? "⏸" : "▶"}</button>` : "";
    return `
    <li class="song-row" data-num="${s.num}">
      <a class="song" href="song.html?n=${s.num}">
        <span class="num">${s.num}</span>
        <span class="title">${escapeHtml(s.t)}</span>
        <span class="chev">›</span>
      </a>
      ${playBtn}
      <button class="fav-btn${fav ? " on" : ""}" type="button"
              data-num="${s.num}"
              aria-pressed="${fav ? "true" : "false"}"
              aria-label="Toggle favourite for song ${s.num}">${fav ? "★" : "☆"}</button>
    </li>`;
  }).join("");
  listEl.innerHTML = html;
  countEl.textContent = `${items.length} / ${SONGS.length} பாடல்கள்`;
}

function songByNum(num) {
  return SONGS.find((s) => s.num === Number(num));
}

function renderShelf(shelfId, chipsId, nums) {
  const shelf = document.getElementById(shelfId);
  const chips = document.getElementById(chipsId);
  if (!shelf || !chips) return;
  const valid = (nums || []).map(songByNum).filter(Boolean);
  if (!valid.length) {
    shelf.hidden = true;
    chips.innerHTML = "";
    return;
  }
  chips.innerHTML = valid.map((s) => `
    <a class="chip" href="song.html?n=${s.num}">
      <span class="chip-num">${s.num}</span>
      <span class="chip-title">${escapeHtml(s.t)}</span>
    </a>`).join("");
  shelf.hidden = false;
}

function renderShelves() {
  if (!store) return;
  renderShelf("recent-shelf", "recent-chips", store.getRecent());
  renderShelf("fav-shelf", "fav-chips", store.getFavourites());
  // Show "Play favourites" once the audio manifest is loaded and at least one
  // favourite has audio. Before the manifest loads, don't force-hide it — that
  // avoids a race where an early render (or pageshow/visibilitychange) would
  // wrongly hide it while AUDIO is still empty.
  const playFav = document.getElementById("playfav-btn");
  if (playFav && AUDIO_READY) {
    const anyAudio = store.getFavourites().some((n) => !!mainSrcFor(n));
    playFav.hidden = !anyAudio;
  }
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => (
    { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]
  ));
}

function filter(q) {
  const raw = String(q || "").trim();
  if (!raw) return SONGS;

  // Number search stays exact and takes priority.
  if (/^\d+$/.test(raw)) {
    return SONGS.filter((s) => String(s.num).startsWith(raw) || String(s.num) === raw);
  }

  const lower = raw.toLowerCase();
  const qKey = soundKey(raw);

  // Score every song: direct Tamil/Roman substring wins; otherwise phonetic.
  const scored = [];
  for (const s of SONGS) {
    let score = null;
    if (s.t.toLowerCase().includes(lower)) score = 0;          // exact Tamil substring
    else {
      const ps = phoneticScore(s._key, qKey);                  // sounds-like
      if (ps !== null) score = ps;
    }
    if (score !== null) scored.push({ s, score, num: s.num });
  }
  // Best matches first; stable by song number within the same score.
  scored.sort((a, b) => (a.score - b.score) || (a.num - b.num));
  return scored.map((x) => x.s);
}

// Hide the range bar while searching/filtering (it only makes sense for the full list).
function updateRangeBarVisibility() {
  if (!rangeEl) return;
  rangeEl.hidden = searchEl.value.trim().length > 0;
}

// Voice search: fill the search box from spoken words using the browser's
// Web Speech API. Hidden where unsupported (e.g. iOS Safari). Tamil first,
// with a graceful result either way — the text just flows into normal search.
function setupVoiceSearch() {
  const micBtn = document.getElementById("mic-btn");
  if (!micBtn) return;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return; // unsupported browser: leave the mic hidden

  // iOS Safari/WebKit exposes webkitSpeechRecognition but it does not actually
  // work (speech recognition is unavailable to web pages on iOS). Detect iOS —
  // including iPadOS, which reports as "Macintosh" but is touch-capable — and
  // keep the mic hidden there so users don't see a button that fails.
  const ua = navigator.userAgent || "";
  const isIOS = /iPad|iPhone|iPod/.test(ua) ||
    (/Macintosh/.test(ua) && typeof navigator.maxTouchPoints === "number" && navigator.maxTouchPoints > 1);
  if (isIOS) return; // leave the mic hidden on iOS

  micBtn.hidden = false;
  let recognizing = false;
  let recognition = null;

  micBtn.addEventListener("click", () => {
    if (recognizing && recognition) { recognition.stop(); return; }
    recognition = new SR();
    recognition.lang = "ta-IN";        // Tamil; the engine still returns text we can search
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      recognizing = true;
      micBtn.classList.add("listening");
      micBtn.setAttribute("aria-label", "Listening… tap to stop");
    };
    const done = () => {
      recognizing = false;
      micBtn.classList.remove("listening");
      micBtn.setAttribute("aria-label", "Voice search");
    };
    recognition.onend = done;
    recognition.onerror = done;
    recognition.onresult = (event) => {
      const said = (event.results[0] && event.results[0][0] && event.results[0][0].transcript) || "";
      if (said) {
        searchEl.value = said.trim();
        render(filter(searchEl.value));
        updateRangeBarVisibility();
        searchEl.focus();
      }
    };
    try { recognition.start(); } catch (e) { done(); }
  });
}

function init(data) {
  SONGS = data.map((s) => ({ ...s, _roman: translit(s.t), _key: soundKey(s.t) }));
  render(SONGS);
  renderShelves();
  buildRangeBar();
  updateRangeBarVisibility();
  // Load the audio manifest, then re-render rows (play buttons) and refresh the
  // shelves so "Play favourites" is decided once the audio data is known.
  if (window.TPAudio) {
    window.TPAudio.load().then((m) => {
      AUDIO = m || {};
      AUDIO_READY = true;
      render(filter(searchEl.value));
      renderShelves();
    });
  } else {
    AUDIO_READY = true; // no audio support; shelves can settle immediately
  }
  searchEl.addEventListener("input", () => {
    render(filter(searchEl.value));
    updateRangeBarVisibility();
  });

  setupVoiceSearch();

  // Range jump chips.
  if (rangeEl) {
    rangeEl.addEventListener("click", (e) => {
      const chip = e.target.closest(".range-chip");
      if (!chip) return;
      jumpToSong(Number(chip.dataset.jump));
    });
  }

  // Play favourites (auto-advance through favourited songs that have audio).
  const playFavBtn = document.getElementById("playfav-btn");
  if (playFavBtn && store) {
    playFavBtn.addEventListener("click", () => {
      playQueue(store.getFavourites());
    });
  }

  // Now-playing bar controls.
  const np = document.getElementById("nowplaying");
  if (np) {
    np.querySelector(".np-prev").addEventListener("click", playPrev);
    np.querySelector(".np-next").addEventListener("click", playNext);
    np.querySelector(".np-play").addEventListener("click", togglePausePlay);
    np.querySelector(".np-stop").addEventListener("click", stopAudio);

    // Seek slider: drag to scrub through the current track.
    const seek = np.querySelector(".np-seek");
    const beginSeek = () => { seeking = true; };
    const commitSeek = () => {
      if (isFinite(player.duration) && player.duration > 0) {
        player.currentTime = (Number(seek.value) / 1000) * player.duration;
      }
      seeking = false;
      updateSeek();
    };
    seek.addEventListener("input", () => {
      seeking = true;
      const cur = np.querySelector(".np-cur");
      if (isFinite(player.duration) && player.duration > 0) {
        cur.textContent = formatTime((Number(seek.value) / 1000) * player.duration);
      }
    });
    seek.addEventListener("mousedown", beginSeek);
    seek.addEventListener("touchstart", beginSeek, { passive: true });
    seek.addEventListener("change", commitSeek);
  }

  // Back-to-top button: show after scrolling down a bit.
  if (toTopEl) {
    const onScroll = () => { toTopEl.hidden = window.pageYOffset < 400; };
    window.addEventListener("scroll", onScroll, { passive: true });
    toTopEl.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
    onScroll();
  }

  // Play button (event delegation so it works after re-render).
  listEl.addEventListener("click", (e) => {
    const play = e.target.closest(".play-btn");
    if (!play) return;
    e.preventDefault();
    toggleAudio(Number(play.dataset.num));
  });

  // Favourite toggle (event delegation so it works after re-render).
  if (store) {
    listEl.addEventListener("click", (e) => {
      const btn = e.target.closest(".fav-btn");
      if (!btn) return;
      const num = Number(btn.dataset.num);
      const nowFav = store.toggleFavourite(num);
      btn.classList.toggle("on", nowFav);
      btn.textContent = nowFav ? "★" : "☆";
      btn.setAttribute("aria-pressed", nowFav ? "true" : "false");
      renderShelves();
    });

    // iOS Safari restores this page from the back-forward cache without re-running
    // the script, so the shelves would stay stale after viewing/favouriting a song.
    // Refresh them whenever the page is shown again or becomes visible, and also
    // re-sync each row's star state.
    const refresh = () => { render(filter(searchEl.value)); renderShelves(); };
    window.addEventListener("pageshow", refresh);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") refresh();
    });
  }
}

fetch("songs.json?v=27")
  .then((r) => { if (!r.ok) throw new Error("load failed"); return r.json(); })
  .then(init)
  .catch(() => {
    listEl.innerHTML = `<li class="empty">பாடல்களை ஏற்ற முடியவில்லை.<br>Could not load songs.json.</li>`;
  });

// expose helper for song page (shared file)
window.kaumaramUrl = kaumaramUrl;
