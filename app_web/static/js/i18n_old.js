/**
 * DataLab Web i18n Module
 * Provides multilingual support for the application
 */

(function() {
  'use strict';

  // Translation dictionaries
  const translations = {
    zh: {
      // Navigation
      'nav.extrapolation': '序列外推',
      'nav.uncertainty': '误差传递',
      'nav.fitting': '拟合',
      'nav.statistics': '统计',
      'nav.docs': '文档',

      // Footer
      'footer.version': 'DataLab Web - 版本 1.0',
      'footer.deployHint': '生产环境部署请参考 ',
      'footer.docsLink': '使用与技术文档',

      // Documentation page
      'docs.title': '文档',
      'docs.subtitle': 'DataLab Web 使用指南与技术文档',
      'docs.backToHome': '返回主页',
      'docs.fullDocSite': '完整文档站（MkDocs）',
      'docs.tableOfContents': '目录',
      'docs.previous': '上一页',
      'docs.next': '下一页',

      // Buttons and Actions
      'btn.run': '运行',
      'btn.download': '下载',
      'btn.downloadCSV': '下载 CSV',
      'btn.downloadPDF': '下载 PDF',
      'btn.generate': '生成',
      'btn.calculate': '计算',
      'btn.reset': '重置',

      // Common labels
      'label.dataInput': '数据输入',
      'label.parameters': '参数',
      'label.results': '结果',
      'label.latex': 'LaTeX',
      'label.plot': '图表',
      'label.uncertainty': '不确定度',

      // Help system
      'help.formulaTitle': '可用函数',
      'help.methodTitle': '外推方法说明',
      'help.close': '关闭',
    },
    en: {
      // Navigation
      'nav.extrapolation': 'Extrapolation',
      'nav.uncertainty': 'Error Propagation',
      'nav.fitting': 'Fitting',
      'nav.statistics': 'Statistics',
      'nav.docs': 'Docs',

      // Footer
      'footer.version': 'DataLab Web - v1.0',
      'footer.deployHint': 'For production deployment, refer to ',
      'footer.docsLink': 'Documentation',

      // Documentation page
      'docs.title': 'Documentation',
      'docs.subtitle': 'User Guide & Technical Documentation',
      'docs.backToHome': 'Back to Home',
      'docs.fullDocSite': 'Full Documentation Site (MkDocs)',
      'docs.tableOfContents': 'Table of Contents',
      'docs.previous': 'Previous',
      'docs.next': 'Next',

      // Buttons and Actions
      'btn.run': 'Run',
      'btn.download': 'Download',
      'btn.downloadCSV': 'Download CSV',
      'btn.downloadPDF': 'Download PDF',
      'btn.generate': 'Generate',
      'btn.calculate': 'Calculate',
      'btn.reset': 'Reset',

      // Common labels
      'label.dataInput': 'Data Input',
      'label.parameters': 'Parameters',
      'label.results': 'Results',
      'label.latex': 'LaTeX',
      'label.plot': 'Plot',
      'label.uncertainty': 'Uncertainty',

      // Help system
      'help.formulaTitle': 'Available Functions',
      'help.methodTitle': 'Extrapolation Method Description',
      'help.close': 'Close',
    }
  };

  // Current language
  let currentLang = localStorage.getItem('datalab_lang') || 'zh';

  // i18n module
  const i18nModule = {
    /**
     * Get translation for a key
     * @param {string} key - Translation key (e.g., 'nav.extrapolation')
     * @param {object} params - Optional parameters for interpolation
     * @returns {string} - Translated text
     */
    t: function(key, params) {
      const dict = translations[currentLang] || translations.zh;
      let text = dict[key] || key;

      // Simple parameter interpolation: {param}
      if (params) {
        for (const [key, value] of Object.entries(params)) {
          text = text.replace(new RegExp(`{${key}}`, 'g'), value);
        }
      }

      return text;
    },

    /**
     * Set current language
     * @param {string} lang - Language code ('zh' or 'en')
     */
    setLang: function(lang) {
      if (translations[lang]) {
        currentLang = lang;
        localStorage.setItem('datalab_lang', lang);
        // Update <html lang> attribute
        document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
      }
    },

    /**
     * Get current language
     * @returns {string} - Current language code
     */
    getLang: function() {
      return currentLang;
    },

    /**
     * Apply i18n to all elements with data-i18n attribute
     */
    applyI18n: function() {
      document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (key) {
          // Check if it's a link inside translated text
          if (el.tagName === 'A' && el.parentElement && el.parentElement.hasAttribute('data-i18n')) {
            // Skip - will be handled by parent
            return;
          }

          // Handle text with embedded links
          const hasLink = el.querySelector('a[data-i18n]');
          if (hasLink) {
            const linkKey = hasLink.getAttribute('data-i18n');
            const linkText = this.t(linkKey);
            const parentKey = key;
            const parentText = this.t(parentKey);

            // Replace link placeholder with actual link
            // Assuming parent text contains the full text
            el.childNodes.forEach(node => {
              if (node.nodeType === Node.TEXT_NODE) {
                node.textContent = parentText.replace(linkText, '');
              }
            });
            hasLink.textContent = linkText;
          } else {
            el.textContent = this.t(key);
          }
        }
      });

      // Update placeholder attributes
      document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (key) {
          el.placeholder = this.t(key);
        }
      });

      // Update title attributes
      document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (key) {
          el.title = this.t(key);
        }
      });
    }
  };

  // Auto-apply i18n on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      i18nModule.setLang(currentLang);
      i18nModule.applyI18n();
    });
  } else {
    i18nModule.setLang(currentLang);
    i18nModule.applyI18n();
  }

  // Export to global scope
  window.i18nModule = i18nModule;
})();
