/**
 * DataLabSpreadsheet — lightweight editable table component.
 *
 * Shows a compact data preview; click to open full spreadsheet in a modal.
 * Supports CSV/TSV paste, add column/row, text view toggle.
 */

;(function () {
  'use strict';

  /* ------------------------------------------------------------------ */
  /*  Constructor                                                        */
  /* ------------------------------------------------------------------ */

  function DataLabSpreadsheet(container, opts) {
    opts = opts || {};
    this.container = typeof container === 'string'
      ? document.querySelector(container) : container;
    if (!this.container) return;

    this.minRows = opts.minRows || 6;
    this.minCols = opts.minCols || 3;
    this.textareaName = opts.textareaName || 'data_text';
    this.initialData = opts.initialData || '';
    this.onSync = opts.onSync || null;
    this.fixedHeaders = opts.fixedHeaders || null;

    this._rows = [];
    this._headers = [];

    this._build();
    if (this.fixedHeaders) {
      this._headers = this.fixedHeaders.slice();
      this.minCols = this.fixedHeaders.length;
    }
    if (this.initialData) {
      this.loadFromText(this.initialData);
    } else {
      this._ensureMinSize();
      this._render();
    }
  }

  /* ------------------------------------------------------------------ */
  /*  DOM scaffolding — compact preview + modal                          */
  /* ------------------------------------------------------------------ */

  DataLabSpreadsheet.prototype._build = function () {
    var self = this;
    this.container.innerHTML = '';
    this.container.classList.add('spreadsheet-root');

    // --- Compact preview bar (always visible) ---
    var preview = _el('div', 'spreadsheet-preview');
    preview.setAttribute('tabindex', '0');
    preview.setAttribute('role', 'button');

    this._previewSummary = _el('span', 'spreadsheet-preview-summary');
    this._previewSummary.textContent = '点击编辑数据…';

    var editHint = _el('span', 'spreadsheet-preview-hint');
    editHint.setAttribute('data-i18n', 'spreadsheet.clickToEdit');
    editHint.textContent = '✎ 编辑';

    // Mini table preview (shows first 2 rows)
    this._miniTable = _el('table', 'spreadsheet-mini-table');

    preview.appendChild(this._previewSummary);
    preview.appendChild(this._miniTable);
    preview.appendChild(editHint);
    preview.addEventListener('click', function () { self._openModal(); });
    preview.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); self._openModal(); } });
    this.container.appendChild(preview);
    this._previewEl = preview;

    // --- Hidden textarea for form POST ---
    this._hiddenEl = document.createElement('textarea');
    this._hiddenEl.name = this.textareaName;
    this._hiddenEl.style.display = 'none';
    this.container.appendChild(this._hiddenEl);

    // --- Modal overlay (built once, shown/hidden) ---
    this._modalEl = null;  // lazy-built on first open
    this._isTextView = false;
  };

  DataLabSpreadsheet.prototype._buildModal = function () {
    var self = this;
    var overlay = _el('div', 'spreadsheet-modal-overlay');
    overlay.addEventListener('click', function (e) { if (e.target === overlay) self._closeModal(); });

    var modal = _el('div', 'spreadsheet-modal');

    // Modal header
    var header = _el('div', 'spreadsheet-modal-header');
    var title = _el('span', 'spreadsheet-modal-title');
    title.setAttribute('data-i18n', 'spreadsheet.editData');
    title.textContent = '编辑数据';
    var closeBtn = _el('button', 'spreadsheet-modal-close');
    closeBtn.type = 'button';
    closeBtn.innerHTML = '&times;';
    closeBtn.addEventListener('click', function () { self._closeModal(); });
    header.appendChild(title);
    header.appendChild(closeBtn);
    modal.appendChild(header);

    // Toolbar
    var toolbar = _el('div', 'spreadsheet-toolbar');
    var addColBtn = _el('button', 'spreadsheet-btn');
    addColBtn.type = 'button';
    addColBtn.setAttribute('data-i18n', 'spreadsheet.addCol');
    addColBtn.textContent = '+ 列';
    addColBtn.addEventListener('click', this.addColumn.bind(this));
    if (this.fixedHeaders) addColBtn.style.display = 'none';

    var addRowBtn = _el('button', 'spreadsheet-btn');
    addRowBtn.type = 'button';
    addRowBtn.setAttribute('data-i18n', 'spreadsheet.addRow');
    addRowBtn.textContent = '+ 行';
    addRowBtn.addEventListener('click', this.addRow.bind(this));

    var clearBtn = _el('button', 'spreadsheet-btn');
    clearBtn.type = 'button';
    clearBtn.setAttribute('data-i18n', 'spreadsheet.clear');
    clearBtn.textContent = '清除';
    clearBtn.addEventListener('click', this.clear.bind(this));

    var toggleBtn = _el('button', 'spreadsheet-btn spreadsheet-toggle');
    toggleBtn.type = 'button';
    toggleBtn.setAttribute('data-i18n', 'spreadsheet.textView');
    toggleBtn.textContent = '文本视图';
    toggleBtn.addEventListener('click', this._toggleView.bind(this));
    this._toggleBtn = toggleBtn;

    toolbar.appendChild(addColBtn);
    toolbar.appendChild(addRowBtn);
    toolbar.appendChild(clearBtn);
    toolbar.appendChild(toggleBtn);
    modal.appendChild(toolbar);

    // Table wrapper
    var wrap = _el('div', 'spreadsheet-wrap');
    this._tableEl = _el('table', 'spreadsheet-table');
    this._tableEl.addEventListener('paste', this._onPaste.bind(this));
    wrap.appendChild(this._tableEl);
    modal.appendChild(wrap);
    this._wrapEl = wrap;

    // Text view
    this._textViewEl = _el('textarea', 'spreadsheet-text-view');
    this._textViewEl.style.display = 'none';
    this._textViewEl.rows = 12;
    this._textViewEl.spellcheck = false;
    this._textViewEl.addEventListener('input', this._onTextViewInput.bind(this));
    modal.appendChild(this._textViewEl);

    // Done button
    var footer = _el('div', 'spreadsheet-modal-footer');
    var doneBtn = _el('button', 'spreadsheet-btn spreadsheet-done-btn');
    doneBtn.type = 'button';
    doneBtn.setAttribute('data-i18n', 'spreadsheet.done');
    doneBtn.textContent = '完成';
    doneBtn.addEventListener('click', function () { self._closeModal(); });
    footer.appendChild(doneBtn);
    modal.appendChild(footer);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    this._modalEl = overlay;
    this._modalContent = modal;

    // Apply i18n
    if (window.i18nModule && window.i18nModule.applyI18n) {
      window.i18nModule.applyI18n(overlay);
    }
  };

  DataLabSpreadsheet.prototype._openModal = function () {
    if (!this._modalEl) {
      this._buildModal();
      this._render();
    }
    this._modalEl.classList.add('open');
    document.body.style.overflow = 'hidden';
    // Ensure table view is shown
    if (this._isTextView) {
      this._toggleView();
    }
    // Focus first data cell
    var firstTd = this._tableEl.querySelector('tbody td[contenteditable]');
    if (firstTd) setTimeout(function () { firstTd.focus(); }, 100);
  };

  DataLabSpreadsheet.prototype._closeModal = function () {
    if (this._isTextView) {
      // Commit text view changes
      this.loadFromText(this._textViewEl.value);
    }
    this._modalEl.classList.remove('open');
    document.body.style.overflow = '';
    this._updatePreview();
  };

  /* ------------------------------------------------------------------ */
  /*  Preview update                                                     */
  /* ------------------------------------------------------------------ */

  DataLabSpreadsheet.prototype._updatePreview = function () {
    // Summary text
    var dataRows = 0;
    for (var r = 0; r < this._rows.length; r++) {
      if (this._rows[r].some(function (v) { return v.trim() !== ''; })) dataRows++;
    }
    var cols = this._headers.length;
    this._previewSummary.textContent = dataRows + ' × ' + cols;

    // Mini table: show headers + first 2 data rows
    var mt = this._miniTable;
    mt.innerHTML = '';
    var thead = _el('thead');
    var htr = _el('tr');
    for (var c = 0; c < Math.min(cols, 6); c++) {
      var th = _el('th');
      th.textContent = this._headers[c] || '';
      htr.appendChild(th);
    }
    if (cols > 6) {
      var thMore = _el('th');
      thMore.textContent = '…';
      htr.appendChild(thMore);
    }
    thead.appendChild(htr);
    mt.appendChild(thead);

    var tbody = _el('tbody');
    var showRows = Math.min(dataRows, 2);
    var shown = 0;
    for (var r2 = 0; r2 < this._rows.length && shown < showRows; r2++) {
      if (!this._rows[r2].some(function (v) { return v.trim() !== ''; })) continue;
      var tr = _el('tr');
      for (var c2 = 0; c2 < Math.min(cols, 6); c2++) {
        var td = _el('td');
        var val = (this._rows[r2][c2] || '').trim();
        td.textContent = val.length > 12 ? val.substring(0, 10) + '…' : val;
        tr.appendChild(td);
      }
      if (cols > 6) {
        var tdMore = _el('td');
        tdMore.textContent = '…';
        tr.appendChild(tdMore);
      }
      tbody.appendChild(tr);
      shown++;
    }
    if (dataRows > 2) {
      var moreRow = _el('tr');
      var moreCell = _el('td');
      moreCell.colSpan = Math.min(cols, 6) + (cols > 6 ? 1 : 0);
      moreCell.className = 'spreadsheet-more-hint';
      moreCell.textContent = '… ' + (dataRows - 2) + ' more rows';
      moreRow.appendChild(moreCell);
      tbody.appendChild(moreRow);
    }
    mt.appendChild(tbody);
  };

  /* ------------------------------------------------------------------ */
  /*  Data loading                                                       */
  /* ------------------------------------------------------------------ */

  DataLabSpreadsheet.prototype.loadFromText = function (text) {
    text = (text || '').trim();
    if (!text) {
      this._headers = [];
      this._rows = [];
      if (this.fixedHeaders) this._headers = this.fixedHeaders.slice();
      this._ensureMinSize();
      this._render();
      return;
    }

    var lines = text.split(/\r?\n/).filter(function (l) { return l.trim() !== ''; });
    if (!lines.length) { this._ensureMinSize(); this._render(); return; }
    var delim = _detectDelimiter(lines[0]);

    if (this.fixedHeaders) {
      this._headers = this.fixedHeaders.slice();
      // All lines are data rows (no header line to skip)
      this._rows = [];
      for (var i = 0; i < lines.length; i++) {
        this._rows.push(_splitLine(lines[i], delim));
      }
    } else {
      this._headers = _splitLine(lines[0], delim);
      this._rows = [];
      for (var j = 1; j < lines.length; j++) {
        this._rows.push(_splitLine(lines[j], delim));
      }
    }
    this._ensureMinSize();
    this._render();
  };

  /* ------------------------------------------------------------------ */
  /*  Rendering                                                          */
  /* ------------------------------------------------------------------ */

  DataLabSpreadsheet.prototype._render = function () {
    // Update preview always
    this._updatePreview();
    this._sync();

    // If modal not built yet, skip table render
    if (!this._tableEl) return;

    var table = this._tableEl;
    table.innerHTML = '';
    var cols = this._headers.length;

    // Header row
    var thead = _el('thead');
    var htr = _el('tr');
    var th0 = _el('th', 'row-num');
    th0.textContent = '#';
    htr.appendChild(th0);
    for (var c = 0; c < cols; c++) {
      var th = _el('th');
      var isFixed = this.fixedHeaders && c < this.fixedHeaders.length;
      th.contentEditable = isFixed ? 'false' : 'true';
      th.textContent = this._headers[c] || '';
      th.dataset.col = c;
      if (!isFixed) {
        th.addEventListener('input', this._onHeaderInput.bind(this, c));
        th.addEventListener('keydown', this._onCellKey.bind(this));
      }
      htr.appendChild(th);
    }
    thead.appendChild(htr);
    table.appendChild(thead);

    // Data rows
    var tbody = _el('tbody');
    for (var r = 0; r < this._rows.length; r++) {
      var tr = _el('tr');
      var rn = _el('td', 'row-num');
      rn.textContent = r + 1;
      tr.appendChild(rn);
      for (var c2 = 0; c2 < cols; c2++) {
        var td = _el('td');
        td.contentEditable = 'true';
        td.textContent = (this._rows[r] && this._rows[r][c2]) || '';
        td.dataset.row = r;
        td.dataset.col = c2;
        td.addEventListener('input', this._onCellInput.bind(this, r, c2));
        td.addEventListener('keydown', this._onCellKey.bind(this));
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
  };

  /* ------------------------------------------------------------------ */
  /*  Serialisation                                                      */
  /* ------------------------------------------------------------------ */

  DataLabSpreadsheet.prototype.serialize = function () {
    var lines = [];
    lines.push(this._headers.join('\t'));
    for (var r = 0; r < this._rows.length; r++) {
      var row = this._rows[r];
      var hasContent = row.some(function (v) { return v.trim() !== ''; });
      if (hasContent) {
        lines.push(row.join('\t'));
      }
    }
    return lines.join('\n');
  };

  DataLabSpreadsheet.prototype._sync = function () {
    var text = this.serialize();
    this._hiddenEl.value = text;
    if (this._textViewEl) this._textViewEl.value = text;
    if (this.onSync) this.onSync(text);
  };

  /* ------------------------------------------------------------------ */
  /*  Add / remove                                                       */
  /* ------------------------------------------------------------------ */

  DataLabSpreadsheet.prototype.addColumn = function () {
    var idx = this._headers.length;
    var letter = String.fromCharCode(65 + idx % 26);
    if (idx >= 26) letter = String.fromCharCode(64 + Math.floor(idx / 26)) + letter;
    this._headers.push(letter);
    for (var r = 0; r < this._rows.length; r++) {
      this._rows[r].push('');
    }
    this._render();
  };

  DataLabSpreadsheet.prototype.addRow = function () {
    var row = [];
    for (var c = 0; c < this._headers.length; c++) row.push('');
    this._rows.push(row);
    this._render();
  };

  DataLabSpreadsheet.prototype.clear = function () {
    this._headers = [];
    this._rows = [];
    if (this.fixedHeaders) this._headers = this.fixedHeaders.slice();
    this._ensureMinSize();
    this._render();
  };

  /* ------------------------------------------------------------------ */
  /*  Paste handler                                                      */
  /* ------------------------------------------------------------------ */

  DataLabSpreadsheet.prototype._onPaste = function (e) {
    var text = (e.clipboardData || window.clipboardData).getData('text');
    if (!text) return;

    var lines = text.split(/\r?\n/).filter(function (l) { return l.trim() !== ''; });
    if (lines.length <= 1 && !_looksTabular(text)) return;

    e.preventDefault();

    if (lines.length >= 2) {
      this.loadFromText(text);
      return;
    }

    var ds = (e.target || {}).dataset || {};
    var isHeader = !('row' in ds);
    var startCol = parseInt(ds.col, 10) || 0;
    var delim = _detectDelimiter(lines[0]);
    var vals = _splitLine(lines[0], delim);

    if (isHeader) {
      for (var h = 0; h < vals.length; h++) {
        var hc = startCol + h;
        while (hc >= this._headers.length) this.addColumn();
        this._headers[hc] = vals[h];
      }
    } else {
      var startRow = parseInt(ds.row, 10) || 0;
      while (startRow >= this._rows.length) {
        var newRow = [];
        for (var k = 0; k < this._headers.length; k++) newRow.push('');
        this._rows.push(newRow);
      }
      for (var c = 0; c < vals.length; c++) {
        var targetC = startCol + c;
        while (targetC >= this._headers.length) this.addColumn();
        this._rows[startRow][targetC] = vals[c];
      }
    }
    this._render();
  };

  /* ------------------------------------------------------------------ */
  /*  Cell & header events                                               */
  /* ------------------------------------------------------------------ */

  DataLabSpreadsheet.prototype._onCellInput = function (r, c, e) {
    this._rows[r][c] = e.target.textContent;
    this._syncDebounced();
  };

  DataLabSpreadsheet.prototype._syncDebounced = function () {
    clearTimeout(this._syncTimer);
    var self = this;
    this._syncTimer = setTimeout(function () { self._sync(); self._updatePreview(); }, 150);
  };

  DataLabSpreadsheet.prototype._onHeaderInput = function (c, e) {
    this._headers[c] = e.target.textContent.trim();
    this._syncDebounced();
  };

  DataLabSpreadsheet.prototype._onCellKey = function (e) {
    var td = e.target;
    var row = parseInt(td.dataset.row, 10);
    var col = parseInt(td.dataset.col, 10);
    var isHeader = isNaN(row);

    if (e.key === 'Tab') {
      e.preventDefault();
      var next = td.nextElementSibling;
      if (!next && !isHeader) {
        var tr = td.parentElement.nextElementSibling;
        if (tr) next = tr.children[1];
      }
      if (next && next.contentEditable === 'true') next.focus();
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (isHeader) {
        var tbody = this._tableEl.querySelector('tbody');
        if (tbody && tbody.rows[0]) {
          var cell = tbody.rows[0].children[col + 1];
          if (cell) cell.focus();
        }
      } else {
        var nextTr = td.parentElement.nextElementSibling;
        if (nextTr) {
          var nextCell = nextTr.children[col + 1];
          if (nextCell) nextCell.focus();
        }
      }
    } else if (e.key === 'Escape') {
      this._closeModal();
    }
  };

  /* ------------------------------------------------------------------ */
  /*  Text <-> Table toggle                                              */
  /* ------------------------------------------------------------------ */

  DataLabSpreadsheet.prototype._toggleView = function () {
    this._isTextView = !this._isTextView;
    if (this._isTextView) {
      this._wrapEl.style.display = 'none';
      this._textViewEl.style.display = '';
      this._textViewEl.value = this.serialize();
      this._toggleBtn.setAttribute('data-i18n', 'spreadsheet.tableView');
      this._toggleBtn.textContent = '表格视图';
    } else {
      this.loadFromText(this._textViewEl.value);
      this._wrapEl.style.display = '';
      this._textViewEl.style.display = 'none';
      this._toggleBtn.setAttribute('data-i18n', 'spreadsheet.textView');
      this._toggleBtn.textContent = '文本视图';
    }
    if (window.i18nModule && window.i18nModule.applyI18n) {
      window.i18nModule.applyI18n(this._toggleBtn);
    }
  };

  DataLabSpreadsheet.prototype._onTextViewInput = function () {
    this._hiddenEl.value = this._textViewEl.value;
  };

  /* ------------------------------------------------------------------ */
  /*  Helpers                                                            */
  /* ------------------------------------------------------------------ */

  DataLabSpreadsheet.prototype._ensureMinSize = function () {
    while (this._headers.length < this.minCols) {
      var idx = this._headers.length;
      this._headers.push(String.fromCharCode(65 + idx));
    }
    while (this._rows.length < this.minRows) {
      var row = [];
      for (var c = 0; c < this._headers.length; c++) row.push('');
      this._rows.push(row);
    }
    for (var r = 0; r < this._rows.length; r++) {
      while (this._rows[r].length < this._headers.length) {
        this._rows[r].push('');
      }
    }
  };

  function _el(tag, cls) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    return el;
  }

  function _detectDelimiter(line) {
    if (line.indexOf('\t') !== -1) return 'tab';
    if (line.indexOf(',') !== -1) return 'comma';
    return 'space';
  }

  function _splitLine(line, delim) {
    if (delim === 'tab') return line.split('\t');
    if (delim === 'comma') {
      return line.split(',').map(function (s) { return s.trim(); });
    }
    return line.trim().split(/\s+/);
  }

  function _looksTabular(text) {
    if (text.indexOf('\t') !== -1 || text.indexOf(',') !== -1) return true;
    return /  +\S/.test(text.trim());
  }

  /* ------------------------------------------------------------------ */
  /*  Export                                                              */
  /* ------------------------------------------------------------------ */

  window.DataLabSpreadsheet = DataLabSpreadsheet;
})();
