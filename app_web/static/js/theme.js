/**
 * DataLab Web — theme toggle (dark / light).
 *
 * Contract:
 * - Adds the CSS class ``theme-dark`` or ``theme-light`` to
 *   ``#body-root``. The CSS in style.css defines ``--bg``, ``--text``,
 *   etc. for each class; every component reads through the variables
 *   rather than hard-coding colours.
 * - Initial choice: value in ``localStorage['datalab-theme']`` if set,
 *   else the OS-level ``prefers-color-scheme`` media query, else dark.
 * - Clicking ``#theme-toggle`` swaps the class, writes back to
 *   localStorage, and updates the button's icon (🌙 for dark, ☀️ for
 *   light).
 *
 * No-op if ``#body-root`` or ``#theme-toggle`` are absent — safe to
 * load on pages that don't include the toggle.
 *
 * Exposed as ``window.DATALAB_THEME = { apply, toggle, current }``
 * for the (future) web regression tests that exercise the contract
 * from a real Chromium via Playwright.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "datalab-theme";
  var VALID_THEMES = { dark: true, light: true };

  function bodyEl() {
    return document.getElementById("body-root");
  }

  function currentTheme() {
    var b = bodyEl();
    if (!b) return "dark";
    if (b.classList.contains("theme-light")) return "light";
    return "dark";
  }

  function readStoredTheme() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (raw && VALID_THEMES[raw]) return raw;
    } catch (err) {
      /* localStorage may be disabled (Safari private mode) */
    }
    return null;
  }

  function systemPrefers() {
    try {
      if (window.matchMedia &&
          window.matchMedia("(prefers-color-scheme: dark)").matches) {
        return "dark";
      }
      if (window.matchMedia &&
          window.matchMedia("(prefers-color-scheme: light)").matches) {
        return "light";
      }
    } catch (err) {
      /* Old browsers — fall through to default */
    }
    return null;
  }

  function apply(theme) {
    if (!VALID_THEMES[theme]) theme = "dark";
    var b = bodyEl();
    if (!b) return;
    b.classList.toggle("theme-dark", theme === "dark");
    b.classList.toggle("theme-light", theme === "light");
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.textContent = theme === "dark" ? "🌙" : "☀️";
  }

  function toggle() {
    var next = currentTheme() === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (err) {
      /* persistence is a nice-to-have */
    }
    apply(next);
    return next;
  }

  function init() {
    var initial = readStoredTheme() || systemPrefers() || "dark";
    apply(initial);
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.addEventListener("click", toggle);
  }

  // Auto-init on DOM ready so templates don't need to call it.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.DATALAB_THEME = {
    apply: apply,
    toggle: toggle,
    current: currentTheme,
    STORAGE_KEY: STORAGE_KEY,
  };
})();
