/**
 * Dynamic UI Specification System for Web Frontend
 * Fetches UI specs from backend API and dynamically renders parameter panels
 *
 * OPTIMIZED VERSION - Fixes performance issues:
 * - Prevents duplicate event listener bindings
 * - Caches help_specs to avoid repeated fetching
 * - Syncs language state with i18n module
 * - Avoids redundant DOM operations
 *
 * Author: 方昊 (中国科学院精密测量院外场理论组)
 * Date: 2025-12-13 (Performance fixes)
 */

// Global state
let uiSpecs = null;
let uiSpecsCache = null;    // { lang, data } in-memory cache
let helpSpecsCache = null;  // Cache help specs to avoid repeated fetching
let isInitialized = false;  // Prevent duplicate initialization

// Cache versions (bump to invalidate localStorage)
const UI_SPECS_CACHE_VERSION = '2025-12-13.1';
const HELP_SPECS_CACHE_VERSION = '2025-12-15.1';

function _debugPerfEnabled() {
    try {
        return localStorage.getItem('datalab_debug_perf') === '1' || !!window.DATALAB_DEBUG_PERF;
    } catch (e) {
        return !!window.DATALAB_DEBUG_PERF;
    }
}

function _perfMark(label) {
    if (!_debugPerfEnabled() || !window.performance) return;
    try {
        performance.mark(label);
        // Keep logs compact and greppable
        console.log(`[DL PERF] ${label} @ ${Math.round(performance.now())}ms`);
    } catch (e) {}
}

function _perfMeasure(name, startMark, endMark) {
    if (!_debugPerfEnabled() || !window.performance) return;
    try {
        performance.measure(name, startMark, endMark);
        const entries = performance.getEntriesByName(name);
        const last = entries[entries.length - 1];
        if (last) {
            console.log(`[DL PERF] ${name}: ${Math.round(last.duration)}ms`);
        }
    } catch (e) {}
}

function _getLocalStorageJson(key) {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return null;
        return JSON.parse(raw);
    } catch (e) {
        return null;
    }
}

function _setLocalStorageJson(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {}
}

// Get current language from i18n module (sync with main app)
function getCurrentLang() {
    return (window.i18nModule && window.i18nModule.getLang()) || 'zh';
}

function _getServerFormValues() {
    try {
        const values = window.DATALAB_FORM_VALUES;
        if (values && typeof values === 'object') return values;
    } catch (e) {}
    return {};
}

function _getServerFormValue(name) {
    if (!name) return null;
    const values = _getServerFormValues();
    try {
        if (Object.prototype.hasOwnProperty.call(values, name)) return values[name];
    } catch (e) {}
    return null;
}

// Initialize on page load (only once)
document.addEventListener('DOMContentLoaded', async function() {
    if (isInitialized) {
        console.log('[UI Specs] Already initialized, skipping...');
        return;
    }

    try {
        console.log('[UI Specs] Initializing...');

        // Only initialize dynamic extrapolation UI if the method selector exists on this page.
        const methodSelect = document.getElementById('method');
        if (!methodSelect) {
            isInitialized = true;
            console.log('[UI Specs] No method selector found; skipping UI-spec initialization');
            return;
        }

        // Bind lightweight UI interactions immediately (no fetch yet)
        initMethodSelector();
        initParameterPanels();

        // Defer fetching/rendering specs to idle time to avoid blocking tab switches.
        const schedule = window.requestIdleCallback || ((cb) => setTimeout(() => cb({ timeRemaining: () => 0 }), 30));
        schedule(async () => {
            try {
                _perfMark('ui-specs:init:start');
                await loadUISpecs();
                _perfMark('ui-specs:init:loaded');
                _perfMeasure('ui-specs:init', 'ui-specs:init:start', 'ui-specs:init:loaded');

                // Render current method dynamic panel once specs are ready
                onMethodChange();
            } catch (error) {
                console.error('[UI Specs] Deferred initialization failed:', error);
            }
        });

        isInitialized = true;
        console.log('[UI Specs] Initialization complete');
    } catch (error) {
        console.error('[UI Specs] Initialization failed:', error);
        // Fall back to existing hardcoded UI
    }
});

/**
 * Load UI specifications from backend API
 */
async function loadUISpecs() {
    try {
        const lang = getCurrentLang();
        const cacheKey = `datalab_ui_specs:${UI_SPECS_CACHE_VERSION}:${lang}`;

        // In-memory cache
        if (uiSpecsCache && uiSpecsCache.lang === lang && uiSpecsCache.data) {
            uiSpecs = uiSpecsCache.data;
            if (_debugPerfEnabled()) console.log('[UI Specs] Using in-memory UI specs cache for:', lang);
            return uiSpecs;
        }

        // localStorage cache (persists across tab switches/page navigations)
        const cached = _getLocalStorageJson(cacheKey);
        if (cached && cached.data) {
            uiSpecsCache = { lang, data: cached.data };
            uiSpecs = cached.data;
            if (_debugPerfEnabled()) console.log('[UI Specs] Using localStorage UI specs cache for:', lang);
            return uiSpecs;
        }

        _perfMark('ui-specs:fetch:start');
        const response = await fetch(`/api/ui-specs?lang=${lang}`);
        if (!response.ok) {
            throw new Error(`API returned ${response.status}`);
        }
        _perfMark('ui-specs:fetch:response');
        uiSpecs = await response.json();
        _perfMark('ui-specs:fetch:json');
        _perfMeasure('ui-specs:fetch+json', 'ui-specs:fetch:start', 'ui-specs:fetch:json');

        uiSpecsCache = { lang, data: uiSpecs };
        _setLocalStorageJson(cacheKey, { ts: Date.now(), data: uiSpecs });
        console.log('[UI Specs] Loaded for language:', lang);
        return uiSpecs;
    } catch (error) {
        console.error('[UI Specs] Failed to load UI specs:', error);
        throw error;
    }
}

/**
 * Initialize method selector with data from UI specs
 * FIXED: Prevents duplicate event listener binding
 */
function initMethodSelector() {
    const methodSelect = document.getElementById('method');
    if (!methodSelect) return;

    console.log('[UI Specs] Initializing method selector');

    // Add method help button if it doesn't exist (or update tooltip)
    addMethodHelpButton();

    // Bind change listener once (avoid duplicate bindings on dynamic reloads)
    if (methodSelect.dataset.uiSpecsBound === '1') {
        onMethodChange();
        return;
    }
    methodSelect.addEventListener('change', onMethodChange);
    methodSelect.dataset.uiSpecsBound = '1';
    onMethodChange();
}

/**
 * Add "?" help button next to method selector
 */
function addMethodHelpButton() {
    const methodSelect = document.getElementById('method');
    if (!methodSelect) return;

    // Check if button already exists
    let helpBtn = document.getElementById('method-help-btn');
    if (helpBtn) {
        // Update existing button text based on language
        const lang = getCurrentLang();
        helpBtn.title = lang === 'zh'
            ? '点击查看当前外推方法的详细说明'
            : 'Click for detailed method description';
        return;
    }

    // Create help button
    helpBtn = document.createElement('button');
    helpBtn.id = 'method-help-btn';
    helpBtn.type = 'button';
    helpBtn.textContent = '?';
    helpBtn.className = 'help-btn';
    const lang = getCurrentLang();
    helpBtn.title = lang === 'zh'
        ? '点击查看当前外推方法的详细说明'
        : 'Click for detailed method description';
    helpBtn.onclick = showMethodHelp;

    // Insert after method select
    methodSelect.parentNode.insertBefore(helpBtn, methodSelect.nextSibling);
}

/**
 * Handle method selection change
 * OPTIMIZED: Only updates necessary DOM elements
 */
function onMethodChange() {
    const methodSelect = document.getElementById('method');
    if (!methodSelect) return;

    const selectedMethod = methodSelect.value;
    console.log('[UI Specs] Method changed to:', selectedMethod);
    _perfMark(`ui-specs:method:${selectedMethod}:change`);

    // Hide all existing method blocks (legacy)
    document.querySelectorAll('.method-block').forEach(block => {
        block.style.display = 'none';
    });

    // Show legacy blocks that match
    document.querySelectorAll(`[data-methods*="${selectedMethod}"]`).forEach(block => {
        const methods = (block.dataset.methods || '').split(',').map(m => m.trim());
        if (methods.includes(selectedMethod)) {
            block.style.display = 'block';
        }
    });

    // Render dynamic parameter panel (only if container exists)
    renderParameterPanel(selectedMethod);
}

/**
 * Initialize parameter panels container
 */
function initParameterPanels() {
    // Find or create parameter container
    let container = document.getElementById('dynamic-params-container');

    if (!container) {
        // Find the card containing method selector
        const methodSelect = document.getElementById('method');
        const methodCard = methodSelect ? methodSelect.closest('.card') : null;
        if (methodCard) {
            container = document.createElement('div');
            container.id = 'dynamic-params-container';
            container.className = 'dynamic-params';
            // Insert after method select and existing method blocks
            methodCard.appendChild(container);
        }
    }

    return container;
}

/**
 * Render parameter panel for selected method
 * OPTIMIZED: Reuses DOM elements when possible
 */
function renderParameterPanel(methodKey) {
    if (!uiSpecs || !uiSpecs.param_specs) return;

    const container = document.getElementById('dynamic-params-container');
    if (!container) return;

    _perfMark(`ui-specs:params:${methodKey}:start`);

    // Avoid duplicating legacy panels that already exist in templates.
    const skipDynamic = new Set(['power_law', 'custom']);
    if (skipDynamic.has(methodKey)) {
        container.innerHTML = '';
        _perfMark(`ui-specs:params:${methodKey}:end`);
        _perfMeasure(`ui-specs:params:${methodKey}`, `ui-specs:params:${methodKey}:start`, `ui-specs:params:${methodKey}:end`);
        return;
    }

    const params = uiSpecs.param_specs[methodKey];

    // Clear existing content
    container.innerHTML = '';

    if (!params || params.length === 0) {
        console.log('[UI Specs] No parameters for method:', methodKey);
        return;
    }

    console.log('[UI Specs] Rendering parameters for:', methodKey);

    // Create panel
    const panel = document.createElement('div');
    panel.className = 'param-panel';
    panel.id = `panel-${methodKey}`;

    params.forEach(param => {
        const paramDiv = createParameterField(param, methodKey);
        if (paramDiv) {
            panel.appendChild(paramDiv);
        }
    });

    container.appendChild(panel);

    // Apply visibility rules
    applyVisibilityRules(methodKey);

    _perfMark(`ui-specs:params:${methodKey}:end`);
    _perfMeasure(`ui-specs:params:${methodKey}`, `ui-specs:params:${methodKey}:start`, `ui-specs:params:${methodKey}:end`);
}

/**
 * Create parameter field based on spec
 */
function createParameterField(param, methodKey) {
    const fieldDiv = document.createElement('div');
    fieldDiv.className = 'param-field';
    fieldDiv.id = `param-${methodKey}-${param.name}`;

    // Create label
    const label = document.createElement('label');
    label.className = 'field-label';
    label.textContent = param.label;
    label.htmlFor = `input-${methodKey}-${param.name}`;
    if (param.tooltip) {
        label.title = param.tooltip;
    }
    fieldDiv.appendChild(label);

    // Create input based on type
    let input;

    switch (param.type) {
        case 'number':
            input = createNumberInput(param, methodKey);
            break;
        case 'select':
            input = createSelectInput(param, methodKey);
            break;
        case 'textarea':
            input = createTextareaInput(param, methodKey);
            break;
        case 'text':
        default:
            input = createTextInput(param, methodKey);
            break;
    }

    if (input) {
        input.id = `input-${methodKey}-${param.name}`;
        input.name = param.name;
        input.dataset.paramName = param.name;
        input.dataset.methodKey = methodKey;
        fieldDiv.appendChild(input);

        // Add hint if exists
        if (param.placeholder || param.tooltip) {
            const hint = document.createElement('div');
            hint.className = 'hint';
            hint.textContent = param.tooltip || '';
            fieldDiv.appendChild(hint);
        }
    }

    return fieldDiv;
}

/**
 * Create number input
 */
function createNumberInput(param, methodKey) {
    const input = document.createElement('input');
    input.type = 'number';
    const existing = _getServerFormValue(param.name);
    if (existing !== null && existing !== undefined) {
        input.value = String(existing);
    } else {
        input.value = param.default !== null ? String(param.default) : '';
    }

    if (param.min !== null && param.min !== undefined) {
        input.min = param.min;
    }
    if (param.max !== null && param.max !== undefined) {
        input.max = param.max;
    }
    if (param.step) {
        input.step = param.step;
    }
    if (param.tooltip) {
        input.title = param.tooltip;
    }

    return input;
}

/**
 * Create select input
 */
function createSelectInput(param, methodKey) {
    const select = document.createElement('select');

    const existing = _getServerFormValue(param.name);
    const selectedValue = (existing !== null && existing !== undefined)
        ? String(existing)
        : (param.default !== null && param.default !== undefined ? String(param.default) : '');

    if (param.options && Array.isArray(param.options)) {
        param.options.forEach(([label, value]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            if (String(value) === selectedValue) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    }

    if (param.tooltip) {
        select.title = param.tooltip;
    }

    // Listen for changes to apply visibility rules
    // FIXED: Use once: true to prevent duplicate bindings
    select.addEventListener('change', () => {
        applyVisibilityRules(methodKey);
    }, { once: false });  // Allow multiple changes, but prevent duplicate bindings by recreating select

    return select;
}

/**
 * Create textarea input
 */
function createTextareaInput(param, methodKey) {
    const textarea = document.createElement('textarea');
    const existing = _getServerFormValue(param.name);
    if (existing !== null && existing !== undefined) {
        textarea.value = String(existing);
    } else {
        textarea.value = param.default || '';
    }

    if (param.placeholder) {
        textarea.placeholder = param.placeholder;
    }
    if (param.min_height) {
        textarea.style.minHeight = `${param.min_height}px`;
    }
    if (param.tooltip) {
        textarea.title = param.tooltip;
    }

    textarea.rows = 3;
    textarea.spellcheck = false;

    return textarea;
}

/**
 * Create text input
 */
function createTextInput(param, methodKey) {
    const input = document.createElement('input');
    input.type = 'text';
    const existing = _getServerFormValue(param.name);
    if (existing !== null && existing !== undefined) {
        input.value = String(existing);
    } else {
        input.value = param.default || '';
    }

    if (param.placeholder) {
        input.placeholder = param.placeholder;
    }
    if (param.tooltip) {
        input.title = param.tooltip;
    }

    return input;
}

/**
 * Apply visibility rules for dynamic parameters
 */
function applyVisibilityRules(methodKey) {
    if (!uiSpecs || !uiSpecs.visibility_rules) return;

    const rules = uiSpecs.visibility_rules;

    Object.keys(rules).forEach(ruleKey => {
        // Parse rule key: "method.param"
        const [ruleMethod, ruleParam] = ruleKey.split('.');

        // Only apply to current method
        if (ruleMethod !== methodKey) return;

        const rule = rules[ruleKey];
        const dependsKey = String(rule.depends_on || '');
        const dependsParam = dependsKey.includes('.') ? dependsKey.split('.').pop() : dependsKey;
        const dependsInput = document.getElementById(`input-${methodKey}-${dependsParam}`);
        const targetDiv = document.getElementById(`param-${methodKey}-${ruleParam}`);

        if (!dependsInput || !targetDiv) return;

        // Check visibility condition
        const currentValue = dependsInput.value;
        const shouldShow = (currentValue === rule.visible_when);

        targetDiv.style.display = shouldShow ? 'block' : 'none';
    });
}

/**
 * Load and cache help specs
 * CRITICAL FIX: Caches help specs to avoid repeated API calls
 */
async function loadHelpSpecs(lang) {
    const cacheKey = lang || getCurrentLang();
    const storageKey = `datalab_help_specs:${HELP_SPECS_CACHE_VERSION}:${cacheKey}`;

    // Return cached version if available
    if (helpSpecsCache && helpSpecsCache.lang === cacheKey) {
        console.log('[UI Specs] Using cached help specs for:', cacheKey);
        return helpSpecsCache.data;
    }

    // localStorage cache (persists across tab switches/page navigations)
    const cached = _getLocalStorageJson(storageKey);
    if (cached && cached.data) {
        helpSpecsCache = { lang: cacheKey, data: cached.data };
        if (_debugPerfEnabled()) console.log('[UI Specs] Using localStorage help specs cache for:', cacheKey);
        return cached.data;
    }

    try {
        console.log('[UI Specs] Loading help specs for:', cacheKey);
        _perfMark('help-specs:fetch:start');
        const response = await fetch(`/api/help_specs?lang=${cacheKey}`);
        if (!response.ok) {
            throw new Error(`API returned ${response.status}`);
        }

        _perfMark('help-specs:fetch:response');
        const data = await response.json();
        _perfMark('help-specs:fetch:json');
        _perfMeasure('help-specs:fetch+json', 'help-specs:fetch:start', 'help-specs:fetch:json');

        // Cache the result
        helpSpecsCache = {
            lang: cacheKey,
            data: data
        };
        _setLocalStorageJson(storageKey, { ts: Date.now(), data });

        console.log('[UI Specs] Help specs loaded and cached');
        return data;
    } catch (error) {
        console.error('[UI Specs] Failed to load help specs:', error);
        throw error;
    }
}

/**
 * Show function help dialog
 * FIXED: Uses cached help specs
 */
async function showFunctionHelp() {
    const lang = getCurrentLang();

    try {
        _perfMark('help:function:start');
        const data = await loadHelpSpecs(lang);
        _perfMark('help:function:loaded');
        _perfMeasure('help:function', 'help:function:start', 'help:function:loaded');
        const formulaHelp = data.formula_help || {};
        showModal(
            formulaHelp.title || (lang === 'zh' ? '可用函数' : 'Available Functions'),
            formulaHelp.content || ''
        );
    } catch (error) {
        console.error('[UI Specs] Failed to load function help:', error);
        alert((window.i18nModule && window.i18nModule.t) ? window.i18nModule.t('errors.help_load_failed') : 'Failed to load help information');
    }
}

/**
 * Show method help dialog
 * FIXED: Uses cached help specs and ensures correct language
 */
async function showMethodHelp() {
    const methodSelect = document.getElementById('method');
    if (!methodSelect) return;

    const methodKey = methodSelect.value;
    const lang = getCurrentLang();

    try {
        _perfMark('help:method:start');
        const data = await loadHelpSpecs(lang);
        _perfMark('help:method:loaded');
        _perfMeasure('help:method', 'help:method:start', 'help:method:loaded');
        const methodData = data.extrapolation_methods?.[methodKey];

        if (!methodData) {
            alert((window.i18nModule && window.i18nModule.t) ? window.i18nModule.t('errors.help_not_found') : 'Help information not found');
            return;
        }

        const content = methodData.description || '';
        if (!content) {
            alert((window.i18nModule && window.i18nModule.t) ? window.i18nModule.t('errors.help_not_found') : 'Help information not found');
            return;
        }

        // IMPORTANT: keep help body identical to the shared help_specs (desktop/web parity).
        showModal(methodData.name || methodKey, content);
    } catch (error) {
        console.error('[UI Specs] Failed to load method help:', error);
        alert((window.i18nModule && window.i18nModule.t) ? window.i18nModule.t('errors.help_load_failed') : 'Failed to load help information');
    }
}

/**
 * Show modal dialog
 */
function showModal(title, content) {
    // Create modal if it doesn't exist
    let modal = document.getElementById('help-modal');

    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'help-modal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <span class="modal-close">&times;</span>
                <h2 id="modal-title"></h2>
                <div id="modal-body"></div>
            </div>
        `;
        document.body.appendChild(modal);

        // Close button
        modal.querySelector('.modal-close').onclick = () => {
            modal.style.display = 'none';
        };

        // Click outside to close
        modal.onclick = (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        };
    }

    // Set content
    document.getElementById('modal-title').textContent = title;
    const bodyDiv = document.getElementById('modal-body');
    bodyDiv.innerHTML = '';

    // Format content (preserve line breaks and basic markdown)
    const pre = document.createElement('pre');
    pre.style.whiteSpace = 'pre-wrap';
    pre.style.fontFamily = 'monospace';
    pre.style.fontSize = '14px';
    pre.style.lineHeight = '1.6';
    pre.textContent = content;
    bodyDiv.appendChild(pre);

    // Show modal
    modal.style.display = 'block';
}

/**
 * Collect parameters from dynamic form
 * Call this before form submission to ensure dynamic params are included
 */
function collectDynamicParameters() {
    const methodSelect = document.getElementById('method');
    if (!methodSelect) return {};

    const methodKey = methodSelect.value;
    const params = { method: methodKey };

    // Collect all dynamic parameters
    const inputs = document.querySelectorAll(`
        input[data-method-key="${methodKey}"],
        select[data-method-key="${methodKey}"],
        textarea[data-method-key="${methodKey}"]
    `);

    inputs.forEach(input => {
        const paramName = input.dataset.paramName;
        if (paramName) {
            params[paramName] = input.value;
        }
    });

    console.log('[UI Specs] Collected parameters:', params);
    return params;
}

/**
 * Refresh UI when language changes
 * CRITICAL: Called by main app when language is switched
 */
async function onLanguageChange(newLang) {
    console.log('[UI Specs] Language changed to:', newLang);

    // Clear in-memory caches (localStorage caches remain per language)
    helpSpecsCache = null;
    uiSpecsCache = null;
    uiSpecs = null;

    // If this page doesn't use dynamic method specs, skip fetching UI specs.
    // (Function-help modal can still work via loadHelpSpecs.)
    const methodSelect = document.getElementById('method');
    if (!methodSelect) {
        return;
    }

    // Reload UI specs in new language and rerender dynamic panel
    try {
        await loadUISpecs();
        addMethodHelpButton();
        onMethodChange();
    } catch (error) {
        console.error('[UI Specs] Failed to reload on language change:', error);
    }
}

// Export functions for global access
window.uiSpecsModule = {
    loadUISpecs,
    showFunctionHelp,
    showMethodHelp,
    collectDynamicParameters,
    getCurrentLang,
    onLanguageChange,  // NEW: Called when language changes
    clearCache: () => {
        uiSpecsCache = null;
        uiSpecs = null;
        helpSpecsCache = null;
        console.log('[UI Specs] Cache cleared');
    }
};
