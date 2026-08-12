#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pynacl>=1.5.0"]
# ///
#
# Run with uv (no manual pip installs):
#   uv run stellar_sealedbox.py encrypt --to G... --in plain.txt --out msg.b64
#   uv run stellar_sealedbox.py decrypt --me S... --in msg.b64 --out plain.txt
#
# Binary mode (no base64):
#   uv run stellar_sealedbox.py encrypt --to G... --in plain.bin --out msg.ssb --raw
#   uv run stellar_sealedbox.py decrypt --me S... --in msg.ssb --out plain.bin --raw
#
# Stdin/stdout:
#   echo "hi" | uv run stellar_sealedbox.py encrypt --to G... > msg.b64
#   cat msg.b64 | uv run stellar_sealedbox.py decrypt --me S...

import argparse
import base64
import sys
from typing import Tuple

from nacl.public import PublicKey, SealedBox
from nacl.signing import SigningKey
from nacl.bindings import crypto_sign_ed25519_pk_to_curve25519

# Stellar StrKey version bytes:
#   - ed25519 public key: 6 << 3  (0x30) => 'G...'
#   - ed25519 secret seed: 18 << 3 (0x90) => 'S...'
_VERSION_BYTE_G = 6 << 3
_VERSION_BYTE_S = 18 << 3


def _crc16_xmodem(data: bytes) -> int:
    crc = 0x0000
    for b in data:
        crc ^= (b << 8) & 0xFFFF
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def _strkey_decode(raw: str) -> Tuple[int, bytes]:
    s = raw.strip().upper()
    try:
        decoded = base64.b32decode(s, casefold=True)
    except Exception as e:
        raise ValueError(f"Invalid StrKey base32: {e}") from e

    if len(decoded) < 3:
        raise ValueError("StrKey too short")

    version = decoded[0]
    payload_plus = decoded[:-2]
    checksum_le = decoded[-2:]
    expected = _crc16_xmodem(payload_plus).to_bytes(2, "little")
    if checksum_le != expected:
        raise ValueError("Bad StrKey checksum")

    payload = decoded[1:-2]
    return version, payload


def stellar_G_to_ed25519_public(g: str) -> bytes:
    version, payload = _strkey_decode(g)
    if version != _VERSION_BYTE_G:
        raise ValueError("Expected Stellar public key (G...)")
    if len(payload) != 32:
        raise ValueError("Bad public key payload length (expected 32 bytes)")
    return payload


def stellar_S_to_ed25519_seed(s: str) -> bytes:
    version, payload = _strkey_decode(s)
    if version != _VERSION_BYTE_S:
        raise ValueError("Expected Stellar secret seed (S...)")
    if len(payload) != 32:
        raise ValueError("Bad secret seed payload length (expected 32 bytes)")
    return payload


def stellar_G_to_curve25519_public(g: str) -> PublicKey:
    ed_pk = stellar_G_to_ed25519_public(g)
    curve_pk = crypto_sign_ed25519_pk_to_curve25519(ed_pk)
    return PublicKey(curve_pk)


def stellar_S_to_curve25519_private(s: str):
    seed = stellar_S_to_ed25519_seed(s)
    return SigningKey(seed).to_curve25519_private_key()


def encrypt_to_stellar_G(recipient_g: str, plaintext: bytes) -> bytes:
    recipient_curve_pk = stellar_G_to_curve25519_public(recipient_g)
    return SealedBox(recipient_curve_pk).encrypt(plaintext)


def decrypt_with_stellar_S(secret_s: str, ciphertext: bytes) -> bytes:
    recipient_curve_sk = stellar_S_to_curve25519_private(secret_s)
    return SealedBox(recipient_curve_sk).decrypt(ciphertext)


def _read_all(path: str | None) -> bytes:
    if path:
        with open(path, "rb") as f:
            return f.read()
    return sys.stdin.buffer.read()


def _write_all(path: str | None, data: bytes) -> None:
    if path:
        with open(path, "wb") as f:
            f.write(data)
    else:
        sys.stdout.buffer.write(data)


def main() -> int:
    p = argparse.ArgumentParser(
        description="SealedBox encryption using Stellar keys (Ed25519->X25519)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser(
        "encrypt", help="Encrypt to recipient Stellar public key (G...)"
    )
    pe.add_argument("--to", required=True, help="Recipient Stellar public key (G...)")
    pe.add_argument(
        "--in", dest="inp", default=None, help="Input file (default: stdin)"
    )
    pe.add_argument(
        "--out", dest="out", default=None, help="Output file (default: stdout)"
    )
    pe.add_argument(
        "--raw", action="store_true", help="Output raw binary (default: base64)"
    )

    pd = sub.add_parser("decrypt", help="Decrypt with Stellar secret seed (S...)")
    pd.add_argument("--me", required=True, help="Your Stellar secret seed (S...)")
    pd.add_argument(
        "--in", dest="inp", default=None, help="Input file (default: stdin)"
    )
    pd.add_argument(
        "--out", dest="out", default=None, help="Output file (default: stdout)"
    )
    pd.add_argument(
        "--raw", action="store_true", help="Input is raw binary (default: base64)"
    )

    args = p.parse_args()

    if args.cmd == "encrypt":
        pt = _read_all(args.inp)
        ct = encrypt_to_stellar_G(args.to, pt)
        if args.raw:
            _write_all(args.out, ct)
        else:
            _write_all(args.out, base64.b64encode(ct) + b"\n")
        return 0

    if args.cmd == "decrypt":
        data = _read_all(args.inp)
        if args.raw:
            ct = data
        else:
            ct = base64.b64decode(data.strip())
        pt = decrypt_with_stellar_S(args.me, ct)
        _write_all(args.out, pt)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
