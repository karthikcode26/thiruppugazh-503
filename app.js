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
    .replace(/(.)\1+/g, "$1"); // collapse any remaining doubles
}
function translit(tamil) {
  return normalizeRoman(translitRaw(tamil));
}

let SONGS = [];
let AUDIO = {};                 // audio.json manifest (song number -> { main, extra })

const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
const countEl = document.getElementById("count");
const store = window.TPStore || null;

// One shared audio element so only one song plays at a time.
const player = new Audio();
let playingNum = null;

function mainSrcFor(num) {
  const info = window.TPAudio ? window.TPAudio.forSong(AUDIO, num) : null;
  return info && info.main ? info.main.src : "";
}

function stopAudio() {
  player.pause();
  const prev = playingNum;
  playingNum = null;
  if (prev != null) paintPlayBtn(prev, false);
}

function toggleAudio(num) {
  const src = mainSrcFor(num);
  if (!src) return;
  if (playingNum === num && !player.paused) {
    stopAudio();
    return;
  }
  if (playingNum !== num) {
    stopAudio();
    player.src = src;
    playingNum = num;
  }
  player.play().then(() => paintPlayBtn(num, true)).catch(() => paintPlayBtn(num, false));
}

function paintPlayBtn(num, playing) {
  const btn = listEl.querySelector(`.play-btn[data-num="${num}"]`);
  if (!btn) return;
  btn.classList.toggle("on", playing);
  btn.textContent = playing ? "⏸" : "▶";
  btn.setAttribute("aria-label", (playing ? "Pause" : "Play") + ` audio for song ${num}`);
}

player.addEventListener("ended", () => { const n = playingNum; playingNum = null; if (n != null) paintPlayBtn(n, false); });

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
    <li class="song-row">
      <a class="song" href="song.html?n=${s.num}">
        <span class="num">${s.num}</span>
        <span class="title">${escapeHtml(s.t)}</span>
        <span class="chev">›</span>
      </a>
      <button class="fav-btn${fav ? " on" : ""}" type="button"
              data-num="${s.num}"
              aria-pressed="${fav ? "true" : "false"}"
              aria-label="Toggle favourite for song ${s.num}">${fav ? "★" : "☆"}</button>
      ${playBtn}
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
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => (
    { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]
  ));
}

function filter(q) {
  q = q.trim().toLowerCase();
  if (!q) return SONGS;
  const isNum = /^\d+$/.test(q);
  const qn = normalizeRoman(q); // normalized English query
  return SONGS.filter((s) => {
    if (isNum) return String(s.num).startsWith(q) || String(s.num) === q;
    // match Tamil text directly OR its normalized romanized form
    return s.t.toLowerCase().includes(q) || s._roman.includes(qn);
  });
}

function init(data) {
  SONGS = data.map((s) => ({ ...s, _roman: translit(s.t) }));
  render(SONGS);
  renderShelves();
  // Load the audio manifest, then re-render so rows with audio get a play button.
  if (window.TPAudio) {
    window.TPAudio.load().then((m) => { AUDIO = m || {}; render(filter(searchEl.value)); });
  }
  searchEl.addEventListener("input", () => render(filter(searchEl.value)));

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

fetch("songs.json")
  .then((r) => { if (!r.ok) throw new Error("load failed"); return r.json(); })
  .then(init)
  .catch(() => {
    listEl.innerHTML = `<li class="empty">பாடல்களை ஏற்ற முடியவில்லை.<br>Could not load songs.json.</li>`;
  });

// expose helper for song page (shared file)
window.kaumaramUrl = kaumaramUrl;
