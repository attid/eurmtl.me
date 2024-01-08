var globalCash = {}; // Глобальный словарь для хранения данных запросов
var blockCounter = 0;

function deleteBlock(element) {
    $(element).closest('.card').remove();
}

function viewAccount(element) {
    var destinationValue = $(element).closest('.row').find('.account-input').val().trim();

    if (destinationValue.length === 56) {
        window.open('https://stellar.expert/explorer/public/account/' + destinationValue, '_blank');
    } else {
        M.toast({html: 'Адрес должен содержать 56 символов', classes: 'rounded'});
    }
}

function viewAsset(element) {
    var destinationValue = $(element).closest('.row').find('.account-input').val().trim();

    if (destinationValue.length > 2) {
        window.open('https://stellar.expert/explorer/public/asset/' + destinationValue, '_blank');
    } else {
        M.toast({html: 'Ассет не выбран', classes: 'rounded'});
    }
}

function getSourceKey(buttonElement){
    var $button = $(buttonElement);
    var $inputField = $button.closest('.account-selector');
    var sourceAccount = $inputField.find('.sourceAccount').val();
    var publicKey = $('[id^="publicKey-"]').val();


    var keyToUse = sourceAccount && sourceAccount.length === 56 ? sourceAccount : (publicKey.length === 56 ? publicKey : null);

    if (!keyToUse) {
        M.toast({html: 'Please provide a valid publicKey or sourceAccount', classes: 'rounded'});
        return;
    }
    return keyToUse;
}

function fetchDataAndShowDropdown(url, globalDataVarKey, $inputField, $input) {
    if (!window.globalCash[globalDataVarKey]) {
        M.toast({html: 'Подождите идет загрузка', classes: 'rounded'});
        $.ajax({
            url: url,
            type: 'GET',
            success: function(response) {
                window.globalCash[globalDataVarKey] = response; // Сохраняем данные в глобальном объекте
                showDropdown($inputField, $input, response);
            },
            error: function() {
                console.error('Не удалось получить данные');
            }
        });
    } else {
        showDropdown($inputField, $input, window.globalCash[globalDataVarKey]);
    }
}

function fetchAccounts(buttonElement) {
    var $button = $(buttonElement);
    var $inputField = $button.closest('.input-field');
    var $input = $inputField.find('input');

    fetchDataAndShowDropdown('/lab/mtl_accounts', 'accountsMTL', $inputField, $input);
}

function fetchAssetsMTL(buttonElement) {
    var $button = $(buttonElement);
    var $inputField = $button.closest('.input-field');
    var $input = $inputField.find('input');

    fetchDataAndShowDropdown('/lab/mtl_assets', 'assetsMTL', $inputField, $input);
}

function fetchAssetsSrc(buttonElement) {
    var keyToUse = getSourceKey(buttonElement);
    if (!keyToUse) {
        return;
    }

    var $button = $(buttonElement);
    var $inputField = $button.closest('.input-field');
    var $input = $inputField.find('input');

    fetchDataAndShowDropdown(`/lab/assets/${keyToUse}`, keyToUse, $inputField, $input);
}


function showDropdown($inputField, $input, accounts) {
    var dropdownId = 'dropdown-' + new Date().getTime();
    var $dropdown = $('<ul>').addClass('dropdown-content').attr('id', dropdownId);

    $.each(accounts, function(name, address) {
        var $li = $('<li>').append($('<span>').text(name));
        $li.on('click', function() {
            // Установка значения выбранного элемента в инпут
            $input.val(address);
            // Закрытие выпадающего списка
            var instance = M.Dropdown.getInstance($input[0]);
            if (instance) {
                instance.close();
                instance.destroy();
            }
        });
        $dropdown.append($li);
    });

    $inputField.find('.dropdown-content').remove();
    $inputField.append($dropdown);

    // Устанавливаем data-target для инпута и добавляем класс dropdown-trigger
    $input.attr('data-target', dropdownId).addClass('dropdown-trigger');

    // Инициализируем выпадающий список с обратным вызовом onCloseEnd
    M.Dropdown.init($input[0], {
        coverTrigger: false,
        onCloseEnd: function() {
            var instance = M.Dropdown.getInstance($input[0]);
            if (instance) {
                instance.destroy();
            }
            // Удаляем класс dropdown-trigger у инпута
            $input.removeClass('dropdown-trigger');
        }
    });
    // Открываем выпадающий список
    var instance = M.Dropdown.getInstance($input[0]);
    instance.open();
}

function get_uid(){
    return new Date().getTime();
}

function generateAccountSelector(fieldName = "sourceAccount",
                                 labelName = "Source Account (optional)",
                                 fieldValue = "") {
    var uid = get_uid();
    var validation = fieldName === "sourceAccount" ? 'data-validation="account_null"' : 'data-validation="account"';
    return `
<!-- Account -->
<div class="row input-field">
    <div class="input-field col s10">
        <input type="text" class="validate account-input" data-length="56" data-type="${fieldName}" ${validation}
            value="${fieldValue}" id="${fieldName}-${uid}">
        <label for="${fieldName}-${uid}">${labelName}</label>
    </div>
    <div class="col s1">
        <button type="button" class="btn-floating waves-effect waves-light tooltipped"
            data-position="bottom" data-tooltip="Выбрать из списка" onclick="fetchAccounts(this)">
            <i class="material-icons">terrain</i>
        </button>
    </div>
    <div class="col s1">
        <button type="button" class="btn-floating waves-effect waves-light tooltipped"
            data-position="bottom" data-tooltip="Просмотреть в эксперте" onclick="viewAccount(this)">
            <i class="material-icons">visibility</i>
        </button>
    </div>
</div>
    `;
}

function generateAssetSelector(fieldName = "asset",
                                 labelName = "Asset",
                                 fieldValue = "") {
    var uid = get_uid();
    return `
<!-- Account -->
<div class="row input-field">
    <div class="input-field col s9">
        <input type="text" class="validate account-input" data-type="${fieldName}" data-validation="asset"
            value="${fieldValue}" id="${fieldName}-${uid}">
        <label for="${fieldName}-${uid}">${labelName}</label>
    </div>
    <div class="col s1">
        <button type="button" class="btn-floating waves-effect waves-light tooltipped"
            data-position="bottom" data-tooltip="Выбрать из списка" onclick="fetchAssetsMTL(this)">
            <i class="material-icons">terrain</i>
        </button>
    </div>
    <div class="col s1">
        <button type="button" class="btn-floating waves-effect waves-light tooltipped"
            data-position="bottom" data-tooltip="Выбрать из трастлайнов аккаунта" onclick="fetchAssetsSrc(this)">
            <i class="material-icons">search</i>
        </button>
    </div>
    <div class="col s1">
        <button type="button" class="btn-floating waves-effect waves-light tooltipped"
            data-position="bottom" data-tooltip="Просмотреть в эксперте" onclick="viewAsset(this)">
            <i class="material-icons">visibility</i>
        </button>
    </div>
</div>
    `;
}

function generateOfferSelector(fieldName = "offer_id", labelName = "Offer ID", fieldValue = "") {
    var uid = get_uid();
    return `
<div class="row input-field">
    <div class="input-field col s10">
        <input type="text" class="validate" id="${fieldName}-${uid}" value="${fieldValue}"
            data-type="${fieldName}" data-validation="int">
        <label for="${fieldName}-${uid}">${labelName}</label>
        <span class="helper-text">If 0, will create a new offer. Existing offer id numbers can be found using the Offers for Account endpoint.</span>
    </div>
    <div class="col s2">
        <button type="button" class="btn-floating waves-effect waves-light tooltipped"
            data-position="bottom" data-tooltip="Fetch Offers" onclick="fetchOffers(this)">
            <i class="material-icons">search</i>
        </button>
    </div>
</div>
    `;
}

function generateInput(fieldName = "amount", labelName = "Amount", validation, fieldValue = "", helperText = "") {
    var uid = get_uid();
    var fullId = `${fieldName}-${uid}`;
    var onInputAttribute = '';

    if (validation === 'float_trade') {
        onInputAttribute = `oninput="calculateFinalCost(this)"`;
    }

    return `
<div class="row input-field">
    <div class="input-field col s10">
        <input id="${fullId}" type="text" class="validate" data-type="${fieldName}"
            data-validation="${validation}" value="${fieldValue}" ${onInputAttribute}>
        <label for="${fullId}">${labelName}</label>
        ${helperText ? `<span class="helper-text">${helperText}</span>` : ""}
    </div>
</div>
    `;
}

function fetchOffers(buttonElement) {
    var keyToUse = getSourceKey(buttonElement);
    if (!keyToUse) {
        return;
    }

    var $button = $(buttonElement);
    var $inputField = $button.closest('.input-field');
    var $input = $inputField.find('input');

    fetchDataAndShowDropdown(`/lab/offers/${keyToUse}`, 'offers'+keyToUse, $inputField, $input);
}

function fetchDataEntry(buttonElement) {
    var keyToUse = getSourceKey(buttonElement);
    if (!keyToUse) {
        return;
    }

    var $button = $(buttonElement);
    var $inputField = $button.closest('.input-field');
    var $input = $inputField.find('input');

    fetchDataAndShowDropdown(`/lab/data/${keyToUse}`, 'data'+keyToUse, $inputField, $input);
}

function generatePathSelector(fieldName = "path", labelName = "Path") {
    var uid = get_uid();
    return `
<div class="row input-field">
    <div class="input-field col s10">
        <input type="text" class="validate" data-type="${fieldName}" id="${fieldName}-${uid}" placeholder="Choose path" required>
        <label for="${fieldName}-${uid}">${labelName}</label>
    </div>
    <div class="col s2">
        <button type="button" class="btn-floating waves-effect waves-light tooltipped"
            data-position="bottom" data-tooltip="Fetch Path" onclick="fetchPath(this, '${fieldName}-${uid}')">
            <i class="material-icons">search</i>
        </button>
    </div>
</div>
    `;
}

function fetchPath0(buttonElement, pathFieldId) {
    var $button = $(buttonElement);
    var $inputField = $button.closest('.input-field');
    var $pathInput = $('#' + pathFieldId);

    var sellingAsset = $('.selling').val() || 0;
    var buyingAsset = $('.buying').val() || 0;
    var amount = $('.amount').val() || 0;
    var publicKey = `${sellingAsset}/${buyingAsset}/${amount}`;

    fetchDataAndShowDropdown(`/lab/path/${publicKey}`, 'path'+publicKey, $inputField, $pathInput);
}

function fetchPath(buttonElement, pathFieldId) {
    var $button = $(buttonElement);
    var $inputField = $button.closest('.input-field'); // Возвращаем это значение
    var $operationBlock = $button.closest('.card-content');

    var sellingAsset = $operationBlock.find('[data-type="selling"]').val() || 0;
    var buyingAsset = $operationBlock.find('[data-type="buying"]').val() || 0;
    var amount = $operationBlock.find('[data-type="amount"]').val() || 0;
    var publicKey = `${sellingAsset}/${buyingAsset}/${amount}`;

    fetchDataAndShowDropdown(`/lab/path/${publicKey}`, 'path'+publicKey, $inputField, $('#' + pathFieldId));
}

function getBlockCounter() {
    return blockCounter++;
}

function generateCardHeader(cardName, blockId) {
    return `
        <div class="row">
            <span class="card-title col s8">${cardName} Block #${blockId}</span>
            <button class="btn waves-effect waves-light col s2" onclick="cloneBlock(this)">Clone</button>
            <button class="btn waves-effect waves-light col s2 red" onclick="deleteBlock(this)">Delete Block</button>
        </div>
    `;
}

function generateCardFirst() {
    return `
<div class="card" id="firstCard">
    <div class="card-content">
        ${generateAccountSelector("publicKey", "PublicKey")}

        <!-- Memo type and input -->
        <div class="row">
            <div class="input-field col s12">
                <select id="memo_type" name="memo_type" onchange="updateMemoField()">
                    <option value="none" selected>None</option>
                    <option value="memo_text">Text</option>
                    <option value="memo_hash">Hash</option>
                </select>
                <label for="memo_type">Memo Type</label>
            </div>
        </div>

        <div class="row">
            <div class="input-field col s12" id="memo-input-field" style="display: none;">
                <input type="text" id="memo" name="memo" class="validate" data-length="10">
                <label for="memo">Memo</label>
            </div>
        </div>
    </div>
</div>
    `;
}

function generateCardPayment() {
    var uid = get_uid();
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="payment" data-index="${blockId}">
        ${generateCardHeader("Payment", blockId)}

        ${generateAccountSelector("destination", "Destination")}
        ${generateAssetSelector("asset", "Asset")}
        ${generateInput("amount", "Amount", "float")}
        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}

function generateCardTrustPayment() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="trust_payment" data-index="${blockId}">
        ${generateCardHeader("Trust Payment", blockId)}
        ${generateAccountSelector("destination", "Destination")}
        ${generateAssetSelector("asset", "Asset")}
        ${generateInput("amount", "Amount", "float")}

        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}

function generateCardChangeTrust() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="change_trust" data-index="${blockId}">
        ${generateCardHeader("Change Trust", blockId)}
        ${generateAssetSelector("asset", "Asset")}

        ${generateInput("limit", "Trust Limit (optional)", "float_null", "",
            "Leave empty to default to the max int64. Set to 0 to remove the trust line.")}

        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}

function generateCardBuy() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="buy" data-index="${blockId}">
        ${generateCardHeader("Buy", blockId)}
        ${generateAssetSelector("buying", "Buying")}
        ${generateAssetSelector("selling", "Selling")}

        ${generateInput("amount", "Amount you are buying (zero to delete offer)", "float_trade")}
        ${generateInput("price", "Price per unit (buying in terms of selling)", "float_trade","","Тут будет расчет получаемого")}

        ${generateOfferSelector()}

        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}

function generateCardSell() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="sell" data-index="${blockId}">
        ${generateCardHeader("Sell", blockId)}
        ${generateAssetSelector("selling", "Selling")}
        ${generateAssetSelector("buying", "Buying")}

        ${generateInput("amount", "Amount you are selling (zero to delete offer)", "float_trade")}
        ${generateInput("price", "Price per unit (buying in terms of selling)", "float_trade","","Тут будет расчет получаемого")}

        ${generateOfferSelector()}

        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}

function generateCardSellPassive() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="sell_passive" data-index="${blockId}">
        ${generateCardHeader("Sell Passive", blockId)}
        ${generateAssetSelector("selling", "Selling")}
        ${generateAssetSelector("buying", "Buying")}

        ${generateInput("amount", "Amount you are selling (zero to delete offer)", "float_trade")}
        ${generateInput("price", "Price per unit (buying in terms of selling)", "float_trade","","Тут будет расчет получаемого")}

        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}

function generateCardCreateAccount() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="create_account" data-index="${blockId}">
        ${generateCardHeader("Create Account", blockId)}
        ${generateAccountSelector("destination", "Destination")}

        ${generateInput("startingBalance", "Starting Balance", "float")}

        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}

function generateCardManageData() {
    var blockId = getBlockCounter();
    var uid = get_uid();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="manage_data" data-index="${blockId}">
        ${generateCardHeader("Manage Data", blockId)}

        <div class="row">
            <div class="input-field col s10">
                <input id="data_name-${uid}" type="text" class="validate" data-length="64"
                    data-type="data_name" data-validation="text_null">
                <label for="data_name-${uid}">Entry Name</label>
            </div>
            <div class="col s2">
                <button type="button" class="btn-floating waves-effect waves-light tooltipped"
                    data-position="bottom" data-tooltip="Fetch Data" onclick="fetchDataEntry(this)">
                    <i class="material-icons">search</i>
                </button>
            </div>
        </div>

        <div class="row">
            <div class="input-field col s10">
                <input id="data_value-${uid}" type="text" class="validate" data-length="64"
                    data-type="data_value" data-validation="text_null">
                <label for="data_value-${uid}">Entry Value (optional)</label>
                <span class="helper-text">If empty, will delete the data entry named in this operation. Note: Only supports strings.</span>
            </div>
        </div>

        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}

function generateCardSetOption() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="set_options" data-index="${blockId}">
        ${generateCardHeader("Set Options", blockId)}

        ${generateInput("master", "Master Weight (optional)", "int",  "",
            "This can result in a permanently locked account. Are you sure you know what you are doing?")}
        ${generateInput("threshold", "Low/Medium/High Threshold (optional)", "int",  "",
            "This can result in a permanently locked account. Are you sure you know what you are doing?")}
        ${generateInput("home", "Home Domain (optional)", "text_null")}

        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}

function generateCardSetOptionSigner() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="set_options_signer" data-index="${blockId}">
        ${generateCardHeader("Set Options Signer", blockId)}

        ${generateAccountSelector("signerAccount", "Ed25519 Public Key (optional)")}

        ${generateInput("weight", "Signer Weight", "int",  "",
            "Signer will be removed from account if this weight is 0. Used to add/remove or adjust weight of an additional signer on the account.")}

        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}


function generateCardClawback() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="clawback" data-index="${blockId}">
        ${generateCardHeader("Clawback", blockId)}

        ${generateAssetSelector("asset", "Asset")}
        ${generateAccountSelector("from", "From")}
        ${generateInput("amount", "Amount", "float")}

        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}

function generateCardCopyMultiSign() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="copy_multi_sign" data-index="${blockId}">
        ${generateCardHeader("Copy Multi Sign", blockId)}

        ${generateAccountSelector("from", "From")}
        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}

function generateCardSwap() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-content gather-block" data-type="swap" data-index="${blockId}">
        ${generateCardHeader("Swap", blockId)}

        ${generateAssetSelector("selling", "Selling")}
        ${generateAssetSelector("buying", "Buying")}

        ${generateInput("amount", "Amount you are swap", "float")}
        ${generateInput("destination", "Minimum destination amount", "float")}

        ${generatePathSelector("path", "Path")}

        ${generateAccountSelector("sourceAccount")}
    </div>
</div>
    `;
}

function getCardByName(selectedOperation){
    var newCardHTML;

    switch (selectedOperation) {
        case 'payment':
            newCardHTML = generateCardPayment();
            break;
        case 'trust_payment':
            newCardHTML = generateCardTrustPayment();
            break;
        case 'change_trust':
        case 'changeTrust':
            newCardHTML = generateCardChangeTrust();
            break;
        case 'buy':
        case 'manageBuyOffer':
            newCardHTML = generateCardBuy();
            break;
        case 'sell':
        case 'manageSellOffer':
            newCardHTML = generateCardSell();
            break;
        case 'sell_passive':
        case 'sellPassive':
        case 'createPassiveSellOffer':
            newCardHTML = generateCardSellPassive();
            break;
        case 'create_account':
        case 'createAccount':
            newCardHTML = generateCardCreateAccount();
            break;
        case 'manage_data':
        case 'manageData':
                newCardHTML = generateCardManageData();
            break;
        case 'options':
        case 'setOptions':
        case 'set_options':
            newCardHTML = generateCardSetOption();
            break;
        case 'options_signer':
        case 'setOptionsSigner':
        case 'set_options_signer':
                newCardHTML = generateCardSetOptionSigner();
            break;
        case 'clawback':
            newCardHTML = generateCardClawback();
            break;
        case 'copy_multi_sign':
        case 'CopyMultiSign':
            newCardHTML = generateCardCopyMultiSign();
            break;
        case 'swap':
            newCardHTML = generateCardSwap();
            break;

        default:
            M.toast({html: `Can't find selectedOperation ${selectedOperation} =(`, classes: 'rounded'});
            return;
    }
    return newCardHTML;
}


function addOperation() {
    var selectedOperation = $('#operation').val();
    var newCardHTML = getCardByName(selectedOperation);


    if (newCardHTML) {
        var $newCard = $(newCardHTML).hide(); // Изначально скрываем карточку
        $('.new-operation').before($newCard);
        $newCard.fadeIn(); // Плавное появление карточки

        $newCard.find('input[data-length]').characterCounter();
    }

    // Сброс выбора в выпадающем списке
    $('#operation').val('');
}

function updateMemoField() {
    var $memoField = $('#memo');
    var selectedOperation = $('#memo_type').val();
    var maxLength = selectedOperation === 'memo_text' ? 28 : (selectedOperation === 'memo_hash' ? 32 : 0);

    if (selectedOperation === 'none') {
        $('#memo-input-field').hide();
    } else {
        $('#memo-input-field').show();
        $memoField.attr('data-length', maxLength);
        $memoField.characterCounter();
    }
}

function handleXDR() {
    var data = gatherData();
    if (!data) {
        return;
    }

    $.ajax({
        url: "/lab/build_xdr",
        type: "POST",
        contentType: "application/json",
        data: JSON.stringify(data),
        success: function(response) {
            if (response.xdr) {
                $('.tx-body').text(response.xdr);
                M.toast({html: 'XDR successfully received', classes: 'rounded'});
            } else if (response.error) {
                M.toast({html: response.error, classes: 'rounded'});
            } else {
                M.toast({html: "Can't get XDR =(", classes: 'rounded'});
            }
        },
        error: function(xhr, status, error) {
            M.toast({html: "An error occurred: " + error, classes: 'rounded'});
        }
    });
}

function validateInput(value, validationType, dataType, type, index) {
    switch(validationType) {
        case 'account':
            if (value.trim().length !== 56) {
                throw new Error(`Неверная длина для ${dataType} в блоке ${type} #${index}`);
            }
            break;
        case 'account_null':
            if (value && value.trim().length !== 56) {
                throw new Error(`Неверная длина для ${dataType} в блоке ${type} #${index}`);
            }
            break;
        case 'asset':
            if (value !== "XLM" && !/^[A-Za-z0-9]+-[A-Za-z0-9]+$/.test(value)) {
                    throw new Error(`Неверный формат для ${dataType} в блоке ${type} #${index}`);
            }
            break;
        case 'int':
            if (!/^\d+$/.test(value)) {
                throw new Error(`Не целое число для ${dataType} в блоке ${type} #${index}`);
            }
            break;
        case 'float':
        case 'float_trade':
            value = value.replace(',', '.');
            if (isNaN(parseFloat(value))) {
                throw new Error(`Не число с плавающей точкой для ${dataType} в блоке ${type} #${index}`);
            }
            break;
        case 'float_null':
            if (value) {
                value = value.replace(',', '.');
                if (isNaN(parseFloat(value))) {
                    throw new Error(`Не число с плавающей точкой для ${dataType} в блоке ${type} #${index}`);
                }
            }
            break;
        case 'text':
            if (!value.trim()) {
                throw new Error(`Текст не может быть пустым для ${dataType} в блоке ${type} #${index}`);
            }
            break;
        case 'text_null':
            // Нет дополнительной проверки, так как может быть пустым
            break;
        default:
            throw new Error(`Неизвестный тип валидации: ${validationType}`);
    }
    return value;    
}

function gatherData() {
    let data = {};
    let operations = [];

    // Кэширование селекторов
    let publicKeyInput = $('[id^="publicKey-"]');
    data['publicKey'] = publicKeyInput.val();

    if (data['publicKey'].trim().length !== 56) {
        M.toast({html: `Неверная длина для publicKey !`, classes: 'rounded'});
        return;
    }

    data['memo_type'] = $('#memo_type').val();
    data['memo'] = $('#memo').val();

    try {
        $('.gather-block').each(function() {
            let block = $(this);
            let blockData = {};
            let type = block.data('type');
            let index = block.data('index');
            blockData['type'] = type;

            block.find('[data-validation]').each(function() {
                let input = $(this);
                let dataType = input.data('type');
                let value = input.val();
                let validation = input.data('validation');

                value = validateInput(value, validation, dataType, type, index);
                blockData[dataType] = value;
            });

            operations.push(blockData);
        });
    } catch (error) {
        M.toast({html: error.message, classes: 'rounded'});
        return;
    }

    if (operations.length === 0) {
        return;
    }

    data['operations'] = operations;
    return data; // Возвращает собранные данные
}

function cloneBlock(element) {
    let originalBlock = $(element).closest('.card');
    let cardContent = originalBlock.find('.card-content');
    let dataType = cardContent.data('type'); // Получаем data-type из card-content
    let newBlockHTML = getCardByName(dataType); // Генерируем HTML нового блока

    if (!newBlockHTML) {
        return; // Если нет соответствующего HTML, пропускаем итерацию
    }

    let newBlock = $(newBlockHTML);

    // Копируем значения всех input из оригинального блока в новый, используя data-type
    originalBlock.find('input').each(function() {
        let dataType = $(this).data('type');
        let value = $(this).val();
        newBlock.find(`input[data-type="${dataType}"]`).val(value);
    });

    // Вставляем новый блок перед элементом с классом "new-operation"
    $('.new-operation').before(newBlock.fadeIn());

    // Обновляем поля и выпадающие списки
    M.updateTextFields();
}

$(document).ready(function() {
    var newCardHTML = generateCardFirst();
    var $newCard = $(newCardHTML); // Преобразование HTML строки в jQuery объект
    $('.new-operation').before($newCard);
    $('select').formSelect();

    // Теперь $newCard является jQuery объектом, и вы можете использовать .find()
    $newCard.find('input[data-length]').characterCounter();
});

function toCamelCase(str) {
    return str.replace(/(_\w)/g, function(m) {
        return m[1].toUpperCase();
    });
}

function processOperations(jsonData) {
    jsonData.operations.forEach((op) => {
        var blockHTML = getCardByName(op.name);
        if (!blockHTML) {
            return; // Если нет соответствующего HTML, пропускаем итерацию
        }

        let $block = $(blockHTML);
        $block.find('input').each(function() {
            let dataType = $(this).data('type');
            let camelCaseDataType = toCamelCase(dataType);

            // Обработка поля asset
            if (dataType.toLowerCase().includes('asset') ||
                dataType.toLowerCase().includes('buying') ||
                dataType.toLowerCase().includes('selling')) {
                    let asset = op.attributes[camelCaseDataType];
                    let value = '';

                    if (asset && asset.type === 'native') {
                        value = 'XLM';
                    } else if (asset) {
                        value = `${asset.code}-${asset.issuer}`;
                    }

                $(this).val(value);
            } else if (op.attributes.hasOwnProperty(camelCaseDataType)) {
                let value = op.attributes[camelCaseDataType];
                $(this).val(value);
            }
        });

        $block.hide();
        $('.new-operation').before($block);
        $block.fadeIn();
        $block.find('input[data-length]').characterCounter();
    });
    M.updateTextFields();
}

function importOperations() {
    // Получаем XDR из текстового поля
    var xdrText = $('#xdr-input').val();

    // Отправляем XDR на сервер и ожидаем JSON в ответ
    $.ajax({
        url: '/lab/xdr_to_json',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ xdr: xdrText }),
        dataType: 'json',
        success: function(jsonData) {
            // Обрабатываем заголовки транзакции и операции, используя полученный JSON
            processOperations(jsonData);
        },
        error: function(xhr, status, error) {
            // В случае ошибки, показываем сообщение пользователю
            var errorMessage = xhr.status + ': ' + xhr.statusText;
            M.toast({html: 'Ошибка при импорте XDR: ' + errorMessage, classes: 'rounded'});
        }
    });
}

function processHeaders(jsonData) {
    // Удаляем все существующие блоки gather-block
    $('.gather-block').each(function() {
        $(this).closest('.card').remove();
    });
    blockCounter = 0;

    // Извлекаем sourceAccount, memo и его тип из объекта jsonData
    var sourceAccount = jsonData.attributes.sourceAccount;
    var memoType = jsonData.attributes.memoType ? jsonData.attributes.memoType.toLowerCase() : ''; // Преобразование в нижний регистр
    var memoContent = jsonData.attributes.memoContent || '';

    // Устанавливаем значения в соответствующие поля
    $('[id^="publicKey-"]').val(sourceAccount);
    $('#memo_type').val(memoType ? memoType : "none");
    $('#memo').val(memoContent);

    // Обновляем состояние текстовых полей и выпадающего списка
    M.updateTextFields(); // Обновляем текстовые поля
    $('select').formSelect(); // Обновляем выпадающие списки

    // Обновляем поле мемо на основе его типа
    updateMemoField(); // Эта функция должна быть определена в вашем коде
}

function importTransaction() {
    // Получаем XDR из текстового поля
    var xdrText = $('#xdr-input').val();

    // Отправляем XDR на сервер и ожидаем JSON в ответ
    $.ajax({
        url: '/lab/xdr_to_json',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ xdr: xdrText }),
        dataType: 'json',
        success: function(jsonData) {
            // Обрабатываем заголовки транзакции и операции, используя полученный JSON
            processHeaders(jsonData);
            processOperations(jsonData);
        },
        error: function(xhr, status, error) {
            // В случае ошибки, показываем сообщение пользователю
            var errorMessage = xhr.status + ': ' + xhr.statusText;
            M.toast({html: 'Ошибка при импорте XDR: ' + errorMessage, classes: 'rounded'});
        }
    });
}

function calculateFinalCost(inputElement) {
    var $inputElement = $(inputElement);
    var $operationBlock = $inputElement.closest('.card-content');

    const amountInput = $operationBlock.find('[data-type="amount"]');
    const priceInput = $operationBlock.find('[data-type="price"]');
    const helperTextDiv = priceInput.closest('.input-field').find('.helper-text');
    const sellingInput = $operationBlock.find('[data-type="selling"]');
    const buyingInput = $operationBlock.find('[data-type="buying"]');

    let amount = parseFloat(amountInput.val().replace(',', '.'));
    let price = parseFloat(priceInput.val().replace(',', '.'));
    let sellingValue = sellingInput.val() ? sellingInput.val().split('-')[0] : '';
    let buyingValue = buyingInput.val() ? buyingInput.val().split('-')[0] : '';

    if (!isNaN(amount) && !isNaN(price)) {
        let finalCost = amount * price;
        let operationType = $operationBlock.data('type');
        let textOutput = '';

        if (operationType === 'buy') {
            textOutput = `Вы продадите ${finalCost.toFixed(2)} ${sellingValue}`;
        } else {
            textOutput = `Вы купите ${finalCost.toFixed(2)} ${buyingValue}`;
        }

        helperTextDiv.text(textOutput);
    } else {
        helperTextDiv.text('');
    }
}