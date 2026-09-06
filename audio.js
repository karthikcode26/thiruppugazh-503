/* ===== Thiruppugazh 503 — audio manifest helpers =====
 * Loads audio.json once and exposes per-song audio for the main singer plus any
 * number of extra recordings (other singers' audio or other authors' videos).
 *
 * audio.json shape (all parts optional; a missing song = no audio):
 * {
 *   "1": {
 *     "main":  { "label": "Main singer", "type": "audio", "src": "audio/main/1.mp3" },
 *     "extra": [
 *       { "label": "Guru Ramesh",  "type": "audio", "src": "audio/ramesh/1.mp3" },
 *       { "label": "Class video",  "type": "video", "youtubeId": "XXXXXXXXXXX" }
 *     ]
 *   }
 * }
 */
(function (global) {
  "use strict";

  var VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;
  var cache = null;
  var pending = null;

  function isValidAudio(item) {
    return item && item.type === "audio" && typeof item.src === "string" && item.src.length > 0;
  }
  function isValidVideo(item) {
    return item && item.type === "video" && VIDEO_ID_RE.test(item.youtubeId || "");
  }
  function isValidEntry(item) {
    return isValidAudio(item) || isValidVideo(item);
  }

  // Load audio.json once; resolves to {} on any error so pages still work.
  function load() {
    if (cache) return Promise.resolve(cache);
    if (pending) return pending;
    pending = fetch("audio.json")
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (data) {
        cache = data && typeof data === "object" ? data : {};
        return cache;
      })
      .catch(function () { cache = {}; return cache; });
    return pending;
  }

  // Return { main: entry|null, extra: [validEntry...] } for a song number.
  function forSong(data, num) {
    var entry = data && data[String(num)];
    var main = entry && isValidAudio(entry.main) ? entry.main : null;
    var extra = [];
    if (entry && Array.isArray(entry.extra)) {
      for (var i = 0; i < entry.extra.length; i++) {
        if (isValidEntry(entry.extra[i])) extra.push(entry.extra[i]);
      }
    }
    return { main: main, extra: extra };
  }

  global.TPAudio = { load: load, forSong: forSong, isValidVideo: isValidVideo, isValidAudio: isValidAudio };
})(window);
