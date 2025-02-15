// ==UserScript==
// @name         Telegram Folder Controls
// @namespace    http://tampermonkey.net/
// @version      2025-01-30
// @description  Добавляет "Show All/Hide All Except This" в контекстное меню папок
// @match        https://web.telegram.org/a/
// @icon         https://www.google.com/s2/favicons?sz=64&domain=telegram.org
// @grant        GM_addStyle
// @grant        GM_setValue
// @grant        GM_getValue
// @author       skynet
// @updateURL    https://eurmtl.me/static/telegram.focus.user.js
// @downloadURL  https://eurmtl.me/static/telegram.focus.user.js
// ==/UserScript==

(function() {
    'use strict';

    const MENU_SELECTOR = '.Menu.compact.in-portal.Tab-context-menu';
    const FOLDER_SELECTOR = '.Tab--interactive';
    const STORY_RIBBON_ID = '#StoryRibbon';
    const HEADER_SELECTOR = '.LeftMainHeader';

    let currentTargetFolder = null;

    // Общие стили
    GM_addStyle(`
        .folder-hidden { display: none !important; }
    `);

    // Перехват правого клика
    document.addEventListener('contextmenu', e => {
        currentTargetFolder = e.target.closest(FOLDER_SELECTOR);
    });

    // Модификация меню
    const observer = new MutationObserver(() => {
        const menu = document.querySelector(MENU_SELECTOR);
        if (!menu || menu.dataset.customAdded) return;

        menu.querySelector('.menu-container').insertAdjacentHTML('afterbegin', `
            <div role="menuitem" class="MenuItem compact" id="show-all-folders">
                <i class="icon icon-eye"></i>Show All
            </div>
            <div role="menuitem" class="MenuItem compact" id="hide-others-folders">
                <i class="icon icon-eye-closed"></i>Hide All Except This
            </div>
        `);

        menu.dataset.customAdded = 'true';
        menu.querySelector('#show-all-folders').addEventListener('click', showAll);
        menu.querySelector('#hide-others-folders').addEventListener('click', hideOthers);
    });

    observer.observe(document.body, { childList: true, subtree: true });

    // Функции управления
    function showAll() {
        document.querySelectorAll(FOLDER_SELECTOR).forEach(el => el.classList.remove('folder-hidden'));
        document.querySelector(STORY_RIBBON_ID)?.classList.remove('folder-hidden');
        document.querySelector(HEADER_SELECTOR)?.classList.remove('folder-hidden');
    }

    function hideOthers() {
        document.querySelectorAll(FOLDER_SELECTOR).forEach(folder => {
            folder.classList.toggle('folder-hidden', folder !== currentTargetFolder);
        });

        // Скрываем дополнительные элементы
        document.querySelector(STORY_RIBBON_ID)?.classList.add('folder-hidden');
        document.querySelector(HEADER_SELECTOR)?.classList.add('folder-hidden');
    }
})();