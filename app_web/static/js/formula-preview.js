/**
 * Real-time formula preview using shared server-side formula metadata.
 *
 * The web layer intentionally does not own formula parsing/conversion rules.
 * It fetches sanitized LaTeX from /api/formula-preview and keeps KaTeX as a
 * thin display adapter.
 */
(function () {
  'use strict';

  var ENDPOINT = '/api/formula-preview';
  var INPUT_IDS = ['custom_formula', 'fit_custom_expr', 'error_formula'];

  function previewLanguage(input) {
    return input.getAttribute('data-formula-language') ||
      input.getAttribute('data-preview-language') ||
      'datalab';
  }

  function previewLhs(input) {
    return input.getAttribute('data-formula-lhs') || '';
  }

  function renderPlaceholder(preview) {
    preview.innerHTML = '<span class="formula-preview-placeholder"></span>';
    preview.firstChild.textContent = '公式预览';
  }

  function renderError(preview, payload) {
    var message = (payload && payload.error_message) ||
      (payload && payload.fallback_text) ||
      '';
    preview.innerHTML = '<span class="katex-error"></span>';
    preview.firstChild.textContent = message;
  }

  function renderLatex(preview, latex) {
    if (typeof katex === 'undefined') {
      preview.textContent = latex;
      return;
    }
    try {
      katex.render(latex, preview, { throwOnError: false, displayMode: true });
    } catch (e) {
      preview.innerHTML = '<span class="katex-error"></span>';
      preview.firstChild.textContent = e.message;
    }
  }

  function fetchFormulaMetadata(input) {
    var params = new URLSearchParams();
    params.set('source', input.value || (input.textContent || ''));
    params.set('language', previewLanguage(input));
    var lhs = previewLhs(input);
    if (lhs) params.set('lhs', lhs);
    return fetch(ENDPOINT + '?' + params.toString(), {
      method: 'GET',
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' },
    }).then(function (response) {
      return response.json();
    });
  }

  function setupPreview(inputId) {
    var input = document.getElementById(inputId);
    if (!input) return;

    var preview = document.createElement('div');
    preview.className = 'formula-preview';
    input.parentElement.insertBefore(preview, input.nextSibling);

    var timer = null;
    var requestId = 0;

    function update() {
      var raw = input.value || (input.textContent || '');
      if (!raw.trim()) {
        requestId += 1;
        renderPlaceholder(preview);
        return;
      }

      var currentRequest = requestId + 1;
      requestId = currentRequest;
      fetchFormulaMetadata(input)
        .then(function (payload) {
          if (currentRequest !== requestId) return;
          if (!payload || !payload.ok || !payload.latex) {
            renderError(preview, payload);
            return;
          }
          renderLatex(preview, payload.latex);
        })
        .catch(function (error) {
          if (currentRequest !== requestId) return;
          renderError(preview, { error_message: error.message || String(error) });
        });
    }

    input.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(update, 300);
    });

    setTimeout(update, 500);
  }

  document.addEventListener('DOMContentLoaded', function () {
    INPUT_IDS.forEach(setupPreview);
  });
})();
