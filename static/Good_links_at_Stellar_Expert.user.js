// ==UserScript==
// @name        Good_links_at_Stellar_Expert
// @namespace   http://tampermonkey.net/
// @match       https://stellar.expert/explorer/public/account/*
// @grant       none
// @version     0.6
// @description Change links at Stellar Expert
// @author      skynet
// @updateURL   https://eurmtl.me/static/Good_links_at_Stellar_Expert.user.js
// @downloadURL https://eurmtl.me/static/Good_links_at_Stellar_Expert.user.js
// @icon        data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==
// ==/UserScript==

let observer;

(function() {
    'use strict';

    function modifyLinks() {
        // Отключаем observer
        observer.disconnect();

        let links = document.querySelectorAll('.account-balance');
        links.forEach((link) => {
            let assetLink = link.querySelector('.asset-link');
            let asset = assetLink.getAttribute('aria-label');
            if (asset) {
                let newHref;

                // Если asset содержит "-", значит это первый формат
                if (asset.includes('-')) {
                    newHref = `https://stellar.expert/explorer/public/asset/${asset}`;
                } else {
                    // Иначе это второй формат
                    newHref = `https://stellar.expert/explorer/public/liquidity-pool/${asset}`;
                }

                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    window.location.href = newHref;
                });
            }
        });

        // Включаем observer снова
        observer.observe(document.body, { attributes: false, childList: true, subtree: true });
    }

    function isValidBase64(str) {
        try {
            atob(str);
            return true;
        } catch (e) {
            return false;
        }
    }

    function decodeBase64Text() {
        // Отключаем observer
        observer.disconnect();

        let encodedListItems = document.querySelectorAll('.text-small.condensed .word-break');
        if (encodedListItems) {
            encodedListItems.forEach(item => {
                let separatorIndex = item.textContent.lastIndexOf(': ');
                if (separatorIndex > -1) {
                    let property = item.textContent.substring(0, separatorIndex);
                    let encodedText = item.textContent.substring(separatorIndex + 2);
                    if (isValidBase64(encodedText) && !encodedText.startsWith('*')) {
                        let decodedText = '*' + atob(encodedText);
                        item.textContent = property + ': ' + decodedText;
                    }
                }
            });
        }

        // Включаем observer снова
        observer.observe(document.body, { attributes: false, childList: true, subtree: true });
    }

    function removeUnwantedElements() {
        // Отключаем observer
        observer.disconnect();

        let unwantedElements = document.querySelectorAll('.account-balance.claimable:not(:last-child)');
        unwantedElements.forEach(element => element.remove());

        // Включаем observer снова
        observer.observe(document.body, { attributes: false, childList: true, subtree: true });
    }

    function processDOMChanges() {
        modifyLinks();
        decodeBase64Text();
        removeUnwantedElements();
    }

    // Check if the URL matches the specific pattern
    const urlPattern = /https:\/\/stellar.expert\/explorer\/public\/account\/[^/]+$/;
    if (urlPattern.test(window.location.href)) {
        observer = new MutationObserver(processDOMChanges);
        observer.observe(document.body, { attributes: false, childList: true, subtree: true });
    }
})();