(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.EurmtlSealedBox = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const BASE64_VARIANT = "ORIGINAL";

  function toUint8Array(value) {
    return value instanceof Uint8Array ? value : new Uint8Array(value);
  }

  function trimKey(value) {
    return String(value || "").trim();
  }

  function getBase64Variant(sodium) {
    return sodium.base64_variants[BASE64_VARIANT];
  }

  function bytesToBase64(sodium, bytes) {
    return sodium.to_base64(toUint8Array(bytes), getBase64Variant(sodium));
  }

  function base64ToBytes(sodium, value) {
    return sodium.from_base64(String(value || "").trim(), getBase64Variant(sodium));
  }

  function publicKeyToCurve25519(sodium, StellarSdk, publicKey) {
    const key = trimKey(publicKey);
    if (!StellarSdk.StrKey.isValidEd25519PublicKey(key)) {
      throw new Error("Expected Stellar public key (G...)");
    }
    const ed25519Public = StellarSdk.StrKey.decodeEd25519PublicKey(key);
    return sodium.crypto_sign_ed25519_pk_to_curve25519(toUint8Array(ed25519Public));
  }

  function publicKeyFromSecret(StellarSdk, secretSeed) {
    const key = trimKey(secretSeed);
    if (!StellarSdk.StrKey.isValidEd25519SecretSeed(key)) {
      throw new Error("Expected Stellar secret seed (S...)");
    }
    return StellarSdk.Keypair.fromSecret(key).publicKey();
  }

  function secretSeedToCurve25519(sodium, StellarSdk, secretSeed) {
    const key = trimKey(secretSeed);
    if (!StellarSdk.StrKey.isValidEd25519SecretSeed(key)) {
      throw new Error("Expected Stellar secret seed (S...)");
    }
    const seed = StellarSdk.StrKey.decodeEd25519SecretSeed(key);
    const ed25519Keypair = sodium.crypto_sign_seed_keypair(toUint8Array(seed));
    return sodium.crypto_sign_ed25519_sk_to_curve25519(ed25519Keypair.privateKey);
  }

  function resolveRecipientPublicKey(StellarSdk, publicOrSecretKey) {
    const key = trimKey(publicOrSecretKey);
    if (StellarSdk.StrKey.isValidEd25519PublicKey(key)) {
      return key;
    }
    if (StellarSdk.StrKey.isValidEd25519SecretSeed(key)) {
      return publicKeyFromSecret(StellarSdk, key);
    }
    throw new Error("Expected Stellar public key (G...) or secret seed (S...)");
  }

  function encryptToStellarKey(sodium, StellarSdk, publicOrSecretKey, plaintext) {
    const publicKey = resolveRecipientPublicKey(StellarSdk, publicOrSecretKey);
    const curvePublic = publicKeyToCurve25519(sodium, StellarSdk, publicKey);
    return sodium.crypto_box_seal(toUint8Array(plaintext), curvePublic);
  }

  function decryptWithStellarSecret(sodium, StellarSdk, secretSeed, ciphertext) {
    const publicKey = publicKeyFromSecret(StellarSdk, secretSeed);
    const curvePublic = publicKeyToCurve25519(sodium, StellarSdk, publicKey);
    const curveSecret = secretSeedToCurve25519(sodium, StellarSdk, secretSeed);
    return sodium.crypto_box_seal_open(toUint8Array(ciphertext), curvePublic, curveSecret);
  }

  function generateStellarKeypair(StellarSdk) {
    const keypair = StellarSdk.Keypair.random();
    return {
      publicKey: keypair.publicKey(),
      secretKey: keypair.secret(),
    };
  }

  function textToBytes(text) {
    return new TextEncoder().encode(text);
  }

  function bytesToText(bytes) {
    return new TextDecoder("utf-8", { fatal: true }).decode(toUint8Array(bytes));
  }

  function isDisplayableText(text) {
    if (text.length === 0) {
      return true;
    }
    let controlCharacters = 0;
    for (const character of text) {
      const code = character.charCodeAt(0);
      if (code < 32 && code !== 9 && code !== 10 && code !== 13) {
        controlCharacters += 1;
      }
    }
    return controlCharacters / text.length < 0.02;
  }

  function decodeDisplayText(bytes) {
    try {
      const text = bytesToText(bytes);
      return isDisplayableText(text) ? text : null;
    } catch (_error) {
      return null;
    }
  }

  function decryptedFilename(file) {
    if (!file || !file.name) {
      return "sealedbox-output.bin";
    }
    if (file.name.endsWith(".ssb")) {
      return file.name.slice(0, -4) || "sealedbox-output.bin";
    }
    return `${file.name}.decrypted`;
  }

  function encryptedFilename(file) {
    if (!file || !file.name) {
      return "sealedbox.ssb";
    }
    return `${file.name}.ssb`;
  }

  async function readFileInput(input) {
    if (!input.files || input.files.length === 0) {
      return null;
    }
    return new Uint8Array(await input.files[0].arrayBuffer());
  }

  function notify(message, type) {
    if (typeof showToast === "function") {
      showToast(message, type || "info");
      return;
    }
    console.log(`${type || "info"}: ${message}`);
  }

  function formatBytes(size) {
    if (size < 1024) {
      return `${size} B`;
    }
    if (size < 1024 * 1024) {
      return `${(size / 1024).toFixed(1)} KB`;
    }
    return `${(size / 1024 / 1024).toFixed(2)} MB`;
  }

  function setActiveInputMode(textButton, fileButton, textPanel, filePanel, mode) {
    const textMode = mode === "text";
    textButton.classList.toggle("btn-primary", textMode);
    textButton.classList.toggle("btn-outline-primary", !textMode);
    fileButton.classList.toggle("btn-primary", !textMode);
    fileButton.classList.toggle("btn-outline-primary", textMode);
    textPanel.classList.toggle("d-none", !textMode);
    filePanel.classList.toggle("d-none", textMode);
  }

  function setButtonBusy(button, isBusy) {
    button.disabled = isBusy;
    const spinner = button.querySelector(".spinner-border");
    if (spinner) {
      spinner.classList.toggle("d-none", !isBusy);
    }
  }

  function setKeyValidation(input, hint, validator, emptyText) {
    const value = trimKey(input.value);
    input.classList.remove("is-valid", "is-invalid");
    hint.classList.remove("text-success", "text-danger");
    if (!value) {
      hint.textContent = emptyText;
      return false;
    }
    if (validator(value)) {
      input.classList.add("is-valid");
      hint.classList.add("text-success");
      hint.textContent = "Key looks valid.";
      return true;
    }
    input.classList.add("is-invalid");
    hint.classList.add("text-danger");
    hint.textContent = value.length < 56 ? "Expected 56 Stellar StrKey characters." : "Stellar key checksum is invalid.";
    return false;
  }

  function setFileChip(state, prefix, file) {
    const chip = state[`${prefix}FileChip`];
    const input = state[`${prefix}File`];
    if (!file) {
      input.value = "";
      chip.classList.remove("is-visible");
      state[`${prefix}FileName`].textContent = "";
      state[`${prefix}FileSize`].textContent = "";
      return;
    }
    state[`${prefix}FileName`].textContent = file.name;
    state[`${prefix}FileSize`].textContent = formatBytes(file.size);
    chip.classList.add("is-visible");
  }

  function attachDropzone(rootDocument, state, prefix) {
    const dropzone = state[`${prefix}FileDropzone`];
    const input = state[`${prefix}File`];
    const clear = state[`${prefix}FileClear`];
    const setFile = (file) => {
      if (!file) {
        return;
      }
      if (typeof DataTransfer !== "undefined") {
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
      }
      setFileChip(state, prefix, file);
    };

    input.addEventListener("change", () => setFileChip(state, prefix, input.files?.[0] || null));
    clear.addEventListener("click", () => setFileChip(state, prefix, null));
    dropzone.addEventListener("dragover", (event) => {
      event.preventDefault();
      dropzone.classList.add("is-over");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-over"));
    dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-over");
      setFile(event.dataTransfer?.files?.[0]);
    });
    rootDocument.addEventListener("sealedbox:clear", () => setFileChip(state, prefix, null));
  }

  function setResult(state, text, bytes, filename) {
    state.resultBytes = bytes ? toUint8Array(bytes) : null;
    state.resultFilename = filename || "sealedbox.bin";
    state.result.value = text;
    state.resultPanel.classList.remove("d-none");
    state.downloadButton.disabled = !state.resultBytes;
  }

  function wireUi(rootDocument, sodium, StellarSdk) {
    const state = {
      publicKey: rootDocument.getElementById("sealedbox-public-key"),
      publicKeyHint: rootDocument.getElementById("sealedbox-public-key-hint"),
      secretKey: rootDocument.getElementById("sealedbox-secret-key"),
      secretKeyHint: rootDocument.getElementById("sealedbox-secret-key-hint"),
      plainText: rootDocument.getElementById("sealedbox-plain-text"),
      plainTextButton: rootDocument.getElementById("sealedbox-plain-text-mode"),
      plainFileButton: rootDocument.getElementById("sealedbox-plain-file-mode"),
      plainTextPanel: rootDocument.getElementById("sealedbox-plain-text-panel"),
      plainFilePanel: rootDocument.getElementById("sealedbox-plain-file-panel"),
      plainFile: rootDocument.getElementById("sealedbox-plain-file"),
      plainFileDropzone: rootDocument.getElementById("sealedbox-plain-file-dropzone"),
      plainFileChip: rootDocument.getElementById("sealedbox-plain-file-chip"),
      plainFileName: rootDocument.getElementById("sealedbox-plain-file-name"),
      plainFileSize: rootDocument.getElementById("sealedbox-plain-file-size"),
      plainFileClear: rootDocument.getElementById("sealedbox-plain-file-clear"),
      cipherText: rootDocument.getElementById("sealedbox-cipher-text"),
      cipherTextButton: rootDocument.getElementById("sealedbox-cipher-text-mode"),
      cipherFileButton: rootDocument.getElementById("sealedbox-cipher-file-mode"),
      cipherTextPanel: rootDocument.getElementById("sealedbox-cipher-text-panel"),
      cipherFilePanel: rootDocument.getElementById("sealedbox-cipher-file-panel"),
      cipherFile: rootDocument.getElementById("sealedbox-cipher-file"),
      cipherFileDropzone: rootDocument.getElementById("sealedbox-cipher-file-dropzone"),
      cipherFileChip: rootDocument.getElementById("sealedbox-cipher-file-chip"),
      cipherFileName: rootDocument.getElementById("sealedbox-cipher-file-name"),
      cipherFileSize: rootDocument.getElementById("sealedbox-cipher-file-size"),
      cipherFileClear: rootDocument.getElementById("sealedbox-cipher-file-clear"),
      resultPanel: rootDocument.getElementById("sealedbox-result-panel"),
      result: rootDocument.getElementById("sealedbox-result"),
      resultStatus: rootDocument.getElementById("sealedbox-result-status"),
      downloadButton: rootDocument.getElementById("sealedbox-download-result"),
      resultBytes: null,
      resultFilename: "sealedbox.bin",
    };

    state.plainTextButton.addEventListener("click", () =>
      setActiveInputMode(state.plainTextButton, state.plainFileButton, state.plainTextPanel, state.plainFilePanel, "text"),
    );
    state.plainFileButton.addEventListener("click", () =>
      setActiveInputMode(state.plainTextButton, state.plainFileButton, state.plainTextPanel, state.plainFilePanel, "file"),
    );
    state.cipherTextButton.addEventListener("click", () =>
      setActiveInputMode(
        state.cipherTextButton,
        state.cipherFileButton,
        state.cipherTextPanel,
        state.cipherFilePanel,
        "text",
      ),
    );
    state.cipherFileButton.addEventListener("click", () =>
      setActiveInputMode(
        state.cipherTextButton,
        state.cipherFileButton,
        state.cipherTextPanel,
        state.cipherFilePanel,
        "file",
      ),
    );
    attachDropzone(rootDocument, state, "plain");
    attachDropzone(rootDocument, state, "cipher");

    state.publicKey.addEventListener("input", () =>
      setKeyValidation(
        state.publicKey,
        state.publicKeyHint,
        StellarSdk.StrKey.isValidEd25519PublicKey,
        "Starts with G, 56 characters.",
      ),
    );
    state.secretKey.addEventListener("input", () =>
      setKeyValidation(
        state.secretKey,
        state.secretKeyHint,
        StellarSdk.StrKey.isValidEd25519SecretSeed,
        "Starts with S. It never leaves this tab.",
      ),
    );

    rootDocument.getElementById("sealedbox-secret-toggle").addEventListener("click", (event) => {
      const showSecret = state.secretKey.type === "password";
      state.secretKey.type = showSecret ? "text" : "password";
      event.currentTarget.innerHTML = showSecret ? '<i class="ti ti-eye-off"></i>' : '<i class="ti ti-eye"></i>';
    });

    rootDocument.getElementById("sealedbox-generate-key").addEventListener("click", () => {
      const keypair = generateStellarKeypair(StellarSdk);
      state.publicKey.value = keypair.publicKey;
      state.secretKey.value = keypair.secretKey;
      state.publicKey.dispatchEvent(new Event("input"));
      state.secretKey.dispatchEvent(new Event("input"));
      notify("Keypair generated", "success");
    });

    rootDocument.getElementById("sealedbox-public-from-secret").addEventListener("click", () => {
      try {
        state.publicKey.value = publicKeyFromSecret(StellarSdk, state.secretKey.value);
        notify("Public key derived", "success");
      } catch (error) {
        notify(error.message, "danger");
      }
    });

    rootDocument.getElementById("sealedbox-encrypt-button").addEventListener("click", async () => {
      const button = rootDocument.getElementById("sealedbox-encrypt-button");
      try {
        setButtonBusy(button, true);
        const fileMode = !state.plainFilePanel.classList.contains("d-none");
        const fileBytes = fileMode ? await readFileInput(state.plainFile) : null;
        const plaintext = fileBytes || textToBytes(state.plainText.value);
        const recipientKey = state.publicKey.value || state.secretKey.value;
        const ciphertext = encryptToStellarKey(sodium, StellarSdk, recipientKey, plaintext);
        const base64 = bytesToBase64(sodium, ciphertext);
        state.cipherText.value = base64;
        setResult(state, base64, ciphertext, encryptedFilename(state.plainFile.files?.[0]));
        state.resultStatus.textContent = `Encrypted ${plaintext.length} bytes. Download saves raw sealed box bytes.`;
        notify("Encrypted", "success");
      } catch (error) {
        notify(error.message, "danger");
      } finally {
        setButtonBusy(button, false);
      }
    });

    rootDocument.getElementById("sealedbox-decrypt-button").addEventListener("click", async () => {
      const button = rootDocument.getElementById("sealedbox-decrypt-button");
      try {
        setButtonBusy(button, true);
        const fileMode = !state.cipherFilePanel.classList.contains("d-none");
        const fileBytes = fileMode ? await readFileInput(state.cipherFile) : null;
        const ciphertext = fileBytes || base64ToBytes(sodium, state.cipherText.value);
        const plaintext = decryptWithStellarSecret(sodium, StellarSdk, state.secretKey.value, ciphertext);
        const text = decodeDisplayText(plaintext);
        const filename = decryptedFilename(state.cipherFile.files?.[0]);
        if (text === null) {
          setResult(
            state,
            `Decrypted ${plaintext.length} binary bytes. Use Download to save the file.`,
            plaintext,
            filename,
          );
        } else {
          setResult(state, text, plaintext, filename);
        }
        state.resultStatus.textContent =
          text === null
            ? `Binary result ready: ${plaintext.length} bytes.`
            : `Text result ready: ${plaintext.length} bytes.`;
        notify("Decrypted", "success");
      } catch (error) {
        notify(error.message, "danger");
      } finally {
        setButtonBusy(button, false);
      }
    });

    rootDocument.getElementById("sealedbox-clear-button").addEventListener("click", () => {
      state.publicKey.value = "";
      state.secretKey.value = "";
      state.plainText.value = "";
      state.cipherText.value = "";
      state.result.value = "";
      state.resultBytes = null;
      state.resultFilename = "sealedbox.bin";
      state.resultPanel.classList.add("d-none");
      state.downloadButton.disabled = true;
      state.resultStatus.textContent = "";
      rootDocument.dispatchEvent(new Event("sealedbox:clear"));
      state.publicKey.dispatchEvent(new Event("input"));
      state.secretKey.dispatchEvent(new Event("input"));
      notify("Cleared", "success");
    });

    rootDocument.getElementById("sealedbox-copy-result").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(state.result.value);
        notify("Copied", "success");
      } catch (error) {
        notify(error.message, "danger");
      }
    });

    state.downloadButton.addEventListener("click", () => {
      if (!state.resultBytes) {
        return;
      }
      const url = URL.createObjectURL(new Blob([state.resultBytes]));
      const link = rootDocument.createElement("a");
      link.href = url;
      link.download = state.resultFilename;
      link.click();
      URL.revokeObjectURL(url);
    });
  }

  async function initBrowser() {
    if (!document.getElementById("sealedbox-app")) {
      return;
    }
    try {
      await self.sodium.ready;
      wireUi(document, self.sodium, self.StellarSdk);
      notify("SealedBox crypto ready", "success");
    } catch (error) {
      notify(`Crypto initialization failed: ${error.message}`, "danger");
    }
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initBrowser);
    } else {
      initBrowser();
    }
  }

  return {
    base64ToBytes,
    bytesToBase64,
    decodeDisplayText,
    decryptWithStellarSecret,
    decryptedFilename,
    encryptedFilename,
    encryptToStellarKey,
    generateStellarKeypair,
    isDisplayableText,
    publicKeyFromSecret,
    publicKeyToCurve25519,
    resolveRecipientPublicKey,
    secretSeedToCurve25519,
  };
});
