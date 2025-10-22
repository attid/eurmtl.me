// ==UserScript==
// @name        Good_links_at_Stellar_Expert
// @namespace   http://tampermonkey.net/
// @match       https://stellar.expert/*
// @grant       none
// @version     1.12
// @description Change links at Stellar Expert
// @author      skynet
// @updateURL   https://eurmtl.me/static/Good_links_at_Stellar_Expert.user.js
// @downloadURL https://eurmtl.me/static/Good_links_at_Stellar_Expert.user.js
// @icon        https://eurmtl.me/static/favicon.ico
// ==/UserScript==

let observer;

async function CalcOrders(accountAddress) {
    const url = `https://horizon.stellar.org/accounts/${accountAddress}/offers?limit=100`;

    try {
        const response = await fetch(url);
        const data = await response.json();

        if (!data._embedded || !data._embedded.records) {
            console.error('No offers found.');
            return;
        }

        const totals = {};

        data._embedded.records.forEach(offer => {
            const { selling, amount } = offer;
            let assetKey;

            if (selling.asset_type === 'native') {
                assetKey = 'XLM';
            } else {
                assetKey = `${selling.asset_code}-${selling.asset_issuer}`;
            }

            if (totals[assetKey]) {
                totals[assetKey] += parseFloat(amount);
            } else {
                totals[assetKey] = parseFloat(amount);
            }
        });

        console.log(totals);
        document.querySelectorAll('.account-balance').forEach(balanceElement => {
            const assetLabelElement = balanceElement.querySelector('[aria-label]');
            if (assetLabelElement) {
                const assetLabel = assetLabelElement.getAttribute('aria-label');
                if (totals[assetLabel]) {
                    const condensedText = balanceElement.querySelector('.condensed').textContent.replace(',', '').trim();
                    const currentAmount = parseFloat(condensedText);
                    const freeAmount = currentAmount - totals[assetLabel];
                    const summaryText = `Orders (${totals[assetLabel].toFixed(2)}) Free (${freeAmount.toFixed(2)})`;
                    const tinyCondensedDiv = balanceElement.querySelector('.text-tiny.condensed');
                    tinyCondensedDiv.innerHTML = `<div style="color: black;">${summaryText}</div>`;
                }
            }
        });

    } catch (error) {
        console.error('Error fetching or processing data:', error);
    }
}

function initButton() {
    // Извлечение адреса аккаунта
    const accountAddressElement = document.querySelector('.account-address .account-key');

    if (accountAddressElement) {
        const accountAddress = accountAddressElement.innerText.trim();
        addExternalLinks(accountAddress);
    } else {
        console.error('Адрес аккаунта не найден.');
    }
}

function addExternalLinks(accountAddress) {
    const buttonStellarchain = document.createElement('a');
    const buttonScopuly = document.createElement('a');
    const buttonCalcOrders = document.createElement('a');
    const buttonWhereSigner = document.createElement('a');
    const buttonBSN = document.createElement('a');

    // Настройка кнопки для Stellarchain
    buttonStellarchain.href = `https://stellarchain.io/accounts/${accountAddress}`;
    buttonStellarchain.innerText = 'Stellarchain';
    buttonStellarchain.target = "_blank";
    buttonStellarchain.classList.add('button', 'small', 'text-small', 'skynet-button');
    //buttonStellarchain.style.marginRight = '10px';

    // Настройка кнопки для Scopuly
    buttonScopuly.href = `https://scopuly.com/account/${accountAddress}`;
    buttonScopuly.innerText = 'Scopuly';
    buttonScopuly.target = "_blank";
    buttonScopuly.classList.add('button', 'small', 'text-small', 'skynet-button');

    const buttonBsnExpert = document.createElement('a');
    buttonBsnExpert.href = `https://bsn.expert/accounts/${accountAddress}`;
    buttonBsnExpert.innerText = 'bsn.expert';
    buttonBsnExpert.target = "_blank";
    buttonBsnExpert.classList.add('button', 'small', 'text-small', 'skynet-button');
    // Настройка кнопки Calc Orders
    buttonCalcOrders.href = '#';
    buttonCalcOrders.innerText = 'Reload Scripts';
    buttonCalcOrders.addEventListener('click', () => reloadScripts(accountAddress));
    buttonCalcOrders.classList.add('button', 'small', 'text-small', 'skynet-button');

    // Настройка кнопки Calc Orders
    buttonWhereSigner.href = '#';
    buttonWhereSigner.innerText = '🔑';
    buttonWhereSigner.addEventListener('click', () => loadWhereSigner(accountAddress));
    buttonWhereSigner.classList.add('button', 'small', 'text-small', 'skynet-button');

    // Настройка кнопки Calc Orders
    buttonBSN.href = '#';
    buttonBSN.innerText = 'BSN';
    buttonBSN.addEventListener('click', () => loadBSN(accountAddress));
    buttonBSN.classList.add('button', 'small', 'text-small', 'skynet-button');

    // Поиск элемента для добавления кнопок
    const parentElement = document.querySelector('h1, h2'); // Измените селектор в соответствии с реальным расположением на странице

    // Добавление кнопок на страницу
    if (parentElement) {
        parentElement.appendChild(buttonBsnExpert);
        parentElement.appendChild(buttonScopuly);
        parentElement.appendChild(buttonStellarchain);

        const moreButton = document.createElement('button');
        moreButton.innerText = 'More';
        moreButton.classList.add('button', 'small', 'text-small', 'skynet-button');
        parentElement.appendChild(moreButton);

        const hiddenButtons = document.createElement('div');
        hiddenButtons.style.display = 'none';
        hiddenButtons.appendChild(buttonCalcOrders);
        hiddenButtons.appendChild(buttonWhereSigner);
        hiddenButtons.appendChild(buttonBSN);
        parentElement.appendChild(hiddenButtons);

        moreButton.addEventListener('click', () => {
            hiddenButtons.style.display = hiddenButtons.style.display === 'none' ? 'block' : 'none';
        });
    }

}


function removeUnwantedElements() {
    let unwantedElements = document.querySelectorAll('.account-balance.claimable:not(:last-child)');
    unwantedElements.forEach(element => element.remove());
}

function isValidBase64(str) {
    try {
        atob(str);
        return true;
    } catch (e) {
        return false;
    }
}

function isValidStellarAddress(address) {
    return /^[G][A-Z2-7]{55}$/.test(address);
}

function decodeBase64Text() {
    function isValidUrl(string) {
        try { new URL(string); return true; } catch { return false; }
    }
    function createLink(url) {
        const link = document.createElement('a');
        link.href = url; link.textContent = url; link.target = '_blank';
        link.rel = 'noopener noreferrer';
        return link;
    }

    const encodedListItems = document.querySelectorAll('.text-small.condensed .word-break');

    if (!encodedListItems) return;

    encodedListItems.forEach(item => {
        // пример строки: "A1: <encoded>"
        const sepIdx = item.textContent.lastIndexOf(': ');
        if (sepIdx <= -1) return;

        const property = item.textContent.substring(0, sepIdx).trim();       // "A1"
        const encodedText = item.getAttribute('data-old')                     // уже ставили выше
            ?? item.textContent.substring(sepIdx + 2);

        // уже обработано — не трогаем разметку, но проставим мета-данные если их ещё нет
        if (item.hasAttribute('data-decoded') && item.hasAttribute('data-prop')) return;

        if (isValidBase64(encodedText) && !String(encodedText).startsWith('*')) {
            const decodedText = atob(encodedText);

            // Сохраняем для фильтра
            item.setAttribute('data-prop', property);
            item.setAttribute('data-decoded', decodedText.toLowerCase());

            // Перерисовываем видимую часть (как и раньше)
            // Очищаем и ставим "A1: " префикс
            item.textContent = property + ': ';

            if (isValidStellarAddress(decodedText)) {
                const link = document.createElement('a');
                link.href = `https://stellar.expert/explorer/public/account/${decodedText}`;
                link.textContent = decodedText;
                link.target = '_blank';
                item.appendChild(link);
            } else if (isValidUrl(decodedText)) {
                item.appendChild(createLink(decodedText));
            } else {
                const urlRegex = /(https?:\/\/[^\s]+)/g;
                let lastIndex = 0, match;
                while ((match = urlRegex.exec(decodedText)) !== null) {
                    if (match.index > lastIndex) {
                        item.appendChild(document.createTextNode(decodedText.substring(lastIndex, match.index)));
                    }
                    item.appendChild(createLink(match[0]));
                    lastIndex = match.index + match[0].length;
                }
                if (lastIndex < decodedText.length) {
                    item.appendChild(document.createTextNode(decodedText.substring(lastIndex)));
                }
            }
        } else {
            // Небезопасно/не base64: всё равно сохраняем prop и «сырой» текст для базового поиска
            const raw = item.textContent.substring(sepIdx + 2).toLowerCase();
            item.setAttribute('data-prop', property);
            item.setAttribute('data-decoded', raw);
        }
    });
}

function addDataEntriesFilter() {
    // Ищем H4 с текстом "Data Entries"
    const headers = Array.from(document.querySelectorAll('h4'));
    const dataH4 = headers.find(h => h.textContent.trim().startsWith('Data Entries'));
    if (!dataH4) return;

    // Не дублировать
    if (dataH4.querySelector('.skynet-data-filter')) return;

    // Создаём input
    const wrap = document.createElement('span');
    wrap.style.marginLeft = '8px';

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'skynet-data-filter';
    input.placeholder = 'фильтр по имени/значению… (Enter)';
    input.title = 'Фильтрует элементы ниже по имени (A1, A10, …) и по значению. Нажмите Enter для применения, Esc — очистить.';
    input.style.cssText = 'font-size:12px;padding:3px 6px;min-width:260px;border-radius:6px;border:1px solid #ddd;';

    // Подсказка-хинт
    const hint = document.createElement('span');
    hint.className = 'text-tiny dimmed';
    hint.textContent = ' ⏎ для фильтра, Esc — сброс';
    hint.style.marginLeft = '6px';

    wrap.appendChild(input);
    wrap.appendChild(hint);
    dataH4.appendChild(wrap);

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            filterDataEntries(input.value);
        } else if (e.key === 'Escape') {
            input.value = '';
            filterDataEntries('');
        }
    });
}

function filterDataEntries(query) {
    // Находим соответствующий UL сразу после заголовка "Data Entries"
    const headers = Array.from(document.querySelectorAll('h4'));
    const dataH4 = headers.find(h => h.textContent.trim().startsWith('Data Entries'));
    if (!dataH4) return;

    // Ищем ближайший UL с классом списка данных (обычно он следующий)
    let ul = dataH4.nextElementSibling;
    while (ul && !(ul.tagName === 'UL' && ul.classList.contains('text-small') && ul.classList.contains('condensed'))) {
        ul = ul.nextElementSibling;
    }
    if (!ul) return;

    const q = (query || '').trim().toLowerCase();
    const items = ul.querySelectorAll('li.word-break');

    if (!q) {
        items.forEach(li => { li.style.display = ''; });
        return;
    }

    // Фильтруем: имя (data-prop, напр. "A10") ИЛИ значение (data-decoded)
    items.forEach(li => {
        const prop = (li.getAttribute('data-prop') || '').toLowerCase();
        const val  = (li.getAttribute('data-decoded') || li.textContent || '').toLowerCase();
        const match = prop.includes(q) || val.includes(q);
        li.style.display = match ? '' : 'none';
    });
}


function modifyLinks() {
    let links = document.querySelectorAll('.account-balance');
    links.forEach((link) => {
        let assetLink = link.querySelector('.asset-link');
        if (assetLink) {
            let asset = assetLink.getAttribute('aria-label');

            if (!assetLink.querySelector('.skynet-helper')) {
                let newHref;

                if (asset.includes('-')) {
                    newHref = `https://stellar.expert/explorer/public/asset/${asset}`;
                } else {
                    newHref = `https://stellar.expert/explorer/public/liquidity-pool/${asset}`;
                }

                let searchButton = document.createElement('span');
                searchButton.className = 'skynet-helper'; // Установка класса для новой кнопки
                searchButton.setAttribute('onclick', `location.href='${newHref}';`);
                searchButton.setAttribute('style', 'background-color: black; color: white; border-radius: 50%; padding: 5px; margin-left: 10px; cursor: pointer;');
                searchButton.innerHTML = '<span style="font-size: 16px;">🔍</span>';

                assetLink.appendChild(searchButton);
            }
        }
    });
}


function initOfferButton() {
    const offerId = new URL(window.location.href).pathname.split('/').pop().split('?')[0];

    if (offerId) {
        const button = document.createElement('a');
        button.href = `https://horizon.stellar.org/offers/${offerId}`;
        button.target = '_blank';
        button.className = 'button small text-small skynet-button';
        button.textContent = 'Horizon';

        const h2Elements = document.querySelectorAll('h2');
        let found = false;
        for (let h2 of h2Elements) {
            const span = h2.querySelector('span.dimmed');
            if (span && span.textContent.includes('DEX offer')) {
                h2.appendChild(button);
                found = true;
                break;
            }
        }
        if (!found) {
            console.error('Заголовок предложения DEX не найден.');
        }
    } else {
        console.error('ID предложения не найден.');
    }
}

function loadXDR(txID) {
    const url = 'https://horizon.stellar.org/transactions/' + txID;

    fetch(url)
        .then(response => response.json())
        .then(data => {
            // Получаем envelope_xdr из ответа
            const envelopeXDR = data.envelope_xdr;

            // Создаём новый div с XDR
            const xdrDiv = document.createElement('div');
            xdrDiv.className = 'xdr-container';
            xdrDiv.style.cssText = `
                padding: 10px;
                border-radius: 4px;
                margin-bottom: 10px;
                word-break: break-all;
                font-family: monospace;
            `;

            // Добавляем заголовок
            const heading = document.createElement('h4');
            heading.textContent = 'Transaction XDR:';
            heading.style.marginBottom = '5px';
            xdrDiv.appendChild(heading);

            // Добавляем сам XDR
            const xdrContent = document.createElement('div');
            xdrContent.textContent = envelopeXDR;
            xdrContent.style.cssText = `
                -webkit-user-select: all !important;
                -moz-user-select: all !important;
                -ms-user-select: all !important;
                user-select: all !important;
            `;
            xdrDiv.appendChild(xdrContent);

            // Находим ближайший div с классом segment
            const segmentDiv = document.querySelector('.segment');
            if (segmentDiv) {
                // Вставляем новый div в начало segment
                segmentDiv.insertBefore(xdrDiv, segmentDiv.firstChild);
            } else {
                console.error('Элемент с классом segment не найден');
            }
        })
        .catch(error => {
            console.error('Ошибка при загрузке XDR:', error);
        });
}

function initTxButton() {
    //const txId = new URL(window.location.href).pathname.split('/').pop().split('?')[0];
    const txId = document.querySelector('h2 .block-select').textContent.trim();
    console.log(txId);

    if (txId) {
        const button = document.createElement('a');
        button.href = '#';
        button.innerText = 'Get XDR';
        button.classList.add('button', 'small', 'text-small', 'skynet-button');
        button.addEventListener('click', () => loadXDR(txId));

        // Поиск элемента для добавления кнопок
        const parentElement = document.querySelector('h1, h2'); // Измените селектор в соответствии с реальным расположением на странице

        // Добавление кнопок на страницу
        if (parentElement) {
            parentElement.appendChild(button);
        }

    } else {
        console.error('ID предложения не найден.');
    }
}


function checkPage() {
    const accountPattern = /https:\/\/stellar.expert\/explorer\/public\/account\/[^/]+$/;
    const offerPattern = /https:\/\/stellar.expert\/explorer\/public\/offer\/[^/]+$/;
    const txPattern = /https:\/\/stellar.expert\/explorer\/public\/tx\/[^/]+$/;
    const assetPattern = /https:\/\/stellar.expert\/explorer\/public\/asset\/[A-Za-z0-9\-\.]*$/;
    const liquidityPoolPattern = /https:\/\/stellar.expert\/explorer\/public\/liquidity-pool\/[A-Za-z0-9]*$/;
    const contractPattern = /https:\/\/stellar.expert\/explorer\/public\/contract\/[^/]+$/;
    const currentUrl = window.location.href;

    if (accountPattern.test(currentUrl)) {
        if (!document.querySelector('.skynet-button')) {
            //console.log("URL соответствует и кнопок нет, выполняем скрипт.");
            initButton()
            removeUnwantedElements();
        }
        modifyLinks();
        decodeBase64Text();
        addDataEntriesFilter();
        addBalancesFilter();


    } else if (assetPattern.test(currentUrl)) {
        if (!document.querySelector('.skynet-button')) {
            //console.log("URL соответствует и кнопок нет, выполняем скрипт.");
            initAssetButton();
        }
    } else if (liquidityPoolPattern.test(currentUrl)) {
        if (!document.querySelector('.skynet-button')) {
            //console.log("URL соответствует и кнопок нет, выполняем скрипт.");
            initLiquidityPoolButton();
        }
    } else if (contractPattern.test(currentUrl)) {
        modifyLinks();
    }
    if (offerPattern.test(currentUrl)) {
        if (!document.querySelector('.skynet-button')) {
            //console.log("URL соответствует и кнопок нет, выполняем скрипт.");
            initOfferButton()
        }
    }
    if (txPattern.test(currentUrl)) {
        if (!document.querySelector('.skynet-button')) {
            //console.log("URL соответствует и кнопок нет, выполняем скрипт.");
            initTxButton()
        }
    }
}

function initAssetButton() {
    const assetFull = new URL(window.location.href).pathname.split('/').pop();
    const assetParts = assetFull.split('-');
    const asset = assetParts[0];
    const issuer = assetParts.length > 1 ? assetParts[1] : null;

    if (assetFull) {
        const h2Elements = document.querySelectorAll('h2');
        let parentElement;
        for (let h2 of h2Elements) {
            const span = h2.querySelector('span.dimmed');
            if (span) {
                parentElement = h2;
                break;
            }
        }

        if (parentElement) {
            const buttonEurl = document.createElement('a');
            buttonEurl.href = `https://eurmtl.me/asset/${asset}`;
            buttonEurl.target = '_blank';
            buttonEurl.className = 'button small text-small skynet-button';
            buttonEurl.textContent = 'eurmtl.me';
            parentElement.appendChild(buttonEurl);

            const buttonStellarchain = document.createElement('a');
            buttonStellarchain.href = `https://stellarchain.io/assets/${assetFull}`;
            buttonStellarchain.target = '_blank';
            buttonStellarchain.className = 'button small text-small skynet-button';
            buttonStellarchain.textContent = 'Stellarchain';
            parentElement.appendChild(buttonStellarchain);

            if (issuer) {
                const buttonScopuly = document.createElement('a');
                buttonScopuly.href = `https://scopuly.com/trade/${asset}-XLM/${issuer}/native`;
                buttonScopuly.target = '_blank';
                buttonScopuly.className = 'button small text-small skynet-button';
                buttonScopuly.textContent = 'Scopuly';
                parentElement.appendChild(buttonScopuly);
            }

        } else {
            console.error('Заголовок актива не найден.');
        }
    } else {
        console.error('ID актива не найден.');
    }
}


function addBalancesFilter() {
    // Ищем H3 с текстом "Account Balances"
    const h3s = Array.from(document.querySelectorAll('h3'));
    const header = h3s.find(h => h.firstChild && String(h.firstChild.textContent || h.textContent).trim().startsWith('Account Balances'));
    if (!header) return;

    if (header.querySelector('.skynet-balance-filter')) return; // уже добавлен

    const wrap = document.createElement('span');
    wrap.style.marginLeft = '10px';

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'skynet-balance-filter';
    input.placeholder = 'фильтр по активу/issuer… (Enter)';
    input.title = 'Фильтр по коду/issuer. Нажмите Enter для применения, Esc — очистить.';
    input.style.cssText = 'font-size:12px;padding:3px 6px;min-width:280px;border-radius:6px;border:1px solid #ddd;';

    const hint = document.createElement('span');
    hint.className = 'text-tiny dimmed';
    hint.textContent = ' ⏎ для фильтра, Esc — сброс';
    hint.style.marginLeft = '6px';

    wrap.appendChild(input);
    wrap.appendChild(hint);
    header.appendChild(wrap);

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            filterBalances(input.value);
        } else if (e.key === 'Escape') {
            input.value = '';
            filterBalances('');
        }
    });
}

async function filterBalances(query) {
    const container = document.querySelector('.all-account-balances');
    if (!container) return;

    const q = (query || '').trim().toLowerCase();
    const showAll = () => {
        container.querySelectorAll('a.account-balance').forEach(c => { c.style.display = ''; });
    };

    if (!q) { showAll(); return; }

    // Проходим «пакетами»: скрываем по одной карточке и ждём кадр, чтобы движок дорисовал новые
    // Повторяем, пока на проходе есть изменения.
    let passes = 0;
    const MAX_PASSES = 200; // страховка от бесконечного цикла

    while (passes++ < MAX_PASSES) {
        let changed = false;

        const cards = Array.from(container.querySelectorAll('a.account-balance'));

        for (const card of cards) {
            // плейсхолдер/сырой шаблон — пропускаем, чтобы не мешать дорисовке
            const assetLink = card.querySelector('.asset-link');
            if (!assetLink) continue;

            const label = ((assetLink.getAttribute('aria-label') || '') + ' ' + (assetLink.textContent || '')).toLowerCase().trim();
            if (!label) continue; // ещё не заполнено — пропускаем

            const match = label.includes(q);
            const desiredDisplay = match ? '' : 'none';

            if (card.style.display !== desiredDisplay) {
                card.style.display = desiredDisplay;
                changed = true;

                // Дать странице время перерисовать и подложить следующую партию карточек.
                await new Promise(r => setTimeout(r, 10));
                break; // выходим из for, начнём новый проход по обновлённому DOM
            }
        }

        if (!changed) break; // на этом проходе ничего не менялось — стабилизировались
    }
}


async function initLiquidityPoolButton() {
    const poolId = new URL(window.location.href).pathname.split('/').pop();

    if (poolId) {
        const h2Elements = document.querySelectorAll('h2');
        let parentElement;
        for (let h2 of h2Elements) {
            const span = h2.querySelector('span.dimmed');
            if (span) {
                parentElement = h2;
                break;
            }
        }

        if (parentElement) {
            // Добавляем кнопку StellarX
            const buttonStellarX = document.createElement('a');
            buttonStellarX.href = '#';
            buttonStellarX.target = '_blank';
            buttonStellarX.className = 'button small text-small skynet-button';
            buttonStellarX.textContent = 'StellarX';
            parentElement.appendChild(buttonStellarX);

            // Загружаем данные о пуле
            try {
                const response = await fetch(`https://horizon.stellar.org/liquidity_pools/${poolId}`);
                const poolData = await response.json();

                if (poolData.reserves && poolData.reserves.length === 2) {
                    const [reserve1, reserve2] = poolData.reserves;

                    let stellarXUrl;
                    if (reserve1.asset === 'native') {
                        stellarXUrl = `https://www.stellarx.com/amm/analytics/native/${reserve2.asset}`;
                    } else if (reserve2.asset === 'native') {
                        stellarXUrl = `https://www.stellarx.com/amm/analytics/native/${reserve1.asset}`;
                    } else {
                        stellarXUrl = `https://www.stellarx.com/amm/analytics/${reserve1.asset}/${reserve2.asset}`;
                    }

                    buttonStellarX.href = stellarXUrl;
                }
            } catch (error) {
                console.error('Error fetching pool data:', error);
            }

            const buttonStellarchain = document.createElement('a');
            buttonStellarchain.href = `https://stellarchain.io/liquidity-pool/${poolId}`;
            buttonStellarchain.target = '_blank';
            buttonStellarchain.className = 'button small text-small skynet-button';
            buttonStellarchain.textContent = 'Stellarchain';
            parentElement.appendChild(buttonStellarchain);

            const buttonScopuly = document.createElement('a');
            buttonScopuly.href = `https://scopuly.com/pool/${poolId}`;
            buttonScopuly.target = '_blank';
            buttonScopuly.className = 'button small text-small skynet-button';
            buttonScopuly.textContent = 'Scopuly';
            parentElement.appendChild(buttonScopuly);

        } else {
            console.error('Заголовок пула ликвидности не найден.');
        }
    } else {
        console.error('ID пула ликвидности не найден.');
    }
}


function loadWhereSigner(accountAddress) {
    var myHtmlContent = '<h4 style="margin-bottom: 0px;">Where Account Signer</h4>';
    myHtmlContent += '<ul class="text-small condensed">';
    var url = 'https://horizon.stellar.org/accounts/?signer=' + accountAddress + '&limit=200';

    fetch(url)
        .then(response => response.json())
        .then(data => {
            data._embedded.records.forEach(record => {
                var accountId = record.id;
                myHtmlContent += '<li><a title="' + accountId + '" aria-label="' + accountId + '" class="account-address word-break" href="/explorer/public/account/' + accountId + '"><span class="account-key">' + accountId.slice(0, 4) + '…' + accountId.slice(-4) + '</span></a></li>';
            });
            myHtmlContent += '</ul>';

            // Ищем или создаем контейнер для содержимого
            var containerId = 'where-signer-container';
            var container = document.getElementById(containerId);
            if (!container) {
                container = document.createElement('div');
                container.id = containerId;
                var allAccountBalancesDiv = document.querySelector('.all-account-balances');
                if (allAccountBalancesDiv) {
                    // Вставляем контейнер перед элементом all-account-balances
                    allAccountBalancesDiv.parentNode.insertBefore(container, allAccountBalancesDiv);
                } else {
                    console.error('Element with class all-account-balances not found.');
                    return;
                }
            }

            // Обновляем содержимое контейнера
            container.innerHTML = myHtmlContent;
        })
        .catch(error => console.error('Error:', error));
}

function loadBSN(accountAddress) {
    var myHtmlContent = '<h4 style="margin-bottom: 0px;">BSN Income Tags</h4>';
    myHtmlContent += '<ul class="text-small condensed">';
    var url = 'https://bsn.expert/json';

    fetch(url)
        .then(response => response.json())
        .then(data => {
            var accounts = data.accounts;

            for (var accountId in accounts) {
                if (accounts.hasOwnProperty(accountId)) {
                    var account = accounts[accountId];
                    var tags = account.tags;

                    for (var tag in tags) {
                        if (tags.hasOwnProperty(tag) && tag !== 'Signer') {
                            if (tags[tag].includes(accountAddress)) {
                                myHtmlContent += '<li><b>' + tag + '</b> from ';
                                myHtmlContent += '<a title="' + accountId + '" aria-label="' + accountId + '" class="account-address word-break" href="/explorer/public/account/' + accountId + '"><span class="account-key">' + accountId.slice(0, 4) + '…' + accountId.slice(-4) + '</span></a></li>';
                            }
                        }
                    }
                }
            }

            myHtmlContent += '</ul>';

            // Ищем или создаем контейнер для содержимого BSN
            var containerId = 'bsn-income-tags-container';
            var container = document.getElementById(containerId);
            if (!container) {
                container = document.createElement('div');
                container.id = containerId;
                var allAccountBalancesDiv = document.querySelector('.all-account-balances');
                if (allAccountBalancesDiv) {
                    // Вставляем контейнер перед элементом all-account-balances
                    allAccountBalancesDiv.parentNode.insertBefore(container, allAccountBalancesDiv);
                } else {
                    console.error('Element with class all-account-balances not found.');
                    return;
                }
            }

            // Обновляем содержимое контейнера
            container.innerHTML = myHtmlContent;
        })
        .catch(error => console.error('Error:', error));
}


async function reloadScripts(accountAddress) {
    CalcOrders(accountAddress)
    modifyLinks();
    removeUnwantedElements();
    decodeBase64Text();
}

setInterval(checkPage, 3000);
