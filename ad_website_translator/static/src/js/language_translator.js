/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.WebsiteTranslate = publicWidget.Widget.extend({
    selector: '#wrapwrap',

    start: function () {
        var self = this;

        if (document.body.classList.contains('editor_enable') || $('.editor_enable').length > 0) {
            self.setLanguageCookie('en');
            document.documentElement.classList.remove('ot-pre-translate');
            var loader = document.getElementById('website-translator-loader');
            if (loader) loader.remove();
            return this._super.apply(this, arguments);
        }

        var $ww = $('#wrapwrap');
        var rawLangsJson          = $ww.attr('data-translator-languages-json');
        this.translator_position  = $ww.attr('data-translator-position')      || 'both';
        this.translator_style     = $ww.attr('data-translator-style')          || 'pill';
        this.translator_primary_color = $ww.attr('data-translator-primary-color') || '#714B67';

        this.applyDynamicStyling();

        this.languages = [];
        if (rawLangsJson) {
            try { this.languages = JSON.parse(rawLangsJson); }
            catch (e) { console.error('Translator: JSON parse failed', e); }
        }
        if (!this.languages.length) {
            this.languages = [
                { code: 'en', name: 'English',   flag: '🇺🇸' },
                { code: 'es', name: 'Español',   flag: '🇪🇸' },
                { code: 'fr', name: 'Français',  flag: '🇫🇷' },
                { code: 'de', name: 'Deutsch',   flag: '🇩🇪' },
                { code: 'it', name: 'Italiano',  flag: '🇮🇹' },
                { code: 'pt', name: 'Português', flag: '🇵🇹' }
            ];
        }

        var googtrans = this.getCookie('googtrans');
        this.currentLangCode = 'en';
        var m = googtrans && googtrans.match(/\/en\/([^/]+)/);
        if (m && m[1]) this.currentLangCode = m[1];

        this.renderCustomSelector();
        this.bindNavigationEvents();

        return this._super.apply(this, arguments);
    },

    getCookie: function (name) {
        var v = '; ' + document.cookie, p = v.split('; ' + name + '=');
        return p.length === 2 ? p.pop().split(';').shift() : null;
    },

    setLanguageCookie: function (langCode) {
        var val = '/en/' + langCode;
        var hosts = [
            '',
            'domain=' + window.location.hostname + ';',
            'domain=.' + window.location.hostname.replace(/^www\./, '') + ';'
        ];
        if (langCode === 'en') {
            hosts.forEach(function(h) {
                document.cookie = 'googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;' + h;
            });
        } else {
            hosts.forEach(function(h) {
                document.cookie = 'googtrans=' + val + '; path=/;' + h;
            });
        }
    },

    applyDynamicStyling: function () {
        var c = this.translator_primary_color;
        if (!c) return;
        var id = 'website-translator-dynamic-styles';
        var el = document.getElementById(id) || document.createElement('style');
        el.id = id;
        el.innerHTML =
            '.translator-spinner { border-top-color: ' + c + ' !important; }' +
            '.ot-item:hover  { background-color: ' + c + '14 !important; color: ' + c + ' !important; }' +
            '.ot-item.active { background-color: ' + c + '   !important; color: #fff !important; }' +
            '.ot-flat-item.active { color: ' + c + ' !important; border-bottom-color: ' + c + ' !important; }' +
            '.ot-flat-item:hover  { color: ' + c + ' !important; }';
        if (!document.getElementById(id)) document.head.appendChild(el);
    },

    translatePageInline: function (langCode) {
        var self = this;
        self.setLanguageCookie(langCode);
        self.currentLangCode = langCode;

        document.body.classList.add('ot-translating');
        document.body.classList.remove('ot-translated-in');
        self.renderCustomSelector();

        var selectEl = document.querySelector('select.goog-te-combo');
        if (selectEl) {
            self._doTranslate(langCode, selectEl);
        } else {
            self._pollForSelect(langCode, 0);
        }
    },

    _doTranslate: function (langCode, selectEl) {
        var self = this;
        if (langCode === 'en') {
            var opt = Array.from(selectEl.options).find(function(o) {
                return o.value === '' || o.value === 'en';
            });
            selectEl.value = opt ? opt.value : '';
        } else {
            selectEl.value = langCode;
        }
        selectEl.dispatchEvent(new Event('change', { bubbles: true }));

        var obs = new MutationObserver(function() {
            var html = document.documentElement;
            var done = langCode === 'en'
                ? !html.classList.contains('translated-ltr') && !html.classList.contains('translated-rtl')
                : html.classList.contains('translated-ltr') || html.classList.contains('translated-rtl');
            if (done) { obs.disconnect(); self._revealContent(); }
        });
        obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        setTimeout(function() { obs.disconnect(); self._revealContent(); }, 800);
    },

    _revealContent: function () {
        document.body.classList.remove('ot-translating');
        document.body.classList.add('ot-translated-in');
        setTimeout(function() { document.body.classList.remove('ot-translated-in'); }, 350);
    },

    _pollForSelect: function (langCode, attempts) {
        var self = this;
        var el = document.querySelector('select.goog-te-combo');
        if (el) {
            self._doTranslate(langCode, el);
        } else if (attempts < 40) {
            setTimeout(function() { self._pollForSelect(langCode, attempts + 1); }, 100);
        } else {
            self._revealContent();
            window.location.reload();
        }
    },

    renderCustomSelector: function () {
        var self = this;
        $('.ot-dropdown, .ot-flat-container').remove();

        var activeLang = this.languages.find(function(l) { return l.code === self.currentLangCode; })
                      || this.languages[0];
        var hasNavbar  = $('#google_translate_element').length > 0;
        var showNavbar = this.translator_position === 'both' || this.translator_position === 'navbar';
        var showFloat  = this.translator_position === 'both' || this.translator_position === 'floating'
                      || (!hasNavbar && showNavbar);

        if (this.translator_style === 'flat') {
            var buildFlat = function(isNav) {
                var $c = $('<div class="ot-flat-container notranslate ' + (isNav ? 'navbar-item' : 'floating') + '"></div>');
                self.languages.forEach(function(lang) {
                    var $a = $('<a class="ot-flat-item ' + (lang.code === self.currentLangCode ? 'active' : '') +
                               '" href="#" title="' + lang.name + '">' + lang.flag + '</a>');
                    $a.on('click', function(e) {
                        e.preventDefault();
                        if (lang.code !== self.currentLangCode) self.translatePageInline(lang.code);
                    });
                    $c.append($a);
                });
                return $c;
            };
            if (showNavbar && hasNavbar) $('#google_translate_element').append(buildFlat(true));
            if (showFloat)               $('body').append(buildFlat(false));
        } else {
            var buildDD = function(isNav) {
                var $d = $('<div class="ot-dropdown notranslate ' + (isNav ? 'navbar-item' : 'floating') + '"></div>');
                var btnHtml = self.translator_style === 'minimal'
                    ? '<span class="ot-flag">' + activeLang.flag + '</span>'
                    : '<span class="ot-flag">' + activeLang.flag + '</span><span class="ot-name">' + activeLang.name + '</span>';
                var $btn  = $('<button class="ot-btn" type="button">' + btnHtml + '</button>');
                var $menu = $('<div class="ot-menu"></div>');

                self.languages.forEach(function(lang) {
                    var $item = $('<a class="ot-item ' + (lang.code === self.currentLangCode ? 'active' : '') +
                                  '" href="#"><span class="ot-flag">' + lang.flag +
                                  '</span><span class="ot-name">' + lang.name + '</span></a>');
                    $item.on('click', function(e) {
                        e.preventDefault();
                        $d.removeClass('open');
                        if (lang.code !== self.currentLangCode) self.translatePageInline(lang.code);
                    });
                    $menu.append($item);
                });

                $d.append($btn).append($menu);
                $btn.on('click', function(e) {
                    e.stopPropagation();
                    $('.ot-dropdown').not($d).removeClass('open');
                    $d.toggleClass('open');
                });
                $(document).on('click.otdrop', function() { $d.removeClass('open'); });
                return $d;
            };
            if (showNavbar && hasNavbar) $('#google_translate_element').append(buildDD(true));
            if (showFloat)               $('body').append(buildDD(false));
        }
    },

    bindNavigationEvents: function () {
        if (this.currentLangCode === 'en') return;

        document.addEventListener('click', function (e) {
            var anchor = e.target.closest('a');
            if (!anchor || !anchor.href) return;
            var url;
            try { url = new URL(anchor.href, window.location.href); } catch (err) { return; }
            if (url.origin !== window.location.origin) return;

            var href = anchor.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('javascript:') ||
                anchor.classList.contains('dropdown-toggle') ||
                anchor.closest('.o_edit_mode_menu') ||
                anchor.closest('#oe_main_menu_navbar') ||
                anchor.closest('.editor_enable') ||
                anchor.closest('.notranslate')) return;

            e.preventDefault();
            e.stopPropagation();
            document.body.classList.add('ot-translating');
            window.location.href = anchor.href;
        }, true);
    }
});
