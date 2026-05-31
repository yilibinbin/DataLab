"""Application-level signing for DataLab update manifests.

The signature proves that ``updates.json`` was produced by the DataLab release
key. It is intentionally separate from OS distribution trust such as Apple
Developer ID notarization or Windows Authenticode.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


SIGNATURE_FIELD = "signature"
SIGNATURE_ALGORITHM = "ed25519"
DEFAULT_UPDATE_SIGNING_KEY_ID = "datalab-release-2026-05"
DEFAULT_UPDATE_PUBLIC_KEYS = {
    DEFAULT_UPDATE_SIGNING_KEY_ID: "vZXl75fGsTbr4rkP4u2JrnBm9HIjkzcY3uiB1zn1du4=",
}


class UpdateSignatureError(ValueError):
    """Raised when an update manifest signature is missing or invalid."""


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in manifest.items() if key != SIGNATURE_FIELD}
    return json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sign_manifest(
    manifest: dict[str, Any],
    *,
    private_key_b64: str,
    key_id: str = DEFAULT_UPDATE_SIGNING_KEY_ID,
) -> dict[str, Any]:
    raw_key = _decode_b64(private_key_b64, "private key")
    if len(raw_key) != 32:
        raise UpdateSignatureError("ed25519 private key must contain 32 raw bytes")
    private_key = Ed25519PrivateKey.from_private_bytes(raw_key)
    signed = {key: value for key, value in manifest.items() if key != SIGNATURE_FIELD}
    signature = private_key.sign(canonical_manifest_bytes(signed))
    signed[SIGNATURE_FIELD] = {
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": key_id,
        "value": base64.b64encode(signature).decode("ascii"),
    }
    return signed


def verify_manifest_signature(
    manifest: dict[str, Any],
    *,
    public_keys: dict[str, str] | None = None,
    require_signature: bool = True,
) -> None:
    signature = manifest.get(SIGNATURE_FIELD)
    if signature is None and not require_signature:
        return
    if not isinstance(signature, dict):
        raise UpdateSignatureError("manifest signature is required")
    if signature.get("algorithm") != SIGNATURE_ALGORITHM:
        raise UpdateSignatureError("unsupported manifest signature algorithm")

    key_id = str(signature.get("key_id") or "")
    keys = public_keys or DEFAULT_UPDATE_PUBLIC_KEYS
    public_key_b64 = keys.get(key_id)
    if not public_key_b64:
        raise UpdateSignatureError("unknown manifest signing key")

    signature_value = signature.get("value")
    if not isinstance(signature_value, str) or not signature_value:
        raise UpdateSignatureError("manifest signature value is required")

    raw_public_key = _decode_b64(public_key_b64, "public key")
    if len(raw_public_key) != 32:
        raise UpdateSignatureError("ed25519 public key must contain 32 raw bytes")
    raw_signature = _decode_b64(signature_value, "signature")

    public_key = Ed25519PublicKey.from_public_bytes(raw_public_key)
    try:
        public_key.verify(raw_signature, canonical_manifest_bytes(manifest))
    except InvalidSignature as exc:
        raise UpdateSignatureError("manifest signature verification failed") from exc


def derive_public_key_b64(private_key_b64: str) -> str:
    raw_key = _decode_b64(private_key_b64, "private key")
    if len(raw_key) != 32:
        raise UpdateSignatureError("ed25519 private key must contain 32 raw bytes")
    private_key = Ed25519PrivateKey.from_private_bytes(raw_key)
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(public_key).decode("ascii")


def has_installable_assets(manifest: dict[str, Any]) -> bool:
    assets = manifest.get("assets")
    return isinstance(assets, dict) and any(isinstance(value, dict) for value in assets.values())


def _decode_b64(value: str, label: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:  # noqa: BLE001 - normalize crypto parser errors for UI/tests
        raise UpdateSignatureError(f"invalid base64 {label}") from exc
