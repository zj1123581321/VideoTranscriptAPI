(function (root) {
  function t(key, vars) {
    var table = root.I18N || {};
    var text = table[key];
    if (text == null) {
      throw new Error('missing i18n key ' + key);
    }
    if (vars) {
      Object.keys(vars).forEach(function (name) {
        text = text.replace(new RegExp('\\{' + name + '\\}', 'g'), String(vars[name]));
      });
    }
    return text;
  }

  function applyI18n(rootEl) {
    var lang = root.__VTA_LANG__;
    if (lang && root.document && root.document.documentElement) {
      root.document.documentElement.setAttribute('lang', lang);
    }
    var scope = rootEl || (root.document && root.document);
    if (!scope || !scope.querySelectorAll) {
      return;
    }
    var nodes = scope.querySelectorAll('[data-i18n]');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var key = el.getAttribute('data-i18n');
      var attr = el.getAttribute('data-i18n-attr');
      var value = t(key);
      if (attr) {
        el.setAttribute(attr, value);
      } else {
        el.textContent = value;
      }
    }
    var attrNodes = scope.querySelectorAll('[data-i18n-placeholder], [data-i18n-title], [data-i18n-aria-label]');
    for (var j = 0; j < attrNodes.length; j++) {
      var node = attrNodes[j];
      if (node.hasAttribute('data-i18n-placeholder')) {
        node.setAttribute('placeholder', t(node.getAttribute('data-i18n-placeholder')));
      }
      if (node.hasAttribute('data-i18n-title')) {
        node.setAttribute('title', t(node.getAttribute('data-i18n-title')));
      }
      if (node.hasAttribute('data-i18n-aria-label')) {
        node.setAttribute('aria-label', t(node.getAttribute('data-i18n-aria-label')));
      }
    }
  }

  root.t = t;
  root.applyI18n = applyI18n;
})(typeof window !== 'undefined' ? window : globalThis);
