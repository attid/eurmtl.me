# Sign Tools Firebird Segfault Mitigation

## Goal

Reduce `/sign_tools/<hash>` database pressure for large transactions and update
the Firebird client stack where practical.

## Evidence

- `GET /sign_tools/d547f5e9590a41344256c5cbb4ce2f0caa54309ca0869b789f8785a6048377d4`
  returned `200` locally via production HTTP but took about 21 seconds and
  produced a 156 KB page.
- `GET /remote/get_xdr/<same hash>` returned in about 1 second with a 12.6 KB
  payload.
- The rendered sign page had 27 unique Stellar public keys and 165 table rows.
- The server incident showed `exit 139` and a kernel segfault in
  `libfbclient.so.4.0.5`, not a Python traceback.

## Root Cause Hypothesis

The XDR itself is not the slow path. `/sign_tools/<hash>` expands signer details
with N+1 database queries and opens a nested DB session via `check_user_in_sign`.
Several concurrent page loads can drive many Firebird client operations through
the async dialect/thread bridge and hit a native `libfbclient` crash.

## Scope

- Do not reduce `max_overflow` or otherwise throttle normal traffic.
- Keep public route behavior and template contract unchanged.
- Use bulk repository queries for signer/signature lookups.
- Reuse the current request DB session for permission checks.
- Update Python Firebird packages in `uv.lock`.
- Investigate whether the Docker base can install a Firebird 5 client package.

## Files

- Modify `infrastructure/repositories/transaction_repository.py`.
- Modify `services/transaction_service.py`.
- Modify `tests/services/test_transaction_service.py`.
- Modify `pyproject.toml` / `uv.lock` if dependency resolution updates them.
- Modify `Dockerfile` only if Firebird 5 client is available in the base image.

## Tasks

1. Done: Add failing service tests showing transaction details use bulk repository
   calls instead of per-signer DB calls.
2. Done: Add repository bulk methods for:
   - signers by public key list;
   - visible signatures for a transaction keyed by public key;
   - latest signature date per signer;
   - latest signature date per signer/source pair.
3. Done: Move `check_user_in_sign` logic into `TransactionService` for detail/refresh
   paths so it reuses the existing DB session.
4. Done: Update `get_transaction_details()` to use the bulk maps.
5. Done: Upgrade Firebird Python packages with `uv lock --upgrade-package`.
6. Done: Check Docker package availability for Firebird 5 client. Debian
   `python:3.12-slim` currently exposes `libfbclient2` / `firebird-dev` at
   `4.0.5.3140.ds6-17+deb13u1`; no Firebird 5 client package is available
   without adding an external package source or vendoring an upstream tarball.
7. Done: Run focused and changed-file checks.

## Verification

- `uv run --extra dev pytest tests/services/test_transaction_service.py -q --no-cov`
- `just check-changed`
- `uv tree --package sqlalchemy-firebird-async`
- Docker package availability check for Firebird client version.
- `docker build --build-arg GIT_COMMIT=$(git rev-parse --short HEAD) --build-arg CACHEBUST=$(git rev-parse HEAD)-sign-tools -t mtl_sing_tools:sign-tools-check .`
- `just check` currently fails before tests on unrelated baseline formatting:
  `services/xdr_parser.py` would be reformatted and is not changed by this task.
