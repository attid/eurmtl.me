(function (global) {
    const DEFAULT_LABELS = {
        text: 'Decode to Text',
        json: 'Decode to JSON',
    };

    const loadXdrJsonModule = (() => {
        let modulePromise = null;
        return async () => {
            if (!modulePromise) {
                modulePromise = (async () => {
                    const module = await import('https://esm.sh/@stellar/stellar-xdr-json');
                    const initFn = module.default || module.init;
                    if (typeof initFn === 'function') {
                        await initFn();
                    }
                    return module;
                })().catch((error) => {
                    modulePromise = null;
                    throw error;
                });
            }
            return modulePromise;
        };
    })();

    function escapeHtml(value) {
        return value
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function highlightJson(jsonString) {
        const escaped = escapeHtml(jsonString);
        const highlighted = escaped.replace(/("(?:\\.|[^"])*"\s*:|"(?:\\.|[^"])*"|\b(?:true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g, (match) => {
            if (match.endsWith(':')) {
                return `<span class="text-info">${match}</span>`;
            }
            if (match.startsWith('"')) {
                return `<span class="text-success">${match}</span>`;
            }
            if (match === 'true' || match === 'false') {
                return `<span class="text-warning">${match}</span>`;
            }
            if (match === 'null') {
                return `<span class="text-muted">${match}</span>`;
            }
            return `<span class="text-primary">${match}</span>`;
        });

        return highlighted
            .replace(/\n/g, '<br>')
            .replace(/ {2}/g, '&nbsp;&nbsp;');
    }

    async function decodeXdrToJsonHtml(xdr) {
        if (!xdr || !xdr.trim()) {
            throw new Error('Transaction body is empty');
        }

        const module = await loadXdrJsonModule();
        const decodeFn = module.decode;
        if (typeof decodeFn !== 'function') {
            throw new Error('Decode function is unavailable');
        }

        const decoded = decodeFn('TransactionEnvelope', xdr.trim());
        let formattedJson;
        if (typeof decoded === 'string') {
            try {
                formattedJson = JSON.stringify(JSON.parse(decoded), null, 2);
            } catch (parseError) {
                formattedJson = decoded;
            }
        } else {
            formattedJson = JSON.stringify(decoded, null, 2);
        }

        const highlighted = highlightJson(formattedJson);
        return `<code class="json-output d-block tx-body text-break">${highlighted}</code>`;
    }

    function resolveElement(target) {
        if (!target) {
            return null;
        }
        if (typeof target === 'string') {
            return document.querySelector(target);
        }
        if (target instanceof Element) {
            return target;
        }
        return null;
    }

    function updateButtonMode(button, mode, labels) {
        if (!button) {
            return;
        }
        button.dataset.mode = mode;
        const labelNode = button.querySelector('[data-role="decode-label"]');
        const label = (labels && labels[mode]) || DEFAULT_LABELS[mode] || '';
        if (labelNode) {
            labelNode.textContent = label;
        } else {
            button.textContent = label;
        }
    }

    function resolveContext(config, callerName) {
        const source = callerName || 'toggleXdrDecode';

        if (!config) {
            console.warn(`${source}: configuration is required`);
            return null;
        }

        const button = resolveElement(config.button || config.buttonSelector);
        const responseCard = resolveElement(config.responseCard || config.responseCardSelector);
        const responseDiv = resolveElement(config.responseDiv || config.responseDivSelector);

        if (!button || !responseCard || !responseDiv) {
            console.warn(`${source}: unable to resolve required elements`);
            return null;
        }

        if (typeof config.decodeText !== 'function') {
            console.warn(`${source}: decodeText callback is required`);
            return null;
        }
        if (typeof config.getXdr !== 'function') {
            console.warn(`${source}: getXdr callback is required`);
            return null;
        }

        const labels = Object.assign({}, DEFAULT_LABELS, config.labels || {});

        if (!button.dataset.mode) {
            button.dataset.mode = 'text';
        }
        updateButtonMode(button, button.dataset.mode, labels);

        return {
            button,
            responseCard,
            responseDiv,
            labels,
            config,
            useJquery: typeof global.jQuery === 'function',
        };
    }

    async function performToggle(context) {
        const { button, responseCard, responseDiv, labels, config, useJquery } = context;

        if (button.dataset.loading === 'true') {
            return;
        }

        button.dataset.loading = 'true';
        button.disabled = true;

        const mode = button.dataset.mode || 'text';

        try {
            if (mode === 'text') {
                const html = await config.decodeText();
                if (!html) {
                    if (typeof config.onEmptyText === 'function') {
                        config.onEmptyText();
                    } else if (typeof global.showToast === 'function') {
                        global.showToast('Декодированный текст отсутствует', 'warning');
                    }
                    return;
                }

                if (useJquery) {
                    global.jQuery(responseDiv).html(html);
                    global.jQuery(responseCard).hide().fadeIn();
                } else {
                    responseDiv.innerHTML = html;
                    responseCard.style.display = '';
                }

                updateButtonMode(button, 'json', labels);
            } else {
                const xdr = config.getXdr();
                if (!xdr || !xdr.trim()) {
                    if (typeof config.onMissingXdr === 'function') {
                        config.onMissingXdr();
                    } else if (typeof global.showToast === 'function') {
                        global.showToast('Transaction body is empty', 'danger');
                    }
                    return;
                }

                const jsonHtml = await decodeXdrToJsonHtml(xdr);

                if (useJquery) {
                    global.jQuery(responseDiv).html(jsonHtml);
                    global.jQuery(responseCard).hide().fadeIn();
                } else {
                    responseDiv.innerHTML = jsonHtml;
                    responseCard.style.display = '';
                }

                updateButtonMode(button, 'text', labels);
            }
        } catch (error) {
            console.error('There was a problem decoding the response:', error);
            if (typeof global.showToast === 'function') {
                global.showToast('Произошла ошибка при декодировании транзакции', 'danger');
            }
        } finally {
            button.disabled = false;
            button.dataset.loading = 'false';
        }
    }

    function setupXdrDecodeToggle(config) {
        const context = resolveContext(config, 'setupXdrDecodeToggle');
        if (!context) {
            return;
        }

        const { button } = context;
        button.addEventListener('click', () => {
            performToggle(context);
        });
    }

    async function toggleXdrDecode(config) {
        const context = resolveContext(config, 'toggleXdrDecode');
        if (!context) {
            return;
        }
        await performToggle(context);
    }

    global.setupXdrDecodeToggle = setupXdrDecodeToggle;
    global.toggleXdrDecode = toggleXdrDecode;
})(window);
