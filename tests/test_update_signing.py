from __future__ import annotations

import base64


def test_default_update_signing_key_rotation_keeps_legacy_verification_key() -> None:
    from shared.update_signing import (
        DEFAULT_UPDATE_PUBLIC_KEYS,
        DEFAULT_UPDATE_SIGNING_KEY_ID,
        LEGACY_UPDATE_SIGNING_KEY_ID,
    )

    assert DEFAULT_UPDATE_SIGNING_KEY_ID == "datalab-release-2026-06"
    assert LEGACY_UPDATE_SIGNING_KEY_ID == "datalab-release-2026-05"
    assert DEFAULT_UPDATE_PUBLIC_KEYS[LEGACY_UPDATE_SIGNING_KEY_ID] == (
        "rpgclKq+R6k3tCSy5zwt4WNlYddB8BX6O3c4KvN8xNA="
    )
    assert DEFAULT_UPDATE_PUBLIC_KEYS[DEFAULT_UPDATE_SIGNING_KEY_ID] == (
        "NjugTQCtQmSXUKWpxCTyHA1m6jQWhZzIcOTqYC9+Wu8="
    )
    assert len(base64.b64decode(DEFAULT_UPDATE_PUBLIC_KEYS[DEFAULT_UPDATE_SIGNING_KEY_ID])) == 32
