/**
 * Real-time formula preview using KaTeX.
 * Converts Mathematica-style notation to LaTeX and renders below the input.
 */
(function () {
  'use strict';

  // Mathematica → LaTeX conversion rules
  var CONVERSIONS = [
    [/\bSin\[([^\]]+)\]/gi,   '\\sin\\left($1\\right)'],
    [/\bCos\[([^\]]+)\]/gi,   '\\cos\\left($1\\right)'],
    [/\bTan\[([^\]]+)\]/gi,   '\\tan\\left($1\\right)'],
    [/\bLog\[([^\]]+)\]/gi,   '\\ln\\left($1\\right)'],
    [/\bLog10\[([^\]]+)\]/gi, '\\log_{10}\\left($1\\right)'],
    [/\bExp\[([^\]]+)\]/gi,   'e^{$1}'],
    [/\bSqrt\[([^\]]+)\]/gi,  '\\sqrt{$1}'],
    [/\bAbs\[([^\]]+)\]/gi,   '\\left|$1\\right|'],
    [/\bPi\b/gi,              '\\pi'],
    [/\*\*/g,                 '^'],             // Python-style power
    [/\*/g,                   '\\cdot '],        // multiplication
    [/(\w)\^(-?\w)/g,         '$1^{$2}'],        // simple power
    [/(\w)\^\(([^)]+)\)/g,    '$1^{$2}'],        // power with parens
    [/(\w)\^\{([^}]+)\}/g,    '$1^{$2}'],        // already braced
  ];

  function toLatex(expr) {
    if (!expr || !expr.trim()) return '';
    var tex = expr.trim();
    for (var i = 0; i < CONVERSIONS.length; i++) {
      tex = tex.replace(CONVERSIONS[i][0], CONVERSIONS[i][1]);
    }
    return tex;
  }

  function setupPreview(inputId) {
    var input = document.getElementById(inputId);
    if (!input) return;

    // Create preview container
    var preview = document.createElement('div');
    preview.className = 'formula-preview';
    input.parentElement.insertBefore(preview, input.nextSibling);

    var timer = null;
    function update() {
      var raw = input.value || (input.textContent || '');
      var tex = toLatex(raw);
      if (!tex) {
        preview.innerHTML = '<span style="color:var(--muted);font-size:13px">公式预览</span>';
        return;
      }
      if (typeof katex === 'undefined') {
        preview.textContent = tex;
        return;
      }
      try {
        katex.render(tex, preview, { throwOnError: false, displayMode: true });
      } catch (e) {
        preview.innerHTML = '<span class="katex-error">' + e.message + '</span>';
      }
    }

    input.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(update, 300);
    });

    // Initial render
    setTimeout(update, 500);
  }

  document.addEventListener('DOMContentLoaded', function () {
    // Attach to all known formula inputs
    ['custom_formula', 'fit_custom_expr', 'error_formula'].forEach(setupPreview);
  });
})();
