function generateAccountSelector(fieldName = "sourceAccount", labelName = "Source Account (optional)") {
    return `
        <div class="form-group account-selector">
            <label for="${fieldName}">${labelName}</label>
            <div class="input-group">
                <input type="text" id="${fieldName}" class="${fieldName}" name="${fieldName}" maxlength="56" placeholder="Enter public key" required>
                <button type="button" class="fetchAccounts button secondary">⛰️</button>
                <button type="button" class="openAccounts button secondary">👁</button>
            </div>
            <div class="${fieldName}Dropdown dropdown-content"></div>
        </div>
    `;
}

function generateAssetSelector(fieldName = "asset", labelName = "Asset") {
    return `
        <div class="form-group account-selector">
            <label for="${fieldName}">${labelName}</label>
            <div class="input-group">
                <input type="text" id="${fieldName}" class="${fieldName}" name="${fieldName}" placeholder="Enter asset like XLM or MTL-ISSUER" required>
                <button type="button" class="fetchAssetMTL button secondary">⛰️</button>
                <button type="button" class="fetchAssetSrc button secondary">🔍</button>
                <button type="button" class="openAsset button secondary">👁</button>
            </div>
            <div class="${fieldName}Dropdown dropdown-content"></div>
        </div>
    `;
}

function generateOfferSelector(fieldName = "offer_id", labelName = "Offer ID") {
    return `
        <div class="form-group account-selector">
            <label for="${fieldName}">${labelName}</label>
            <div class="input-group">
                <input type="text" id="${fieldName}" class="${fieldName}" name="${fieldName}" placeholder="Choose offer id or set 0" required>
                <button type="button" class="fetchOffers button secondary">🔍</button>
            </div>
            <div class="${fieldName}Dropdown dropdown-content"></div>
                If 0, will create a new offer. Existing offer id numbers can be found using the Offers for Account endpoint.
        </div>
    `;
}


document.addEventListener('DOMContentLoaded', function() {
    let blockCounter = 0;

    document.querySelector("#add_operation").addEventListener('click', function() {
        let operationType = document.querySelector("#operation").value;

        let blockHTML = "";

        if (operationType === "create_account") {
            blockHTML = `
            <div class="operation-block create_account_block">
              <h4>Account Block #${blockCounter}</h4>

              ${generateAccountSelector("destination", "Destination")}

              <div class="form-group">
                <label for="startingBalance">Starting Balance</label>
                <input type="text" id="startingBalance" name="startingBalance">
              </div>

              ${generateAccountSelector("sourceAccount")}

              <button type="button" class="delete-block">Delete Block</button>
            </div>
          `;
        } else if (operationType === "payment") {
            blockHTML = `
                <div class="operation-block payment_block">
                    <h4>Payment Block #${blockCounter}</h4>

                    ${generateAccountSelector("destination", "Destination")}

                    ${generateAssetSelector("asset", "Asset")}

                    <div class="form-group">
                        <label for="amount">Amount</label>
                        <input type="text" id="amount" name="amount">
                    </div>

                    ${generateAccountSelector("sourceAccount")}

                    <button type="button" class="delete-block">Delete Block</button>
                </div>
            `;
        } else if (operationType === "change_trust") {
            blockHTML = `
                <div class="operation-block change_trust_block">
                    <h4>Change Trust Block #${blockCounter}</h4>

                    ${generateAssetSelector("asset", "Asset")}

                    <div class="form-group">
                        <label for="amount">Trust Limit (optional)</label>
                        <input type="text" id="amount" name="amount">
                        Leave empty to default to the max int64. <br>
                        Set to 0 to remove the trust line.
                    </div>

                    ${generateAccountSelector("sourceAccount")}

                    <button type="button" class="delete-block">Delete Block</button>
                </div>
            `;
        } else if (operationType === "options") {
            blockHTML = `
                <div class="operation-block options_block">
                    <h4>Set Options #${blockCounter}</h4>

                    <div class="form-group">
                        <label for="master">Master Weight (optional)</label>
                        <input type="text" id="master" name="master">
                        This can result in a permanently locked account. Are you sure you know what you are doing?
                    </div>

                    <div class="form-group">
                        <label for="threshold">Low/Medium/High Threshold (optional)</label>
                        <input type="text" id="threshold" name="threshold">
                        This can result in a permanently locked account. Are you sure you know what you are doing?
                    </div>

                    <div class="form-group">
                        <label for="home">Home Domain (optional)</label>
                        <input type="text" id="home" name="home">
                    </div>

                    ${generateAccountSelector("sourceAccount")}

                    <button type="button" class="delete-block">Delete Block</button>
                </div>
            `;
        } else if (operationType === "options_signer") {
            blockHTML = `
                <div class="operation-block options_signer_block">
                    <h4>Set Options Signer #${blockCounter}</h4>

                    ${generateAccountSelector("signerAccount", "Ed25519 Public Key (optional)")}

                    <div class="form-group">
                        <label for="weight">Signer Weight</label>
                        <input type="text" id="weight" name="weight">
                        Signer will be removed from account if this weight is 0. <br>
                        Used to add/remove or adjust weight of an additional signer on the account.
                    </div>

                    ${generateAccountSelector("sourceAccount")}

                    <button type="button" class="delete-block">Delete Block</button>
                </div>
            `;
        } else if (operationType === "buy") {
            blockHTML = `
                <div class="operation-block buy_block">
                    <h4>Buy Block #${blockCounter}</h4>

                    ${generateAssetSelector("buying", "Buying")}
                    ${generateAssetSelector("selling", "Selling")}

                    <div class="form-group">
                        <label for="amount">Amount you are buying</label>
                        <input type="text" id="amount" name="amount">
                        An amount of zero will delete the offer.
                    </div>

                    <div class="form-group">
                        <label for="price">Price of 1 unit of buying in terms of selling </label>
                        <input type="text" id="price" name="price">
                    </div>

                    ${generateOfferSelector()}

                    ${generateAccountSelector("sourceAccount")}

                    <button type="button" class="delete-block">Delete Block</button>
                </div>
            `;
        } else if (operationType === "sell") {
            blockHTML = `
                <div class="operation-block sell_block">
                    <h4>Buy Block #${blockCounter}</h4>

                    ${generateAssetSelector("selling", "Selling")}
                    ${generateAssetSelector("buying", "Buying")}

                    <div class="form-group">
                        <label for="amount">Amount you are selling</label>
                        <input type="text" id="amount" name="amount">
                        An amount of zero will delete the offer.
                    </div>

                    <div class="form-group">
                        <label for="price">Price of 1 unit of selling in terms of buying </label>
                        <input type="text" id="price" name="price">
                    </div>

                    ${generateOfferSelector()}

                    ${generateAccountSelector("sourceAccount")}

                    <button type="button" class="delete-block">Delete Block</button>
                </div>
            `;
        } else if (operationType === "manage_data") {
            blockHTML = `
                <div class="operation-block manage_data_block">
                    <h4>Manage Data Block #${blockCounter}</h4>

                    <div class="form-group account-selector">
                        <label for="data_name">Entry name </label>
                        <div class="input-group">
                            <input type="text" id="data_name" name="data_name" class="data_name">
                            <button type="button" class="fetchData button secondary">🔍</button>
                        </div>
                        <div class="data_nameDropdown dropdown-content"></div>
                    </div>

                    <div class="form-group">
                        <label for="data_value">Entry value (optional) </label>
                        <input type="text" id="data_value" name="data_value">
                        If empty, will delete the data entry named in this operation. <br>
                        Note: The laboratory only supports strings.
                    </div>

                    ${generateAccountSelector("sourceAccount")}

                    <button type="button" class="delete-block">Delete Block</button>
                </div>
            `;
        }


        // Вставляем перед кнопкой "Add Operation"
        document.querySelector(".new-operation").insertAdjacentHTML('beforebegin', blockHTML);
        blockCounter++;
    });

    document.body.addEventListener('click', function(event) {
        if (event.target) {
            // Если клик был по элементу .account-item
            if (event.target.classList.contains('account-item')) {
                let accountSelector = event.target.closest('.account-selector');
                let fieldName = accountSelector.querySelector("input").getAttribute('name');
                accountSelector.querySelector("input").value = event.target.getAttribute('data-account');

                // Здесь мы используем динамическое имя для выбора правильного выпадающего списка
                let dropdown = accountSelector.querySelector(`.${fieldName}Dropdown`);
                dropdown.style.display = 'none';
                dropdown.innerHTML = "";
            }

            // Для кнопки "Delete Block"
            if (event.target.classList.contains('delete-block')) {
                event.target.closest('.operation-block').remove();
            }

            // Если клик был по кнопке .fetchSequence
            if (event.target.classList.contains('loadsSequence')) {
                let publicKey = document.querySelector(".publicKey").value;
                if (publicKey.length !== 56) {
                    alert("Please choose a publicKey");
                    return;
                }

                fetch(`/lab/sequence/${publicKey}`)
                    .then(response => {
                        if (!response.ok) {
                            throw new Error("Network response was not ok");
                        }
                        return response.json();
                    })
                    .then(data => {
                        document.querySelector("#sequence_number").value = data.sequence;
                    })
                    .catch(error => {
                        console.log("There was a problem with the fetch operation:", error.message);
                    });
            }

            // Для fetchAssetSrc
            if (Array.from(event.target.classList).some(className => /^fetch/.test(className))) {
                let fieldName = event.target.closest('.account-selector').querySelector('input').className;
                let dropdown = event.target.closest('.account-selector').querySelector(`.${fieldName}Dropdown`);
                // Если выпадающий список уже отображается, скрываем его
                if (dropdown.style.display === 'block') {
                    dropdown.style.display = 'none';
                } else {
                    let publicKey = document.querySelector(".publicKey").value;
                    let need_key = ['fetchAssetSrc', 'fetchData', 'fetchOffers']
                    if (Array.from(event.target.classList).some(className => need_key.includes(className))) {
                        if (publicKey.length !== 56) {
                            alert("Please choose a publicKey");
                            return;
                        }
                        let operationBlock = event.target.closest('.operation-block');
                        let sourceAccountInput = operationBlock.querySelector('.sourceAccount');

                        if (sourceAccountInput && sourceAccountInput.value.length === 56) {
                            publicKey = sourceAccountInput.value;
                        }
                    }

                    let urls = {
                        'fetchAssetSrc': `/lab/assets/${publicKey}`,
                        'fetchData': `/lab/data/${publicKey}`,
                        'fetchOffers': `/lab/offers/${publicKey}`,
                        'fetchAssetMTL': '/lab/mtl_assets',
                        'fetchAccounts': '/lab/mtl_accounts'
                    };

                    let fetchURL;
                    for (let className in urls) {
                        if (event.target.classList.contains(className)) {
                            fetchURL = urls[className];
                            break;
                        }
                    }

                    if (fetchURL) {
                        fetch(fetchURL)
                            .then(response => response.json())
                            .then(data => {
                                let dropdownContent = "";
                                for (let name in data) {
                                    dropdownContent += `<div class="account-item" data-account="${data[name]}">${name}</div>`;
                                }
                                dropdown.innerHTML = dropdownContent;
                                dropdown.style.display = 'block';
                            });
                    } else {
                        console.error("Invalid fetchURL");
                    }
                }
            }

            // Для fetchAssetSrc
            if (event.target.classList.contains('openAccounts') || event.target.classList.contains('openAsset')) {
                let accountSelector = event.target.closest('.account-selector');
                let input = accountSelector.querySelector('input');
                let publicKey = input.value;

                // Проверяем длину публичного ключа
                if (publicKey.length < 56) {
                    alert("Please choose or enter key");
                    return;
                }

                // Открываем новое окно с заданным URL
                if (event.target.classList.contains('openAccounts')){
                    window.open(`https://stellar.expert/explorer/public/account/${publicKey}`, '_blank');
                }
                // Открываем новое окно с заданным URL
                if (event.target.classList.contains('openAsset')){
                    window.open(`https://stellar.expert/explorer/public/asset/${publicKey}`, '_blank');
                }
            }


            if (event.target.classList.contains('get_xdr')) {
                const data = gatherData();

                fetch("/lab/build_xdr", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(data)
                })
                .then(response => {
                    // Убедитесь, что ответ содержит JSON
                    if (!response.ok) {
                        throw new Error("Network response was not ok");
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.xdr) {
                        // Вставляем XDR в нужный элемент
                        document.querySelector('.tx-body').textContent = data.xdr;
                    } else if (data.error) {
                        // Показываем алерт с сообщением об ошибке
                        alert(data.error);
                    } else {
                        // Показываем общее сообщение об ошибке, если нет xdr или error
                        alert("Cant get XDR =(");
                    }
                })
                .catch(error => {
                    // Обработка ошибок сети или других ошибок запроса
                    alert("An error occurred: " + error.message);
                });
            }
        }



    });

});

function gatherData() {
    const blocks = document.querySelectorAll('.operation-block');
    let data = {};
    let operations = [];
    data['publicKey'] = document.querySelector(".publicKey").value;
    data['sequence'] = document.querySelector(".sequence_number").value;
    data['memo_type'] = document.querySelector(".memo_type").value;
    data['memo'] = document.querySelector(".memo").value;

    blocks.forEach((block, index) => {
        if (block.classList.contains('payment_block')) {
            let blockData = {
                type: 'payment',
                destination: block.querySelector('input[name="destination"]').value,
                asset: block.querySelector('input[name="asset"]').value,
                amount: block.querySelector('input[name="amount"]').value,
                sourceAccount: block.querySelector('input[name="sourceAccount"]').value
            };
            operations.push(blockData);
        }
        if (block.classList.contains('change_trust_block')) {
            let blockData = {
                type: 'change_trust',
                asset: block.querySelector('input[name="asset"]').value,
                amount: block.querySelector('input[name="amount"]').value,
                sourceAccount: block.querySelector('input[name="sourceAccount"]').value
            };
            operations.push(blockData);
        }
        if (block.classList.contains('options_block')) {
            let blockData = {
                type: 'options',
                master: block.querySelector('input[name="master"]').value,
                threshold: block.querySelector('input[name="threshold"]').value,
                home: block.querySelector('input[name="home"]').value,
                sourceAccount: block.querySelector('input[name="sourceAccount"]').value
            };
            operations.push(blockData);
        }
        if (block.classList.contains('options_signer_block')) {
            let blockData = {
                type: 'options_signer',
                signerAccount: block.querySelector('input[name="signerAccount"]').value,
                weight: block.querySelector('input[name="weight"]').value,
                sourceAccount: block.querySelector('input[name="sourceAccount"]').value
            };
            operations.push(blockData);
        }
        if (block.classList.contains('create_account_block')) {
            let blockData = {
                type: 'create_account',
                destination: block.querySelector('input[name="destination"]').value,
                startingBalance: block.querySelector('input[name="startingBalance"]').value,
                sourceAccount: block.querySelector('input[name="sourceAccount"]').value
            };
            operations.push(blockData);
        }
        if (block.classList.contains('buy_block')) {
            let blockData = {
                type: 'buy',
                buying: block.querySelector('input[name="buying"]').value,
                selling: block.querySelector('input[name="selling"]').value,
                amount: block.querySelector('input[name="amount"]').value,
                price: block.querySelector('input[name="price"]').value,
                offer_id: block.querySelector('input[name="offer_id"]').value,
                sourceAccount: block.querySelector('input[name="sourceAccount"]').value
            };
            operations.push(blockData);
        }
        if (block.classList.contains('sell_block')) {
            let blockData = {
                type: 'sell',
                buying: block.querySelector('input[name="buying"]').value,
                selling: block.querySelector('input[name="selling"]').value,
                amount: block.querySelector('input[name="amount"]').value,
                price: block.querySelector('input[name="price"]').value,
                offer_id: block.querySelector('input[name="offer_id"]').value,
                sourceAccount: block.querySelector('input[name="sourceAccount"]').value
            };
            operations.push(blockData);
        }
        if (block.classList.contains('manage_data_block')) {
            let blockData = {
                type: 'manage_data',
                data_name: block.querySelector('input[name="data_name"]').value,
                data_value: block.querySelector('input[name="data_value"]').value,
                sourceAccount: block.querySelector('input[name="sourceAccount"]').value
            };
            operations.push(blockData);
        }

    });

    data['operations'] = operations;

    return data;
}