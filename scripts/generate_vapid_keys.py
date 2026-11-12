"""Generate a VAPID key pair and a device enrollment token."""

from __future__ import annotations

import argparse
import base64
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIVATE_KEY = PROJECT_ROOT / "runtime" / "secrets" / "vapid_private.pem"
TOKEN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def b64url_no_padding(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def generate_enrollment_token(length: int = 8) -> str:
    return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(length))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Web Push VAPID keys")
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace the existing private key; all browsers must subscribe again afterward",
    )
    parser.add_argument(
        "--token-only",
        action="store_true",
        help="generate only a new enrollment token without touching the VAPID key",
    )
    parser.add_argument(
        "--token-length",
        type=int,
        choices=range(5, 9),
        default=8,
        help="enrollment token length from 5 to 8 characters (default: 8)",
    )
    args = parser.parse_args()

    if args.token_only:
        print(f"PUSH_ENROLLMENT_TOKEN={generate_enrollment_token(args.token_length)}")
        return 0

    if DEFAULT_PRIVATE_KEY.exists() and not args.force:
        parser.error(f"Private key already exists at {DEFAULT_PRIVATE_KEY}; use --force only to rotate it.")

    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )

    DEFAULT_PRIVATE_KEY.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_PRIVATE_KEY.write_bytes(private_pem)
    try:
        DEFAULT_PRIVATE_KEY.chmod(0o600)
    except OSError:
        pass

    print("VAPID key pair dibuat. Private key tersimpan lokal; jangan kirim atau unggah file itu.")
    print()
    print(f"VAPID_PUBLIC_KEY={b64url_no_padding(public_bytes)}")
    print("VAPID_PRIVATE_KEY_FILE=runtime/secrets/vapid_private.pem")
    print(f"PUSH_ENROLLMENT_TOKEN={generate_enrollment_token(args.token_length)}")
    print("VAPID_SUBJECT=mailto:admin@example.com")
    print()
    print("Salin nilai ke .env, ganti alamat email, lalu restart Flask.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
