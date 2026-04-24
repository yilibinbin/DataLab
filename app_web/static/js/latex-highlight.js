/**
 * Lightweight LaTeX syntax highlighter for DataLab.
 * Highlights: commands, braces, comments, math mode, environments.
 * Usage: highlightLatex(codeElement)
 */
(function () {
  'use strict';

  // Token types and their CSS class names
  var TOKEN_PATTERNS = [
    { re: /(%.*)$/gm,                          cls: 'tex-comment' },   // line comments
    { re: /(\\begin\{[^}]*\}|\\end\{[^}]*\})/g, cls: 'tex-env' },    // environments
    { re: /(\\[a-zA-Z@]+\*?)/g,                cls: 'tex-cmd' },      // commands
    { re: /([{}])/g,                            cls: 'tex-brace' },    // braces
    { re: /(\[|\])/g,                           cls: 'tex-bracket' },  // brackets
    { re: /(&)/g,                               cls: 'tex-amp' },      // alignment &
    { re: /(\$[^$]*\$)/g,                       cls: 'tex-math' },     // inline math
  ];

  function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /**
   * Apply LaTeX syntax highlighting to a <code> element.
   * Replaces textContent with highlighted innerHTML.
   */
  function highlightLatex(el) {
    if (!el || !el.textContent) return;

    var text = el.textContent;

    // Tokenize: split into segments that should or should not be highlighted
    // We process in priority order, replacing tokens with placeholders
    var placeholders = [];
    var uid = '__TEX_' + Math.random().toString(36).slice(2) + '_';

    function replacer(cls) {
      return function (match) {
        var idx = placeholders.length;
        placeholders.push('<span class="' + cls + '">' + escapeHtml(match) + '</span>');
        return uid + idx + uid;
      };
    }

    // Apply patterns in order; comments first so they take priority
    for (var i = 0; i < TOKEN_PATTERNS.length; i++) {
      var pat = TOKEN_PATTERNS[i];
      var regex = new RegExp(pat.re.source, pat.re.flags);
      text = text.replace(regex, replacer(pat.cls));
    }

    // Escape remaining plain text, then restore placeholders
    var parts = text.split(new RegExp(uid + '(\\d+)' + uid));
    var html = '';
    for (var j = 0; j < parts.length; j++) {
      if (j % 2 === 0) {
        html += escapeHtml(parts[j]);
      } else {
        html += placeholders[parseInt(parts[j], 10)];
      }
    }

    el.innerHTML = html;
  }

  /**
   * Auto-highlight all <code class="lang-latex"> elements on the page.
   */
  function highlightAll() {
    var els = document.querySelectorAll('code.lang-latex');
    for (var i = 0; i < els.length; i++) {
      highlightLatex(els[i]);
    }
  }

  // Expose
  window.latexHighlight = { highlight: highlightLatex, highlightAll: highlightAll };
})();
