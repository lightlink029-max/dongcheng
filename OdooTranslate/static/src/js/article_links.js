/**
 * Ajoute le préfixe de langue aux liens d'articles Knowledge.
 * Ex: /knowledge/article/35 -> /en/knowledge/article/35
 * 
 * Cible:
 * - Les liens dans les articleIndex embedded
 * - Les liens avec la classe o_knowledge_article_link
 */
(function() {
    'use strict';

    function fixArticleLinks() {
        var match = window.location.pathname.match(/^\/([a-z]{2})\//);
        var lang = match ? match[1] : null;
        if (!lang) return;

        // Sélecteur combiné: articleIndex links ET o_knowledge_article_link
        var links = document.querySelectorAll(
            '[data-embedded="articleIndex"] a[href^="/knowledge/"], ' +
            'a.o_knowledge_article_link[href^="/knowledge/"]'
        );
        links.forEach(function(a) {
            var href = a.getAttribute('href');
            if (href && href.indexOf('/' + lang + '/') !== 0) {
                a.href = '/' + lang + href;
            }
        });
    }

    // Exécuter au chargement
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', fixArticleLinks);
    } else {
        fixArticleLinks();
    }

    // Observer les changements DOM (pour les chargements dynamiques)
    var observer = new MutationObserver(function(mutations) {
        fixArticleLinks();
    });

    if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
    } else {
        document.addEventListener('DOMContentLoaded', function() {
            observer.observe(document.body, { childList: true, subtree: true });
        });
    }
})();

