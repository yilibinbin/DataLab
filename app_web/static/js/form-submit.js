/*
 * Double-submit guard for the compute forms (P1-10).
 *
 * The extrapolation / statistics / fitting forms POST and can take seconds to
 * compute server-side. With no feedback the user may click the submit button
 * repeatedly, firing duplicate jobs and leaving them unsure anything happened.
 *
 * On submit: disable the primary submit button, mark it aria-busy, and swap its
 * label to a localized "processing" string. The browser still submits the form
 * normally (we do not preventDefault), so this is purely a UX/idempotency guard.
 * On pageshow (including bfcache back-navigation) the button is restored so a
 * user returning to a cached form is not left with a permanently disabled button.
 */
(function () {
  "use strict";

  function processingLabel() {
    var lang = "zh";
    try {
      if (window.i18nModule && typeof window.i18nModule.getLang === "function") {
        lang = window.i18nModule.getLang();
      } else if (document.documentElement.lang) {
        lang = document.documentElement.lang.indexOf("en") === 0 ? "en" : "zh";
      }
    } catch (e) {
      lang = "zh";
    }
    return lang === "en" ? "Processing…" : "处理中…";
  }

  function restore(button) {
    if (!button) return;
    button.disabled = false;
    button.removeAttribute("aria-busy");
    if (button.dataset.originalLabel !== undefined) {
      button.textContent = button.dataset.originalLabel;
      delete button.dataset.originalLabel;
    }
  }

  function wire(form) {
    form.addEventListener("submit", function () {
      var button = form.querySelector('button[type="submit"], input[type="submit"]');
      if (!button || button.disabled) return;
      button.dataset.originalLabel = button.textContent;
      button.setAttribute("aria-busy", "true");
      button.textContent = processingLabel();
      // Disable after the current event loop turn so the button's value is still
      // included in the submitted form data (a disabled control is not sent).
      window.setTimeout(function () {
        button.disabled = true;
      }, 0);
    });
  }

  function init() {
    var forms = document.querySelectorAll('form[method="post"]');
    for (var i = 0; i < forms.length; i++) {
      wire(forms[i]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Restore submit buttons when the page is shown from the bfcache after a
  // back-navigation, so a returning user gets a usable form again.
  window.addEventListener("pageshow", function () {
    var buttons = document.querySelectorAll(
      'form[method="post"] button[type="submit"], form[method="post"] input[type="submit"]'
    );
    for (var i = 0; i < buttons.length; i++) {
      restore(buttons[i]);
    }
  });
})();
