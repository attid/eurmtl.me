# SealedBox Binary Decrypt Result

## Goal

Fix `/sealedbox` decrypt UI so binary plaintext such as PDF or archive bytes is
not rendered as corrupt text after successful decrypt.

## Root Cause

`static/js/sealedbox.js` always decodes decrypted bytes with `TextDecoder()` and
writes the result into the textarea. This is only valid for text payloads. Binary
payloads decrypt correctly, but the UI renders arbitrary bytes as text.

## Scope

- Keep the sealed box algorithm unchanged.
- Keep all crypto in the browser.
- Detect whether decrypted plaintext is safe UTF-8 text before showing it.
- For binary plaintext, keep the bytes for download and show a status message
  instead of corrupt text.
- Preserve/download a reasonable output filename when possible.

## Files

- Modify `tests/routers/test_index.py`.
- Modify `templates/tabler_sealedbox.html`.
- Modify `static/js/sealedbox.js`.

## Tasks

1. Done: Add a failing route/template test that requires a dedicated result status
   element for binary/text decrypt outcomes.
2. Done: Update the template with that status element.
3. Done: Update browser JS:
   - decode text with fatal UTF-8 mode;
   - reject text previews with excessive control characters;
   - for binary data, show a short status message and enable download;
   - derive `file.ext` from `file.ext.ssb` when decrypting an encrypted file.
4. Done: Verify focused route tests.
5. Done: Verify JS-to-Python and Python-to-JS compatibility still passes for binary
   payloads.
6. Done: Commit and push.

## Verification

- `uv run --extra dev pytest tests/routers/test_index.py::test_sealedbox_page_exposes_browser_only_crypto_tool -q --no-cov`
- JS/Python compatibility smoke test with ZIP/PDF-like binary bytes.
- `uv run --extra dev pytest tests/routers/test_index.py -q --no-cov`
- `just check-changed`
