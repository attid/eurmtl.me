// ==UserScript==
// @name        Good_links_at_Stellar_Expert
// @namespace   http://tampermonkey.net/
// @match       https://stellar.expert/*
// @grant       none
// @version     1.11
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
    // Функция для проверки, является ли строка URL
    function isValidUrl(string) {
        try {
            new URL(string);
            return true;
        } catch (_) {
            return false;
        }
    }

    // Функция для создания HTML-ссылки
    function createLink(url) {
        const link = document.createElement('a');
        link.href = url;
        link.textContent = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer'; // Для безопасности
        return link;
    }

    let encodedListItems = document.querySelectorAll('.text-small.condensed .word-break');

    if (encodedListItems) {
        encodedListItems.forEach(item => {
            let separatorIndex = item.textContent.lastIndexOf(': ');
            if (separatorIndex > -1) {
                let property = item.textContent.substring(0, separatorIndex);
                let encodedText = item.textContent.substring(separatorIndex + 2);

                if (!item.hasAttribute('data-old')) {
                    item.setAttribute('data-old', encodedText);

                    if (isValidBase64(encodedText) && !encodedText.startsWith('*')) {
                        let decodedText = atob(encodedText);

                        // Очищаем содержимое элемента
                        item.textContent = property + ': ';

                        if (isValidStellarAddress(decodedText)) {
                            // Обработка Stellar-адреса
                            let link = document.createElement('a');
                            link.href = `https://stellar.expert/explorer/public/account/${decodedText}`;
                            link.textContent = decodedText;
                            link.target = '_blank';
                            item.appendChild(link);
                        } else if (isValidUrl(decodedText)) {
                            // Обработка URL
                            item.appendChild(createLink(decodedText));
                        } else {
                            // Поиск URL в тексте
                            const urlRegex = /(https?:\/\/[^\s]+)/g;
                            let lastIndex = 0;
                            let match;

                            while ((match = urlRegex.exec(decodedText)) !== null) {
                                // Добавляем текст до URL
                                if (match.index > lastIndex) {
                                    item.appendChild(document.createTextNode(
                                        decodedText.substring(lastIndex, match.index)
                                    ));
                                }

                                // Добавляем URL как ссылку
                                item.appendChild(createLink(match[0]));

                                lastIndex = match.index + match[0].length;
                            }

                            // Добавляем оставшийся текст
                            if (lastIndex < decodedText.length) {
                                item.appendChild(document.createTextNode(
                                    decodedText.substring(lastIndex)
                                ));
                            }
                        }
                    }
                }
            }
        });
    }
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
