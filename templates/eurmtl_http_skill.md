---
name: eurmtl-http
description: Use when an agent needs the public EURMTL HTTP routes, machine entrypoints, and request patterns without relying on browser-only pages.
---

# EURMTL HTTP

## Overview
Use `GET /llms.txt` first for a compact route map, then use this skill when the task needs concrete request patterns and endpoint selection.

## Discovery
- `GET /llms.txt` for the short machine overview
- `GET /.well-known/api-catalog` for API discovery metadata
- `GET /openapi.json` for a compact machine-readable schema
- `GET /.well-known/stellar.toml` for Stellar ecosystem metadata

## Preferred Routes
- Use `POST /remote/decode` to decode Stellar XDR from JSON body `{"xdr":"<base64>"}`.
- Use `POST /remote/update_signature` to submit signed XDR.
- Use `POST /remote/sep07/add`, `POST /remote/sep07/parse-uri`, and `POST /remote/sep07/submit-signed` for SEP-7 URI workflows.
- Use `POST /remote/sep07/auth/init` and `GET /remote/sep07/auth/status/<nonce>/<salt>` for SEP-7 auth polling flows.
- Use `POST /lab/build_xdr` for structured XDR construction and `POST /lab/xdr_to_json` for reverse conversion.
- Use `GET /federation`, `GET /sep6/info`, and `GET /.well-known/stellar.toml` for federation and wallet integration metadata.

## Boundaries
- Prefer machine routes over HTML pages such as `/lab`, `/contracts`, or `/sign_tools` when an API route exists.
- Treat `/authorize`, `/err`, `/log`, `/restart`, and `/updatedb` as service or operator routes, not agent entrypoints.
- Some `/remote/*` routes require `Authorization: Bearer <token>`.

## Response Expectations
- `200` means success.
- `400` means invalid input.
- `401` means missing or invalid bearer token.
- `404` means missing object or unsupported route.
