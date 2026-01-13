var globalCash = {}; // Глобальный словарь для хранения данных запросов
var blockCounter = 0;

function deleteBlock(element) {
    $(element).closest('.card').remove();
}

function viewAccount(element) {
    var destinationValue = $(element).closest('.row').find('.account-input').val().trim();

    if (destinationValue.length === 56) {
        window.open('https://viewer.eurmtl.me/account/' + destinationValue, '_blank');
    } else {
        showToast('Адрес должен содержать 56 символов', 'warning');

    }
}

function viewAsset(element) {
    var destinationValue = $(element).closest('.row').find('.account-input').val().trim();

    if (destinationValue.length > 2) {
        window.open('https://viewer.eurmtl.me/asset/' + destinationValue, '_blank');
    } else {
        showToast('Ассет не выбран', 'warning');
    }
}

function viewClaimableBalance(element) {
    var balanceId = $(element).closest('.row').find('.account-input').val().trim();
    var shortBalanceId = balanceId.replace(/^0+/, '');

    if (!shortBalanceId.length) {
        showToast('Claimable Balance ID пустой', 'warning');
        return;
    }

    if ((balanceId.length === 64 || balanceId.length === 72) && /^[A-Fa-f0-9]+$/.test(balanceId)) {
        window.open('https://stellar.expert/explorer/public/claimable-balance/' + shortBalanceId, '_blank');
        return;
    }

    showToast('Claimable Balance ID должен содержать 64 или 72 hex-символа', 'warning');
}

function getSourceKey(buttonElement){
    var $button = $(buttonElement);
    var $inputField = $button.closest('.account-selector');
    var sourceAccount = $inputField.find('.sourceAccount').val();
    var publicKey = $('[id^="publicKey-"]').val();


    var keyToUse = sourceAccount && sourceAccount.length === 56 ? sourceAccount : (publicKey.length === 56 ? publicKey : null);

    if (!keyToUse) {
        showToast('Please provide a valid publicKey or sourceAccount', 'warning');
        return;
    }
    return keyToUse;
}

function fetchDataAndShowDropdown(url, globalDataVarKey, $row, $input) {
    if (!window.globalCash[globalDataVarKey]) {
        showToast('Подождите, идет загрузка', 'info');
        $.ajax({
            url: url,
            type: 'GET',
            success: function(response) {
                window.globalCash[globalDataVarKey] = response;
                showDropdown($row, $input, response);
            },
            error: function(xhr, status, error) {
                console.error('Не удалось получить данные:', error);
                showToast('Ошибка при загрузке данных', 'danger');
            }
        });
    } else {
        showDropdown($row, $input, window.globalCash[globalDataVarKey]);
    }
}

function fetchAccounts(buttonElement) {
    var $button = $(buttonElement);
    var $row = $button.closest('.row');
    var $input = $row.find('.account-input');

    fetchDataAndShowDropdown('/lab/mtl_accounts', 'accountsMTL', $row, $input);
}

function fetchAssetsMTL(buttonElement) {
    var $button = $(buttonElement);
    var $row = $button.closest('.row');
    var $input = $row.find('.account-input');

    fetchDataAndShowDropdown('/lab/mtl_assets', 'assetsMTL', $row, $input);
}

function fetchAssetsSrc(buttonElement) {
    var keyToUse = getSourceKey(buttonElement);
    if (!keyToUse) {
        return;
    }

    var $button = $(buttonElement);
    var $row = $button.closest('.row');
    var $input = $row.find('.account-input');

    fetchDataAndShowDropdown(`/lab/assets/${keyToUse}`, keyToUse, $row, $input);
}

function fetchClaimableBalances(buttonElement) {
    var keyToUse = getSourceKey(buttonElement);
    if (!keyToUse) {
        return;
    }

    var $button = $(buttonElement);
    var $row = $button.closest('.row');
    var $input = $row.find('.account-input');

    fetchDataAndShowDropdown(`/lab/claimable_balances/${keyToUse}`, `claimable_${keyToUse}`, $row, $input);
}

function showDropdown($row, $input, accounts) {
    var dropdownId = 'dropdown-' + new Date().getTime();

    // Проверка на существование предыдущего dropdown
    if ($('#' + dropdownId).length) {
        $('#' + dropdownId).remove();
    }

    // Удаление всех существующих dropdowns
    $('.dropdown-menu').remove();

    var $dropdown = $('<div>').addClass('dropdown-menu').attr('id', dropdownId);

    $.each(accounts, function(name, address) {
        var $a = $('<a>').addClass('dropdown-item').text(name).attr('href', '#');
        $a.on('click', function(e) {
            e.preventDefault();
            $input.val(address).trigger('change');
            $dropdown.removeClass('show');
        });
        $dropdown.append($a);
    });

    $row.append($dropdown);

    // Обновленное позиционирование
    $input.parent().css('position', 'relative');
    $dropdown.css({
        top: $input.outerHeight(),
        left: 0,
        position: 'absolute',
        width: $input.outerWidth(),
        'z-index': 1000
    });

    // Показываем dropdown
    $dropdown.addClass('show');

    // Закрываем dropdown при клике вне его
    setTimeout(function() {
        var clickHandler = function(event) {
            if (!$(event.target).closest($dropdown).length &&
                !$(event.target).is($input) &&
                !$(event.target).is($row.find('button'))) {
                $dropdown.removeClass('show');
                $(document).off('click', clickHandler);
            }
        };
        $(document).on('click', clickHandler);
    }, 100);
}

function get_uid(){
    return new Date().getTime();
}

function generateAccountSelector(fieldName = "sourceAccount",
                                 labelName = "Source Account (optional)",
                                 fieldValue = "",
                                 helperText = "",
                                 validationOverride = "") {
    var uid = get_uid();
    var validationValue = validationOverride || (fieldName === "sourceAccount" ? "account_null" : "account");
    return `
<!-- Account -->
<div class="row mb-3">
    <div class="col-12">
        <label for="${fieldName}-${uid}" class="form-label">${labelName}</label>
        <div class="input-group">
            <input type="text" class="form-control account-input me-2" maxlength="56" data-type="${fieldName}"
                data-validation="${validationValue}"
                value="${fieldValue}" id="${fieldName}-${uid}">

            <button type="button" class="btn btn-icon btn-primary me-2" data-bs-toggle="tooltip" title="Выбрать из списка"
                onclick="fetchAccounts(this)">
                <i class="ti ti-list"></i>
            </button>

            <button type="button" class="btn btn-icon btn-info" data-bs-toggle="tooltip" title="Просмотреть в эксперте"
                onclick="viewAccount(this)">
                <i class="ti ti-eye"></i>
            </button>
        </div>
        ${helperText ? `<div class="form-text">${helperText}</div>` : ""}
    </div>
</div>
    `;
}

function viewPool(element) {
    var poolId = $(element).closest('.row').find('.account-input').val().trim();
    if (poolId.length === 64) {
        window.open('https://viewer.eurmtl.me/pool/' + poolId, '_blank');
    } else {
        showToast('Pool ID должен содержать 64 символа', 'warning');
    }
}

function fetchPoolsMTL(buttonElement) {
    var $button = $(buttonElement);
    var $row = $button.closest('.row');
    var $input = $row.find('.account-input');
    fetchDataAndShowDropdown('/lab/mtl_pools', 'poolsMTL', $row, $input);
}

function generatePoolSelector(fieldName = "pool",
                             labelName = "Liquidity Pool",
                             fieldValue = "",
                             validationOverride = "pool") {
    var uid = get_uid();
    return `
<!-- Pool Selector -->
<div class="row mb-3">
    <div class="col-12">
        <label for="${fieldName}-${uid}" class="form-label">${labelName}</label>
        <div class="input-group">
            <input type="text" class="form-control account-input me-2" data-type="${fieldName}"
                data-validation="${validationOverride}"
                value="${fieldValue}" id="${fieldName}-${uid}">
            <button type="button" class="btn btn-icon btn-primary me-2" data-bs-toggle="tooltip"
                title="Выбрать из списка" onclick="fetchPoolsMTL(this)">
                <i class="ti ti-list"></i>
            </button>
            <button type="button" class="btn btn-icon btn-info" data-bs-toggle="tooltip"
                title="Просмотреть в эксперте" onclick="viewPool(this)">
                <i class="ti ti-eye"></i>
            </button>
        </div>
    </div>
</div>
    `;
}

function generateAssetSelector(fieldName = "asset",
                                 labelName = "Asset",
                                 fieldValue = "",
                                 helperText = "",
                                 validationOverride = "asset") {
    var uid = get_uid();
    return `
<!-- Asset Selector -->
<div class="row mb-3">
    <div class="col-12">
        <label for="${fieldName}-${uid}" class="form-label">${labelName}</label>
        <div class="input-group">
            <input type="text" class="form-control account-input me-2" data-type="${fieldName}"
                data-validation="${validationOverride}"
                value="${fieldValue}" id="${fieldName}-${uid}" onchange="checkAssetBalance(this)">
            <button type="button" class="btn btn-icon btn-primary me-2" data-bs-toggle="tooltip"
                title="Выбрать из списка" onclick="fetchAssetsMTL(this)">
                <i class="ti ti-list"></i>
            </button>
            <button type="button" class="btn btn-icon btn-secondary me-2" data-bs-toggle="tooltip"
                title="Выбрать из трастлайнов аккаунта" onclick="fetchAssetsSrc(this)">
                <i class="ti ti-search"></i>
            </button>
            <button type="button" class="btn btn-icon btn-info" data-bs-toggle="tooltip"
                title="Просмотреть в эксперте" onclick="viewAsset(this)">
                <i class="ti ti-eye"></i>
            </button>
        </div>
        <div class="form-text text-success balance-text" style="cursor: pointer; display: none; font-weight: bold;" onclick="setAmount(this)"></div>
        ${helperText ? `<div class="form-text">${helperText}</div>` : ""}
    </div>
</div>
    `;
}

function checkAssetBalance(element) {
    var $input = $(element);
    var asset = $input.val();
    // Support picking buying/selling assets in offers
    var $block = $input.closest('.gather-block');
    
    // Find Source Account
    var sourceAccount = $block.find('input[data-type="sourceAccount"]').val();
    if (!sourceAccount || sourceAccount.length !== 56) {
        sourceAccount = $('[id^="publicKey-"]').val();
    }

    if (!sourceAccount || sourceAccount.length !== 56 || !asset) {
        $input.closest('.row').find('.balance-text').hide();
        return;
    }

    // Don't check balance for 'buying' asset in ManageSellOffer (we receive it)
    // But DO check for 'selling' asset.
    // For ManageBuyOffer, we spend 'selling' asset (confusing naming in Horizon/Stellar, but standard is: Selling = what you give, Buying = what you get)
    // Wait, ManageBuyOffer: "Creates an offer that specifies the amount of an asset the account wants to *buy*."
    // But you still pay with the *selling* asset.
    // So for both Sell and Buy offers, we care about the balance of the 'selling' asset?
    // - ManageSellOffer: selling X, buying Y. Need balance of X.
    // - ManageBuyOffer: buying X, selling Y. Need balance of Y.
    
    // Let's just check balance for whatever asset selector triggered this. 
    // If user checks 'Buying' asset balance, it tells them how much they HAVE of the thing they want to buy (maybe useful?)
    // But critically, for 'Selling' field, it tells them how much they can spend.
    
    $.ajax({
        url: '/lab/check_balance',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ account_id: sourceAccount, asset: asset }),
        success: function(response) {
            var $balanceText = $input.closest('.row').find('.balance-text');
            if (response.balance) {
                var text = 'Available: ' + response.balance;
                if (response.is_issuer) text += ' (Issuer)';
                $balanceText.text(text).show();
            } else {
                $balanceText.hide();
            }
        },
        error: function() {
             $input.closest('.row').find('.balance-text').hide();
        }
    });
}

function setAmount(element) {
    var text = $(element).text();
    // Extract number from "Available: 123.456 (Issuer)"
    var amount = text.replace('Available: ', '').split(' ')[0];
    if (amount === 'Unlimited') return; 
    
    var $block = $(element).closest('.gather-block');
    // For ManageSellOffer/Payment, we set 'amount'.
    // For ManageBuyOffer, 'amount' input is "Amount being bought". 
    // If we click balance on 'Selling' asset (asset we pay with), we might want to calculate? 
    // But 'setAmount' usually implies setting the main amount field.
    // If the user clicks balance on 'Asset' (Payment) or 'Selling' (Sell Offer), setting 'amount' is correct.
    // If user clicks balance on 'Buying' (Buy Offer), setting 'amount' (amount to buy) is correct (buying up to current balance of that asset? No, that doesn't make sense).
    
    // Simplification: Always set the 'amount' field of the block.
    // User can adjust if they clicked the wrong one.
    
    var $amountInput = $block.find('input[data-type="amount"]');
    if ($amountInput.length) {
        $amountInput.val(amount);
        $amountInput.trigger('input'); // Trigger any calculations
        showToast('Amount set to ' + amount, 'info');
    }
}

function generateClaimableBalanceSelector(fieldName = "balanceId",
                                          labelName = "Claimable Balance ID",
                                          fieldValue = "",
                                          validationOverride = "claimable_balance_id") {
    var uid = get_uid();
    return `
<!-- Claimable Balance Selector -->
<div class="row mb-3">
    <div class="col-12">
        <label for="${fieldName}-${uid}" class="form-label">${labelName}</label>
        <div class="input-group">
            <input type="text" class="form-control account-input me-2" data-type="${fieldName}"
                data-validation="${validationOverride}" value="${fieldValue}" id="${fieldName}-${uid}">
            <button type="button" class="btn btn-icon btn-primary me-2" data-bs-toggle="tooltip"
                title="Выбрать из списка" onclick="fetchClaimableBalances(this)">
                <i class="ti ti-list"></i>
            </button>
            <button type="button" class="btn btn-icon btn-info" data-bs-toggle="tooltip"
                title="Просмотреть в эксперте" onclick="viewClaimableBalance(this)">
                <i class="ti ti-eye"></i>
            </button>
        </div>
    </div>
</div>
    `;
}

function generateOfferSelector(fieldName = "offer_id", labelName = "Offer ID", fieldValue = "") {
    var uid = get_uid();
    return `
<!-- Offer Selector -->
<div class="row mb-3">
    <div class="col-12">
        <label for="${fieldName}-${uid}" class="form-label">${labelName}</label>
        <div class="input-group">
            <input type="text" class="form-control me-2" id="${fieldName}-${uid}" value="${fieldValue}"
                data-type="${fieldName}" data-validation="int">
            <button type="button" class="btn btn-icon btn-primary" data-bs-toggle="tooltip" title="Fetch Offers" onclick="fetchOffers(this)">
                <i class="ti ti-search"></i>
            </button>
        </div>
        <div class="form-text">If 0, will create a new offer. Existing offer ID numbers can be found using the Offers for Account endpoint.</div>
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
<div class="row mb-3">
    <div class="col-12">
        <label for="${fullId}" class="form-label">${labelName}</label>
        <input id="${fullId}" type="text" class="form-control" data-type="${fieldName}"
            data-validation="${validation}" value="${fieldValue}" ${onInputAttribute}>
        ${helperText ? `<div class="form-text">${helperText}</div>` : ""}
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
    var $row = $button.closest('.row');
    var $input = $row.find('input[data-type="offer_id"]'); // Использование data-type для точного выбора

    fetchOffersAndShowDropdown(`/lab/offers/${keyToUse}`, 'offers'+keyToUse, $row, $input);
}

function fetchOffersAndShowDropdown(url, globalDataVarKey, $row, $input) {
    if (!window.globalCash[globalDataVarKey]) {
        showToast('Подождите, идет загрузка', 'info');
        $.ajax({
            url: url,
            type: 'GET',
            success: function(response) {
                window.globalCash[globalDataVarKey] = response;
                showOfferDropdown($row, $input, response);
            },
            error: function(xhr, status, error) {
                console.error('Не удалось получить данные:', error);
                showToast('Ошибка при загрузке данных', 'danger');
            }
        });
    } else {
        showOfferDropdown($row, $input, window.globalCash[globalDataVarKey]);
    }
}

function showOfferDropdown($row, $input, offers) {
    var dropdownId = 'dropdown-' + new Date().getTime();
    if ($('#' + dropdownId).length) {
        $('#' + dropdownId).remove();
    }
    $('.dropdown-menu').remove();

    var $dropdown = $('<div>').addClass('dropdown-menu').attr('id', dropdownId);

    $.each(offers, function(name, recordJson) {
        var $a = $('<a>').addClass('dropdown-item').text(name).attr('href', '#');
        $a.on('click', function(e) {
            e.preventDefault();
            var record = JSON.parse(recordJson);
            
            // Populate Offer ID
            $input.val(record.id);
            
            // Populate other fields in the same card
            var $cardBody = $row.closest('.card-body');
            var cardType = $cardBody.data('type');
            
            // Selling Asset
            var selling = record.selling;
            var sellingVal = selling.asset_type === 'native' ? 'XLM' : `${selling.asset_code}-${selling.asset_issuer}`;
            $cardBody.find('input[data-type="selling"]').val(sellingVal).trigger('change');
            
            // Buying Asset
            var buying = record.buying;
            var buyingVal = buying.asset_type === 'native' ? 'XLM' : `${buying.asset_code}-${buying.asset_issuer}`;
            $cardBody.find('input[data-type="buying"]').val(buyingVal);

            // Price
            $cardBody.find('input[data-type="price"]').val(record.price);

            // Amount
            if (cardType === 'buy') {
                // For ManageBuyOffer, amount is the amount of asset being BOUGHT.
                // Horizon record.amount is amount of asset being SOLD.
                // buy_amount = sell_amount * price
                var buyAmount = parseFloat(record.amount) * parseFloat(record.price);
                $cardBody.find('input[data-type="amount"]').val(buyAmount.toFixed(7));
            } else {
                // For ManageSellOffer, amount is the amount of asset being SOLD.
                $cardBody.find('input[data-type="amount"]').val(record.amount);
            }

            $dropdown.removeClass('show');
        });
        $dropdown.append($a);
    });

    $row.append($dropdown);

    // Обновленное позиционирование
    $input.parent().css('position', 'relative');
    $dropdown.css({
        top: $input.outerHeight(),
        left: 0,
        position: 'absolute',
        width: $input.outerWidth(),
        'z-index': 1000
    });

    // Показываем dropdown
    $dropdown.addClass('show');

    // Закрываем dropdown при клике вне его
    setTimeout(function() {
        var clickHandler = function(event) {
            if (!$(event.target).closest($dropdown).length &&
                !$(event.target).is($input) &&
                !$(event.target).is($row.find('button'))) {
                $dropdown.removeClass('show');
                $(document).off('click', clickHandler);
            }
        };
        $(document).on('click', clickHandler);
    }, 100);
}


function fetchDataEntry(buttonElement) {
    var keyToUse = getSourceKey(buttonElement);
    if (!keyToUse) {
        return;
    }

    var $button = $(buttonElement);
    var $row = $button.closest('.row');
    var $input = $row.find('[data-type="data_name"]');

    fetchDataAndShowDropdown(`/lab/data/${keyToUse}`, 'data'+keyToUse, $row, $input);
}

function generatePathSelector(fieldName = "path", labelName = "Path") {
    var uid = get_uid();
    return `
<div class="row mb-3">
    <div class="col-10">
        <label for="${fieldName}-${uid}" class="form-label">${labelName}</label>
        <input type="text" class="form-control" data-type="${fieldName}" id="${fieldName}-${uid}" data-validation="text" placeholder="Choose path" required>
    </div>
    <div class="col-2 d-flex align-items-end">
        <button type="button" class="btn btn-icon btn-primary" data-bs-toggle="tooltip" title="Fetch Path" onclick="fetchPath(this, '${fieldName}-${uid}')">
            <i class="ti ti-search"></i>
        </button>
    </div>
</div>
    `;
}

function fetchPath(buttonElement, pathFieldId) {
    var $button = $(buttonElement);
    var $row = $button.closest('.row');
    var $input = $('#' + pathFieldId);
    var $operationBlock = $button.closest('.card-body');

    var sellingAsset = $operationBlock.find('[data-type="selling"]').val() || 0;
    var buyingAsset = $operationBlock.find('[data-type="buying"]').val() || 0;
    var amount = $operationBlock.find('[data-type="amount"]').val() || 0;
    var publicKey = `${sellingAsset}/${buyingAsset}/${amount}`;

    fetchDataAndShowDropdown(`/lab/path/${publicKey}`, 'path'+publicKey, $row, $input);
}

function getBlockCounter() {
    return blockCounter++;
}

function generateCardHeader(cardName, blockId) {
    return `
        <div tabindex="0" class="row mb-3" id="block${blockId}">
            <div class="col-7">
                <h5 class="card-title">${cardName} Block #${blockId}</h5>
            </div>
            <div class="col-1 d-flex justify-content-end">
                <button class="btn btn-icon btn-secondary" data-bs-toggle="tooltip" title="Move block up" onclick="moveBlockUp(this)">
                    <i class="ti ti-arrow-up"></i>
                </button>
            </div>
            <div class="col-2">
                <button class="btn btn-secondary w-100" onclick="cloneBlock(this)">Clone</button>
            </div>
            <div class="col-2">
                <button class="btn btn-danger w-100" onclick="deleteBlock(this)">Delete Block</button>
            </div>
        </div>
    `;
}

function generateCardFirst() {
    return `
<div class="card" id="firstCard">
    <div class="card-body">
        ${generateAccountSelector("publicKey", "PublicKey")}

        <!-- Memo type and input -->
        <div class="mb-3">
            <label for="memo_type" class="form-label">Memo Type</label>
            <select id="memo_type" name="memo_type" class="form-select" onchange="updateMemoField()">
                <option value="none" selected>None</option>
                <option value="memo_text">Text</option>
                <option value="memo_hash">Hash</option>
            </select>
        </div>

        <div class="mb-3" id="memo-input-field" style="display: none;">
            <label for="memo" class="form-label">Memo</label>
            <input type="text" id="memo" name="memo" class="form-control" maxlength="28">
        </div>

        <!-- Sequence -->
        <div class="row mb-3">
            <div class="col-12">
                <label for="sequence" class="form-label">Sequence</label>
                <div class="input-group">
                    <input type="text" id="sequence" name="sequence" class="form-control" value="0" min="0">
    
                    <button type="button" class="btn btn-icon btn-primary" 
                    data-bs-toggle="tooltip" title="Fetch current sequence" onclick="fetchSequence(this)">
                        <i class="ti ti-refresh"></i>
                    </button>
                </div>
                <div class="form-text">Set to 0 for automatic sequence generation from horizon</div>
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
    <div class="card-body gather-block" data-type="payment" data-index="${blockId}">
        ${generateCardHeader("Payment", blockId)}

        ${generateAccountSelector("destination", "Destination", "", "Recipient account (G...)")}
        ${generateAssetSelector("asset", "Asset", "", "Asset being sent")}
        ${generateInput("amount", "Amount", "float", "", "Amount to send")}
        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardTrustPayment() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="trust_payment" data-index="${blockId}">
        ${generateCardHeader("Trust Payment", blockId)}
        ${generateAccountSelector("destination", "Destination", "", "Recipient account (G...)")}
        ${generateAssetSelector("asset", "Asset", "", "Asset being sent with temporary trust flag")}
        ${generateInput("amount", "Amount", "float", "", "Amount to send")}
        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardChangeTrust() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="change_trust" data-index="${blockId}">
        ${generateCardHeader("Change Trust", blockId)}
        ${generateAssetSelector("asset", "Asset", "", "Asset to add/remove trustline")}
        ${generateInput("limit", "Trust Limit (optional)", "float_null", "",
            "Leave empty to default to the max int64. Set to 0 to remove the trust line.")}
        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardBuy() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="buy" data-index="${blockId}">
        ${generateCardHeader("Buy", blockId)}
        
        ${generateOfferSelector()}

        ${generateAssetSelector("buying", "Buying", "", "Asset you want to buy")}
        ${generateAssetSelector("selling", "Selling", "", "Asset you will pay with")}

        ${generateInput("amount", "Amount you are buying (zero to delete offer)", "float_trade", "", "Amount of buying asset; 0 deletes offer")}
        ${generateInput("price", "Price per unit (buying in terms of selling)", "float_trade","","Тут будет расчет получаемого")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardSell() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="sell" data-index="${blockId}">
        ${generateCardHeader("Sell", blockId)}
        
        ${generateOfferSelector()}

        ${generateAssetSelector("selling", "Selling", "", "Asset you are selling")}
        ${generateAssetSelector("buying", "Buying", "", "Asset you want to receive")}

        ${generateInput("amount", "Amount you are selling (zero to delete offer)", "float_trade", "", "Amount of selling asset; 0 deletes offer")}
        ${generateInput("price", "Price per unit (buying in terms of selling)", "float_trade","","Тут будет расчет получаемого")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardSellPassive() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="sell_passive" data-index="${blockId}">
        ${generateCardHeader("Sell Passive", blockId)}
        ${generateAssetSelector("selling", "Selling", "", "Asset you are selling")}
        ${generateAssetSelector("buying", "Buying", "", "Asset you want to receive")}

        ${generateInput("amount", "Amount you are selling (zero to delete offer)", "float_trade", "", "Amount of selling asset; 0 deletes offer")}
        ${generateInput("price", "Price per unit (buying in terms of selling)", "float_trade","","Тут будет расчет получаемого")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardCreateAccount() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="create_account" data-index="${blockId}">
        ${generateCardHeader("Create Account", blockId)}
        ${generateAccountSelector("destination", "Destination", "", "New account (G...)")}

        ${generateInput("startingBalance", "Starting Balance", "float", "", "Amount of XLM to fund new account")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardManageData() {
    var blockId = getBlockCounter();
    var uid = get_uid();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="manage_data" data-index="${blockId}">
        ${generateCardHeader("Manage Data", blockId)}

        <div class="row mb-3">
            <div class="col-11">
                <label for="data_name-${uid}" class="form-label">Entry Name</label>
                <input id="data_name-${uid}" type="text" class="form-control" maxlength="64"
                    data-type="data_name" data-validation="text_null">
            </div>
            <div class="col-1 d-flex align-items-end">
                <button type="button" class="btn btn-icon btn-primary" data-bs-toggle="tooltip"
                    title="Fetch Data" onclick="fetchDataEntry(this)">
                    <i class="ti ti-search"></i>
                </button>
            </div>
        </div>

        <div class="row mb-3">
            <div class="col-11">
                <label for="data_value-${uid}" class="form-label">Entry Value (optional)</label>
                <input id="data_value-${uid}" type="text" class="form-control" maxlength="64"
                    data-type="data_value" data-validation="text_null">
                <div class="form-text">If empty, will delete the data entry named in this operation. Note: Only supports strings.</div>
            </div>
        </div>

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardSetOption() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="set_options" data-index="${blockId}">
        ${generateCardHeader("Set Options", blockId)}

        ${generateInput("master", "Master Weight (optional)", "int_null",  "",
            "This can result in a permanently locked account. Are you sure you know what you are doing?")}
        ${generateInput("threshold", "Low/Medium/High Threshold (optional) you can set just 1 or 10 for all or use 1/2/3", "threshold",  "",
            "This can result in a permanently locked account. Are you sure you know what you are doing?")}
        ${generateInput("home", "Home Domain (optional)", "text_null", "", "Domain to publish in account home_domain")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardSetOptionSigner() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="set_options_signer" data-index="${blockId}">
        ${generateCardHeader("Set Options Signer", blockId)}

        ${generateAccountSelector("signerAccount", "Ed25519 Public Key (optional)")}

        ${generateInput("weight", "Signer Weight", "int",  "",
            "Signer will be removed from account if this weight is 0. Used to add/remove or adjust weight of an additional signer on the account.")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardBumpSequence() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="bump_sequence" data-index="${blockId}">
        ${generateCardHeader("Bump Sequence", blockId)}

        ${generateInput("bump_to", "Bump To", "int", "",
            "New sequence number for source account (must be higher than current)")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardClawback() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="clawback" data-index="${blockId}">
        ${generateCardHeader("Clawback", blockId)}

        ${generateAssetSelector("asset", "Asset", "", "Asset to claw back")}
        ${generateAccountSelector("from", "From", "", "Account to claw back from")}
        ${generateInput("amount", "Amount", "float", "", "Amount to reclaim")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardClaimClaimableBalance() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="claim_claimable_balance" data-index="${blockId}">
        ${generateCardHeader("Claim Claimable Balance", blockId)}

        ${generateClaimableBalanceSelector("balanceId", "Claimable Balance ID")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardBeginSponsoringFutureReserves() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="begin_sponsoring_future_reserves" data-index="${blockId}">
        ${generateCardHeader("Begin Sponsoring Future Reserves", blockId)}

        ${generateAccountSelector("sponsored_id", "Sponsored Account", "", "Account to sponsor future reserves for")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Sponsor account (optional, defaults to top-level public key)")}
    </div>
</div>
    `;
}

function generateCardEndSponsoringFutureReserves() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="end_sponsoring_future_reserves" data-index="${blockId}">
        ${generateCardHeader("End Sponsoring Future Reserves", blockId)}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardRevokeSponsorship() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="revoke_sponsorship" data-index="${blockId}">
        ${generateCardHeader("Revoke Sponsorship", blockId)}

        <div class="row mb-3">
            <div class="col-12">
                <label for="revoke_type-${blockId}" class="form-label">Revoke Type</label>
                <select id="revoke_type-${blockId}" class="form-select" data-type="revoke_type" data-validation="text"
                        onchange="updateRevokeSponsorshipFields(this)">
                    <option value="" disabled>Choose revoke type</option>
                    <option value="account" selected>Account</option>
                    <option value="trustline">Trustline</option>
                    <option value="data">Data</option>
                    <option value="offer">Offer</option>
                    <option value="claimable_balance">Claimable Balance</option>
                    <option value="liquidity_pool">Liquidity Pool</option>
                    <option value="signer">Signer (Ed25519)</option>
                </select>
            </div>
        </div>

        <div data-revoke-target="account">
            ${generateAccountSelector("revoke_account_id", "Account", "", "Account whose sponsorship is being revoked")}
        </div>

        <div data-revoke-target="trustline" style="display: none;">
            ${generateAccountSelector("revoke_trustline_account", "Account", "", "Account holding the trustline", "account_null")}
            ${generateAssetSelector("revoke_trustline_asset", "Asset", "", "Trustline asset to revoke sponsorship for", "text_null")}
        </div>

        <div data-revoke-target="data" style="display: none;">
            ${generateAccountSelector("revoke_data_account", "Account", "", "Account that owns the data entry", "account_null")}
            ${generateInput("revoke_data_name", "Data Name", "text_null", "", "Data entry name")}
        </div>

        <div data-revoke-target="offer" style="display: none;">
            ${generateAccountSelector("revoke_offer_seller", "Seller", "", "Account that owns the offer", "account_null")}
            ${generateInput("revoke_offer_id", "Offer ID", "int_null", "", "Offer ID to revoke sponsorship for")}
        </div>

        <div data-revoke-target="claimable_balance" style="display: none;">
            ${generateClaimableBalanceSelector("revoke_claimable_balance_id", "Claimable Balance ID", "", "text_null")}
        </div>

        <div data-revoke-target="liquidity_pool" style="display: none;">
            ${generatePoolSelector("revoke_liquidity_pool_id", "Liquidity Pool", "", "text_null")}
        </div>

        <div data-revoke-target="signer" style="display: none;">
            ${generateAccountSelector("revoke_signer_account", "Account", "", "Account that owns the signer", "account_null")}
            ${generateAccountSelector("revoke_signer_key", "Signer Public Key", "", "Signer key to revoke sponsorship for", "account_null")}
        </div>

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generatePayDivs() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="pay_divs" data-index="${blockId}">
        ${generateCardHeader("PayDivs", blockId)}

        ${generateAssetSelector("holders", "Holders", "", "Asset whose holders (incl. LP shares) will receive the payout")}

        ${generateAssetSelector("asset", "Asset", "", "Asset used to pay dividends")}

        ${generateInput("amount", "Amount", "float", "", "Total sum to distribute proportionally among holders")}
        ${generateInput("requireTrustline", "Require Trustline (1/0)", "int", "1",
            "1 to skip recipients without a trustline to payout asset, 0 to include all")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardSetTrustLineFlags() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="set_trust_line_flags" data-index="${blockId}">
        ${generateCardHeader("SetTrustLineFlags", blockId)}

        ${generateAssetSelector("asset", "Asset", "", "Asset whose trustline flags to change")}
        ${generateAccountSelector("trustor", "Trustor", "", "Account holding the trustline")}
        ${generateInput("setFlags", "Set Flags", "int_null", "",
            "(optional) 1 - Authorized 2 - Authorized maintain")}
        ${generateInput("clearFlags", "Clear Flags", "int_null", "",
            "(optional) 1 - Authorized 2 - Authorized maintain 4 - Clawback enabled")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}


function generateCardCopyMultiSign() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="copy_multi_sign" data-index="${blockId}">
        ${generateCardHeader("Copy Multi Sign", blockId)}

        ${generateAccountSelector("from", "From", "", "Account to copy signer set from")}
        ${generateAccountSelector("sourceAccount", "Source Account", "", "Target account (defaults to top-level public key)")}
    </div>
</div>
    `;
}
function generateCardSwap() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="swap" data-index="${blockId}">
        ${generateCardHeader("Swap", blockId)}

        ${generateAssetSelector("selling", "Selling", "", "Asset you send")}
        ${generateAssetSelector("buying", "Buying", "", "Asset you want to receive")}

        ${generateInput("amount", "Amount you are swap", "float", "", "Amount to send")}
        ${generateInput("destination", "Minimum destination amount", "float", "", "Minimum you expect to receive")}

        ${generatePathSelector("path", "Path")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}
function generateCardLiquidityPoolDeposit() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="liquidity_pool_deposit" data-index="${blockId}">
        ${generateCardHeader("Liquidity Pool Deposit", blockId)}

        ${generatePoolSelector("liquidity_pool_id", "Liquidity Pool")}
        ${generateInput("max_amount_a", "Max Amount A", "float", "", "Amount of first asset to deposit")}
        ${generateInput("max_amount_b", "Max Amount B", "float", "", "Amount of second asset to deposit")}
        ${generateInput("min_price", "Min Price (deposit_a/deposit_b price). Set 0 for auto", "float", "", "Leave 0 to auto-set about -5% from current")}
        ${generateInput("max_price", "Max Price (deposit_a/deposit_b price). Set 0 for auto", "float", "", "Leave 0 to auto-set about +5% from current")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardLiquidityPoolWithdraw() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="liquidity_pool_withdraw" data-index="${blockId}">
        ${generateCardHeader("Liquidity Pool Withdraw", blockId)}

        ${generatePoolSelector("liquidity_pool_id", "Liquidity Pool")}
        ${generateInput("amount", "Amount (shares to withdraw)", "float", "", "LP share amount to burn")}
        ${generateInput("min_amount_a", "Min Amount A to receive (0 for auto -5%)", "float", "", "Leave 0 to auto-set ~ -5%")}
        ${generateInput("min_amount_b", "Min Amount B to receive (0 for auto -5%)", "float", "", "Leave 0 to auto-set ~ -5%")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
    </div>
</div>
    `;
}

function generateCardLiquidityPoolTrustline() {
    var blockId = getBlockCounter();
    return `
<div class="card">
    <div class="card-body gather-block" data-type="liquidity_pool_trustline" data-index="${blockId}">
        ${generateCardHeader("Liquidity Pool Trustline", blockId)}

        ${generatePoolSelector("liquidity_pool_id", "Liquidity Pool")}
        
        ${generateInput("limit", "Trust Limit (optional)", "float_null", "",
            "Leave empty to default to the max int64. Set to 0 to remove the trust line.")}

        ${generateAccountSelector("sourceAccount", "Source Account", "", "Optional per-op source; defaults to top-level public key")}
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
        case 'bump_sequence':
        case 'bumpSequence':
            newCardHTML = generateCardBumpSequence();
            break;
        case 'clawback':
            newCardHTML = generateCardClawback();
            break;
        case 'claim_claimable_balance':
        case 'claimClaimableBalance':
            newCardHTML = generateCardClaimClaimableBalance();
            break;
        case 'begin_sponsoring_future_reserves':
        case 'beginSponsoringFutureReserves':
            newCardHTML = generateCardBeginSponsoringFutureReserves();
            break;
        case 'end_sponsoring_future_reserves':
        case 'endSponsoringFutureReserves':
            newCardHTML = generateCardEndSponsoringFutureReserves();
            break;
        case 'revoke_sponsorship':
        case 'revokeSponsorship':
            newCardHTML = generateCardRevokeSponsorship();
            break;
        case 'copy_multi_sign':
        case 'copyMultiSign':
            newCardHTML = generateCardCopyMultiSign();
            break;
        case 'swap':
            newCardHTML = generateCardSwap();
            break;
        case 'setTrustLineFlags':
        case 'set_trust_line_flags':
            newCardHTML = generateCardSetTrustLineFlags();
            break;
        case 'pay_divs':
        case 'payDivs':
            newCardHTML = generatePayDivs();
            break;
        case 'liquidity_pool_deposit':
        case 'liquidityPoolDeposit':
            newCardHTML = generateCardLiquidityPoolDeposit();
            break;
        case 'liquidity_pool_withdraw':
        case 'liquidityPoolWithdraw':
            newCardHTML = generateCardLiquidityPoolWithdraw();
            break;
        case 'liquidity_pool_trustline':
        case 'liquidityPoolTrustline':
            newCardHTML = generateCardLiquidityPoolTrustline();
            break;
        default:
            showToast(`Can't find selectedOperation ${selectedOperation} =(`, 'warning');
            return;
    }
    return newCardHTML;
}

function highlightAndFocusBlock(lastCounter) {
   setTimeout(function() {
        var blockElement = document.getElementById(`block${lastCounter}`);
        blockElement.focus();
        blockElement.classList.add('light-blue');
        setTimeout(function() {
            blockElement.classList.remove('light-blue');
        }, 500);
    }, 500);
}

function addOperation(selectElement) {
    var lastCounter = `${blockCounter}`;
    var selectedOperation = $(selectElement).val(); // Получаем значение выбранной операции из переданного элемента
    var newCardHTML = getCardByName(selectedOperation);

    if (newCardHTML) {
        var $newCard = $(newCardHTML).hide(); // Изначально скрываем карточку
        $('.new-operation').before($newCard);
        $newCard.fadeIn(); // Плавное появление карточки

        if (selectedOperation === 'revoke_sponsorship') {
            var revokeSelect = $newCard.find('[data-type="revoke_type"]');
            if (revokeSelect.length) {
                updateRevokeSponsorshipFields(revokeSelect[0]);
            }
        }

        highlightAndFocusBlock(lastCounter);
        showToast("Block " + selectedOperation + " was added", 'success');
    }

    // Сброс выбора в выпадающем списке
    $(selectElement).val('');
}

function updateRevokeSponsorshipFields(selectElement) {
    var $block = $(selectElement).closest('.gather-block');
    var selected = $(selectElement).val();
    var validationMap = {
        revoke_account_id: 'account',
        revoke_trustline_account: 'account',
        revoke_trustline_asset: 'asset',
        revoke_data_account: 'account',
        revoke_data_name: 'text',
        revoke_offer_seller: 'account',
        revoke_offer_id: 'int',
        revoke_claimable_balance_id: 'claimable_balance_id',
        revoke_liquidity_pool_id: 'pool',
        revoke_signer_account: 'account',
        revoke_signer_key: 'account'
    };

    $block.find('[data-revoke-target]').each(function() {
        var $section = $(this);
        var target = $section.data('revoke-target');
        var isActive = target === selected;
        $section.toggle(isActive);

        $section.find('[data-validation]').each(function() {
            var $input = $(this);
            var dataType = $input.data('type');
            var baseValidation = validationMap[dataType];
            if (!baseValidation) {
                return;
            }

            if (isActive) {
                $input.attr('data-validation', baseValidation);
                return;
            }

            if (baseValidation === 'account') {
                $input.attr('data-validation', 'account_null');
            } else if (baseValidation === 'int') {
                $input.attr('data-validation', 'int_null');
            } else if (baseValidation === 'float') {
                $input.attr('data-validation', 'float_null');
            } else {
                $input.attr('data-validation', 'text_null');
            }
        });
    });
}

function updateMemoField() {
    var $memoField = $('#memo');
    var selectedOperation = $('#memo_type').val();
    var maxLength = selectedOperation === 'memo_text' ? 28 : (selectedOperation === 'memo_hash' ? 64 : 0);

    if (selectedOperation === 'none') {
        $('#memo-input-field').hide();
    } else {
        $('#memo-input-field').show();
        $memoField.attr('data-length', maxLength);
        $memoField.attr('maxlength', maxLength);
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
                showToast('XDR successfully received', 'warning');
            } else if (response.error) {
                showToast(response.error, 'warning');
            } else {
                showToast("Can't get XDR =(", 'warning');
            }
        },
        error: function(xhr, status, error) {
            showToast("An error occurred: " + error, 'warning');
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
        case 'int_null':
            if (value) {
                if (!/^\d+$/.test(value)) {
                    throw new Error(`Не целое число для ${dataType} в блоке ${type} #${index}`);
                }
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
        case 'claimable_balance_id': {
            const trimmedBalanceId = value.trim();
            if (!/^[A-Fa-f0-9]+$/.test(trimmedBalanceId) ||
                (trimmedBalanceId.length !== 64 && trimmedBalanceId.length !== 72)) {
                throw new Error(`Неверный Claimable Balance ID для ${dataType} в блоке ${type} #${index}. Должен быть 64 или 72 hex-символа`);
            }
            value = trimmedBalanceId;
            break;
        }
        case 'text':
            if (!value.trim()) {
                throw new Error(`Текст не может быть пустым для ${dataType} в блоке ${type} #${index}`);
            }
            break;
        case 'text_null':
            // Нет дополнительной проверки, так как может быть пустым
            break;
        case 'threshold':
            if (!/^\d+$/.test(value) && !/^\d+\/\d+\/\d+$/.test(value)) {
                throw new Error(`Неверный формат для ${dataType} в блоке ${type} #${index}. Должно быть одно число или три числа через слэш (например, 1/2/3)`);
            }
            break;
        case 'pool':
            if (value.trim().length !== 64 || !/^[a-f0-9]+$/i.test(value)) {
                throw new Error(`Неверный формат Pool ID для ${dataType} в блоке ${type} #${index}. Должен быть 64 hex-символа`);
            }
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
        showToast(`Неверная длина для publicKey !`, 'warning');
        return;
    }

    data['memo_type'] = $('#memo_type').val();
    data['memo'] = $('#memo').val();
    
    // Validate sequence
    const sequence = $('#sequence').val();
    if (isNaN(sequence) || sequence < 0) {
        showToast('Sequence must be a positive number or zero', 'warning');
        return;
    }
    data['sequence'] = sequence;

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
        showToast(error.message, 'warning');
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
    let cardContent = originalBlock.find('.card-body');
    let dataType = cardContent.data('type'); // Получаем data-type из card-content

    if (!dataType) {
        console.error("Can't find selectedOperation: data-type is undefined");
        return;
    }

    let lastCounter = `${blockCounter}`;
    let newBlockHTML = getCardByName(dataType); // Генерируем HTML нового блока

    if (!newBlockHTML) {
        console.error("Can't find HTML for selectedOperation: " + dataType);
        return; // Если нет соответствующего HTML, пропускаем итерацию
    }

    let newBlock = $(newBlockHTML);

    // Копируем значения всех input из оригинального блока в новый, используя data-type
    originalBlock.find('input').each(function() {
        let inputType = $(this).data('type');
        let value = $(this).val();
        newBlock.find(`input[data-type="${inputType}"]`).val(value);
    });

    // Копируем значения select полей из оригинального блока в новый
    originalBlock.find('select').each(function() {
        let selectType = $(this).data('type');
        let value = $(this).val();
        if (selectType) {
            newBlock.find(`select[data-type="${selectType}"]`).val(value);
        }
    });

    if (dataType === 'revoke_sponsorship') {
        var revokeSelect = newBlock.find('[data-type="revoke_type"]');
        if (revokeSelect.length) {
            updateRevokeSponsorshipFields(revokeSelect[0]);
        }
    }

    $('.new-operation').before(newBlock.fadeIn());
    highlightAndFocusBlock(lastCounter);
    showToast("Block " + dataType + " was cloned", 'warning');

}

function moveBlockUp(element) {
    const $card = $(element).closest('.card');
    const $prevCard = $card.prevAll('.card').first();

    // don't move above the initial settings card
    if (!$prevCard.length || $prevCard.attr('id') === 'firstCard') {
        if (typeof showToast === 'function') {
            showToast('Already at the top', 'info');
        }
        return;
    }

    $prevCard.before($card);
}

function toCamelCase(str) {
    return str.replace(/(_\w)/g, function(m) {
        return m[1].toUpperCase();
    });
}

function processOperations(jsonData) {
    let count = 0; // Инициализация счетчика

    jsonData.operations.forEach((op) => {
        const isChangeTrust = op.name === 'changeTrust' || op.name === 'change_trust';
        const assetPayload = op.attributes ? op.attributes.asset : null;
        const isLpTrustline = isChangeTrust && assetPayload &&
            (assetPayload.liquidityPoolId || assetPayload.type === 'liquidity_pool_shares');
        var blockHTML = getCardByName(isLpTrustline ? 'liquidity_pool_trustline' : op.name);
        if (!blockHTML) {
            return; // Если нет соответствующего HTML, пропускаем итерацию
        }

        let $block = $(blockHTML);
        $block.find('input').each(function() {
            let dataType = $(this).data('type');
            let camelCaseDataType = toCamelCase(dataType);

            if (isLpTrustline) {
                if (dataType === 'liquidity_pool_id') {
                    $(this).val(assetPayload.liquidityPoolId || '');
                    return;
                }
                if (dataType === 'limit') {
                    $(this).val(op.attributes.limit || '');
                    return;
                }
            }

            // Обработка поля asset
            if (dataType.toLowerCase().includes('asset') ||
                dataType.toLowerCase().includes('buying') ||
                dataType.toLowerCase().includes('selling')) {
                    let asset = op.attributes[camelCaseDataType];
                    let value = '';

                    if (asset && asset.type === 'native') {
                        value = 'XLM';
                    } else if (asset && asset.liquidityPoolId) {
                        value = asset.liquidityPoolId;
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

        count++; // Увеличиваем счетчик при успешной обработке блока
    });

    showToast(`Импорт завершен, импортировано ${count} операций`, 'success');
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
            showToast('Ошибка при импорте XDR: ' + errorMessage, 'warning');
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
            showToast('Ошибка при импорте XDR: ' + errorMessage, 'warning');
        }
    });
}

function fetchSequence(buttonElement) {
    const publicKey = $('[id^="publicKey-"]').val();
    if (!publicKey || publicKey.length !== 56) {
        showToast('Please enter a valid public key first', 'warning');
        return;
    }

    $.ajax({
        url: `https://horizon.stellar.org/accounts/${publicKey}`,
        type: 'GET',
        success: function(response) {
            // Handle sequence as string to avoid BigInt precision issues
            const currentSequence = String(BigInt(response.sequence) + BigInt(1));
            $('#sequence').val(currentSequence);
            showToast(`Sequence updated to ${currentSequence}`, 'success');
        },
        error: function(xhr, status, error) {
            showToast('Failed to fetch sequence from Horizon', 'danger');
            console.error('Error fetching sequence:', error);
        }
    });
}

function calculateFinalCost(inputElement) {
    const $operationBlock = $(inputElement).closest('.gather-block');

    const getValueByType = (type) => $operationBlock.find(`[data-type="${type}"]`).val();
    const parseNumber = (value) => parseFloat(value.replace(',', '.'));

    const amount = parseNumber(getValueByType('amount'));
    const price = parseNumber(getValueByType('price'));

    const sellingAsset = getValueByType('selling')?.split('-')[0] || '';
    const buyingAsset = getValueByType('buying')?.split('-')[0] || '';

    const operationType = $operationBlock.data('type');

    const $helperText = $operationBlock.find('[data-type="price"]').closest('.row').find('.form-text');

    if (isNaN(amount) || isNaN(price)) {
        $helperText.text('');
        return;
    }

    if (amount === 0) {
        $helperText.text('The order will be deleted');
        return;
    }

    const finalCost = amount * price;
    const assetType = operationType === 'buy' ? sellingAsset : buyingAsset;
    const action = operationType === 'buy' ? 'sell' : 'buy';

    $helperText.text(`You will ${action} ${finalCost.toFixed(7)} ${assetType}`);
}


function initLab() {
    var newCardHTML = generateCardFirst();
    var $newCard = $(newCardHTML); // Преобразование HTML строки в jQuery объект
    $('.new-operation').before($newCard);

    //auto import
    var xdrInput = $('#xdr-input').val();
    if (xdrInput.trim() !== '') {
        importTransaction();
        $('#xdr-input').val('');
    }
}
