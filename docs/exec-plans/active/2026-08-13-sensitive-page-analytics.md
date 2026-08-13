# Sensitive page analytics

## Goal

Prevent third-party analytics JavaScript from running on pages where users enter or generate Stellar secret keys, while keeping a Yandex image pixel for basic pageview tracking.

## Scope

- Add configurable analytics head/body blocks to `templates/tabler_base.html`.
- Use pixel-only analytics in Tabler templates that handle secret seeds/private keys:
  - `templates/tabler_sealedbox.html`
  - `templates/tabler_addr.html`
  - `templates/tabler_laboratory.html`
  - `templates/tabler_sign_sign.html`
- Add route tests that assert those pages do not include the Yandex Metrica JavaScript URL.

## Out Of Scope

- Replacing analytics with a first-party server-side counter.
- Changing non-Tabler standalone pages that do not include the Tabler base analytics snippet.

## Verification

- `uv run --extra dev pytest tests/routers/test_index.py::test_sealedbox_page_disables_third_party_analytics tests/routers/test_index.py::test_address_generator_disables_third_party_analytics tests/routers/test_laboratory.py::test_lab_root_disables_third_party_analytics tests/routers/test_sign_tools.py::test_sign_tools_add_get tests/routers/test_sign_tools.py::test_sign_tools_show_transaction -q --no-cov`
- `uv run --extra dev pytest tests/routers/test_index.py tests/routers/test_laboratory.py tests/routers/test_sign_tools.py -q --no-cov`
- `git diff --check`
- `just check-changed`
