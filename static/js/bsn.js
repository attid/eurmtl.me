async function importData() {
    const input = document.getElementById('importInput').value;
    const importButton = document.getElementById('importButton');

    if (input.length !== 56) {
        alert(translations.errorMessage);
        return;
    }

    importButton.classList.add('is-loading');
    deleteAll();
    const url = `https://horizon.stellar.org/accounts/${input}`;

    try {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Проблема при получении данных: ' + response.statusText);
        }
        const data = await response.json();

        for (const key in data.data) {
            const valueEncoded = data.data[key];
            const valueDecoded = atob(valueEncoded);

            const hiddenBox = document.querySelector('.key-box-hidden.is-hidden');
            const newHiddenBox = hiddenBox.cloneNode(true);
            if (hiddenBox) {
                newHiddenBox.classList.remove('key-box-hidden', 'is-hidden');
                newHiddenBox.classList.add('key-box');

                newHiddenBox.dataset.key = key;
                newHiddenBox.dataset.value = valueDecoded;

                const keyInput = newHiddenBox.querySelector('.bor-key');
                const valueInput = newHiddenBox.querySelector('.bor-value');
                keyInput.value = key;
                valueInput.value = valueDecoded;

                hiddenBox.parentNode.insertBefore(newHiddenBox, hiddenBox.nextSibling);
            }
        }
        const addButton = document.querySelector('.add-button');
        if (addButton.classList.contains('is-hidden')) {
            addButton.classList.remove('is-hidden');
        }
        const endBox = document.querySelector('.end-box');
        if (endBox.classList.contains('is-hidden')) {
            endBox.classList.remove('is-hidden');
        }

        importButton.classList.remove('is-loading');

    } catch (error) {
        console.error('Ошибка:', error);
    }
}

function addKey() {
        const hiddenBox = document.querySelector('.key-box-hidden.is-hidden');
        const newHiddenBox = hiddenBox.cloneNode(true);
        if (hiddenBox) {
            newHiddenBox.classList.remove('key-box-hidden', 'is-hidden');
            newHiddenBox.classList.add('key-box');
            hiddenBox.parentNode.insertBefore(newHiddenBox, hiddenBox.nextSibling);
        }
}

function cloneElement(element) {
    const blockToClone = element.closest('.key-box');
    const clone = blockToClone.cloneNode(true);
    blockToClone.parentNode.insertBefore(clone, blockToClone.nextSibling);

    clone.removeAttribute('data-key');
    clone.removeAttribute('data-value');
}

function deleteAll() {
    const boxes = document.querySelectorAll('.key-box');

    boxes.forEach(box => {
        box.parentNode.removeChild(box);
    });
}

function deleteElement(element) {
    const blockToDelete = element.closest('.key-box');
    const keyInput = blockToDelete.querySelector('.bor-key');
    const valueInput = blockToDelete.querySelector('.bor-value');
    const deleteButton = blockToDelete.querySelector('.delete-button');

    if (!blockToDelete.dataset.key) {
        blockToDelete.parentNode.removeChild(blockToDelete);
    } else {
        blockToDelete.style.backgroundColor = 'red';
        valueInput.readOnly = true;
        valueInput.value = translations.willBeDeleted;
        deleteButton.textContent = translations.restoreButton;
        deleteButton.onclick = function() { restoreElement(deleteButton); };
        blockToDelete.dataset.delete = 'True';
    }
}

function restoreElement(element) {
    const blockToRestore = element.closest('.key-box');
    const valueInput = blockToRestore.querySelector('.bor-value');
    const restoreButton = blockToRestore.querySelector('.delete-button');

    blockToRestore.style.backgroundColor = ''; // сбросить фоновый цвет блока
    valueInput.readOnly = false;
    // Установить значение из data-value атрибута, если он существует
    valueInput.value = blockToRestore.dataset.value ? blockToRestore.dataset.value : "";

    restoreButton.textContent = translations.deleteButton;
    restoreButton.onclick = function() { deleteElement(restoreButton); };
    blockToDelete.dataset.delete = 'False';
}

function moveUp(element) {
    const currentBlock = element.closest('.key-box');
    const previousBlock = currentBlock.previousElementSibling;
    if (previousBlock && previousBlock.classList.contains('key-box')) {
        currentBlock.parentNode.insertBefore(currentBlock, previousBlock);
    }
}

function moveDown(element) {
    const currentBlock = element.closest('.key-box');
    const nextBlock = currentBlock.nextElementSibling;
    if (nextBlock && nextBlock.classList.contains('key-box')) {
        currentBlock.parentNode.insertBefore(nextBlock, currentBlock);
    }
}

async function getXDR() {
    const server = new StellarSdk.Server('https://horizon.stellar.org');
    let account = await server.loadAccount(document.getElementById('importInput').value);
    let transaction = new StellarSdk.TransactionBuilder(account, {
        fee: 10000,
        networkPassphrase: StellarSdk.Networks.TESTNET
    });

    let dictionary = {};

    document.querySelectorAll('.key-box[data-delete="True"]').forEach(box => {
        const key = box.dataset.key;
        transaction.addOperation(StellarSdk.Operation.manageData({ name: key, value: null }));
    });

    // Sort boxes: existing (with data-key) first, then new (without data-key)
    const allBoxes = Array.from(document.querySelectorAll('.key-box'));
    allBoxes.sort((a, b) => {
        const aHasKey = a.dataset.key ? 1 : 0;
        const bHasKey = b.dataset.key ? 1 : 0;
        return bHasKey - aHasKey; // boxes with data-key come first
    });

    allBoxes.forEach(box => {
        if (box.dataset.delete === 'True') return;

        const keyInput = box.querySelector('.bor-key').value;
        const valueInput = box.querySelector('.bor-value').value;
        const originalKey = box.dataset.key;
        const originalValue = box.dataset.value;

        let finalKey = keyInput;
        let counter = 1;

        const match = keyInput.match(/(\D+)(\d*)$/);
        const baseKey = match[1];
        const initialSuffix = match[2] ? parseInt(match[2], 10) : 1;

        if (dictionary[finalKey]) {
            while (dictionary[finalKey]) {
                finalKey = baseKey + counter;
                counter++;
            }
        }
        dictionary[finalKey] = true;

        if (originalKey && (originalKey !== finalKey || originalValue !== valueInput)) {
            if (originalKey !== finalKey && !dictionary[originalKey]) {
                transaction.addOperation(StellarSdk.Operation.manageData({ name: originalKey, value: null }));
            }
            transaction.addOperation(StellarSdk.Operation.manageData({ name: finalKey, value: valueInput }));
        } else if (!originalKey) {
            transaction.addOperation(StellarSdk.Operation.manageData({ name: finalKey, value: valueInput }));
        }
    });

    const builtTx = transaction.setTimeout(60*60*72).build();
    const xdr = builtTx.toXDR();
    document.getElementById('xdr').value = xdr;
}

function filterData() {
    const filterText = document.getElementById('filterInput').value.toLowerCase();
    const keyBoxes = document.querySelectorAll('.key-box');
    const filterButton = document.getElementById('filterButton');
    
    // Добавляем класс is-loading к кнопке фильтра
    filterButton.classList.add('is-loading');
    
    // Если фильтр пустой, показываем все блоки
    if (filterText === '') {
        keyBoxes.forEach(box => {
            box.classList.remove('is-hidden');
        });
        filterButton.classList.remove('is-loading');
        return;
    }
    
    // Проверяем каждый блок на соответствие фильтру
    keyBoxes.forEach(box => {
        const keyInput = box.querySelector('.bor-key').value.toLowerCase();
        const valueInput = box.querySelector('.bor-value').value.toLowerCase();
        
        // Если текст фильтра содержится в ключе или значении, показываем блок, иначе скрываем
        if (keyInput.includes(filterText) || valueInput.includes(filterText)) {
            box.classList.remove('is-hidden');
        } else {
            box.classList.add('is-hidden');
        }
    });
    
    // Убираем класс is-loading с кнопки фильтра
    filterButton.classList.remove('is-loading');
}

document.addEventListener('DOMContentLoaded', function() {
    const input = document.getElementById('importInput').value;
    if (input.length === 56) {
        importData();
    }
    
    // Добавляем обработчик события нажатия клавиши Enter в поле фильтра
    const filterInput = document.getElementById('filterInput');
    if (filterInput) {
        filterInput.addEventListener('keydown', function(event) {
            // Проверяем, была ли нажата клавиша Enter (код 13)
            if (event.keyCode === 13 || event.key === 'Enter') {
                // Предотвращаем стандартное действие (отправку формы, если она есть)
                event.preventDefault();
                // Вызываем функцию фильтрации
                filterData();
            }
        });
    }
});
