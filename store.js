/* ===== Thiruppugazh 503 — on-device store (no login, localStorage only) =====
 * Keeps favourites and recently-viewed songs privately on the user's device.
 * All values are plain song numbers (1..503). Fails safe if storage is blocked
 * (e.g. private mode) by returning empty lists and no-op writes.
 */
(function (global) {
  "use strict";

  var FAV_KEY = "tp503.favourites.v1";
  var RECENT_KEY = "tp503.recent.v1";
  var RECENT_MAX = 12;
  var MIN = 1;
  var MAX = 503;

  function safeGet(key) {
    try {
      var raw = global.localStorage.getItem(key);
      if (!raw) return [];
      var arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return [];
      // keep only valid, unique song numbers, preserving order
      var seen = {};
      var out = [];
      for (var i = 0; i < arr.length; i++) {
        var n = Number(arr[i]);
        if (Number.isInteger(n) && n >= MIN && n <= MAX && !seen[n]) {
          seen[n] = true;
          out.push(n);
        }
      }
      return out;
    } catch (e) {
      return [];
    }
  }

  function safeSet(key, arr) {
    try {
      global.localStorage.setItem(key, JSON.stringify(arr));
      return true;
    } catch (e) {
      return false;
    }
  }

  var Store = {
    getFavourites: function () {
      return safeGet(FAV_KEY);
    },
    isFavourite: function (num) {
      return this.getFavourites().indexOf(Number(num)) !== -1;
    },
    toggleFavourite: function (num) {
      num = Number(num);
      var favs = this.getFavourites();
      var idx = favs.indexOf(num);
      if (idx === -1) {
        favs.unshift(num); // newest first
      } else {
        favs.splice(idx, 1);
      }
      safeSet(FAV_KEY, favs);
      return idx === -1; // true if it is now a favourite
    },
    getRecent: function () {
      return safeGet(RECENT_KEY);
    },
    addRecent: function (num) {
      num = Number(num);
      if (!(Number.isInteger(num) && num >= MIN && num <= MAX)) return;
      var recent = this.getRecent();
      var idx = recent.indexOf(num);
      if (idx !== -1) recent.splice(idx, 1);
      recent.unshift(num); // most recent first
      if (recent.length > RECENT_MAX) recent = recent.slice(0, RECENT_MAX);
      safeSet(RECENT_KEY, recent);
    }
  };

  global.TPStore = Store;
})(window);
