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

  function setResult(state, text, bytes, filename) {
    state.resultBytes = bytes ? toUint8Array(bytes) : null;
    state.resultFilename = filename || "sealedbox.bin";
    state.result.value = text;
    state.downloadButton.disabled = !state.resultBytes;
  }

  function wireUi(rootDocument, sodium, StellarSdk) {
    const state = {
      publicKey: rootDocument.getElementById("sealedbox-public-key"),
      secretKey: rootDocument.getElementById("sealedbox-secret-key"),
      plainText: rootDocument.getElementById("sealedbox-plain-text"),
      plainFile: rootDocument.getElementById("sealedbox-plain-file"),
      cipherText: rootDocument.getElementById("sealedbox-cipher-text"),
      cipherFile: rootDocument.getElementById("sealedbox-cipher-file"),
      result: rootDocument.getElementById("sealedbox-result"),
      resultStatus: rootDocument.getElementById("sealedbox-result-status"),
      downloadButton: rootDocument.getElementById("sealedbox-download-result"),
      resultBytes: null,
      resultFilename: "sealedbox.bin",
    };

    rootDocument.getElementById("sealedbox-generate-key").addEventListener("click", () => {
      const keypair = generateStellarKeypair(StellarSdk);
      state.publicKey.value = keypair.publicKey;
      state.secretKey.value = keypair.secretKey;
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
      try {
        const fileBytes = await readFileInput(state.plainFile);
        const plaintext = fileBytes || textToBytes(state.plainText.value);
        const recipientKey = state.publicKey.value || state.secretKey.value;
        const ciphertext = encryptToStellarKey(sodium, StellarSdk, recipientKey, plaintext);
        const base64 = bytesToBase64(sodium, ciphertext);
        state.cipherText.value = base64;
        const filename = state.plainFile.files?.[0]?.name
          ? `${state.plainFile.files[0].name}.ssb`
          : "sealedbox.ssb";
        setResult(state, base64, ciphertext, filename);
        state.resultStatus.textContent = `Encrypted ${plaintext.length} bytes. Download saves raw sealed box bytes.`;
        notify("Encrypted", "success");
      } catch (error) {
        notify(error.message, "danger");
      }
    });

    rootDocument.getElementById("sealedbox-decrypt-button").addEventListener("click", async () => {
      try {
        const fileBytes = await readFileInput(state.cipherFile);
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
      }
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
    encryptToStellarKey,
    generateStellarKeypair,
    isDisplayableText,
    publicKeyFromSecret,
    publicKeyToCurve25519,
    resolveRecipientPublicKey,
    secretSeedToCurve25519,
  };
});
