// Loader + Observer (head script already hid body + started Google Translate download)
// This file intentionally does NOT use @odoo-module — it must execute immediately
// as a plain script to prevent flash of untranslated content.
(function() {
    function getCookie(name) {
        var v = '; ' + document.cookie, p = v.split('; ' + name + '=');
        return p.length === 2 ? p.pop().split(';').shift() : null;
    }

    var googtrans = getCookie('googtrans');
    var isTranslated = googtrans && googtrans !== '/en/en' && googtrans !== '/en/' && googtrans !== 'null';
    var isEditMode = window.location.search.indexOf('enable_editor') !== -1 ||
                     document.documentElement.classList.contains('editor_enable');

    if (isEditMode) {
        document.documentElement.classList.remove('ot-pre-translate');
        return;
    }

    if (!document.getElementById('google_translate_element_hidden')) {
        var el = document.createElement('div');
        el.id = 'google_translate_element_hidden';
        el.style.display = 'none';
        document.documentElement.appendChild(el);
    }
    if (!window.googleTranslateElementInit) {
        window.googleTranslateElementInit = function() {
            if (window.google && window.google.translate && !document.querySelector('.goog-te-combo')) {
                new google.translate.TranslateElement({
                    pageLanguage: 'en',
                    layout: google.translate.TranslateElement.InlineLayout.SIMPLE,
                    autoDisplay: false
                }, 'google_translate_element_hidden');
            }
        };
    }
    if (!document.querySelector('script[src*="translate.google.com"]')) {
        var s = document.createElement('script');
        s.src = 'https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit';
        s.async = true;
        document.documentElement.appendChild(s);
    }

    if (isTranslated) {
        if (!document.getElementById('website-translator-loader')) {
            var loader = document.createElement('div');
            loader.id = 'website-translator-loader';
            loader.className = 'translator-loader';
            loader.innerHTML = '<div class="translator-spinner"></div><div class="translator-loading-text">Loading...</div>';
            document.documentElement.appendChild(loader);
        }

        var obs = new MutationObserver(function() {
            var html = document.documentElement;
            if (html.classList.contains('translated-ltr') || html.classList.contains('translated-rtl')) {
                html.classList.remove('ot-pre-translate');
                var l = document.getElementById('website-translator-loader');
                if (l) { l.classList.add('hidden'); setTimeout(function() { l.remove(); }, 300); }
                obs.disconnect();
            }
        });
        obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });

        setTimeout(function() {
            document.documentElement.classList.remove('ot-pre-translate');
            var l = document.getElementById('website-translator-loader');
            if (l) { l.classList.add('hidden'); setTimeout(function() { l.remove(); }, 300); }
            obs.disconnect();
        }, 4000);
    }
})();
