"""Firmware signing key helpers shared by smac_sign.py and the container tool.

Key files use the PEM-style text format of tools/firmware_signing (ST): an `ED25519 PRIVATE KEY` block holding
the 32-byte seed and an optional `ED25519 PUBLIC KEY` block, both base64.

Stdlib only; PyNaCl is imported where a signature has to be made or checked.
"""

import base64
import hashlib
import os
import struct
import zlib

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

KEY_ENV_VAR = "SMAC_FW_SIGN_KEY"
DEFAULT_KEY_PATH = os.path.join(REPO_ROOT, "apps", "st", "stm32wba", "sid_smartac_wba_bootloader",
                                "development_sign_key.pem")

PUB_KEY_SIZE = 32
FP_SIZE = 8  # INFO/BOOT_KEY frame: first 8 bytes of SHA-256(public key)

# OTP key record, must match apps/st/stm32wba/common/Core/Inc/boot_key_otp.h
FLASH_OTP_BASE = 0x0BF90000
FLASH_OTP_SIZE = 512
OTP_SLOT_SIZE = 16
OTP_SLOT_DATA_SIZE = OTP_SLOT_SIZE - 1
OTP_SLOTS = 3
OTP_IDX_BASE = 0xB0
OTP_FORMAT_V1 = 1
OTP_RECORD_SIZE = OTP_SLOTS * OTP_SLOT_SIZE
OTP_PAYLOAD_SIZE = OTP_SLOTS * OTP_SLOT_DATA_SIZE

OTP_OK = 0
OTP_NOT_PROVISIONED = 1
OTP_INVALID = 2
OTP_STATUS_NAMES = {OTP_OK: "ok", OTP_NOT_PROVISIONED: "not provisioned", OTP_INVALID: "invalid"}

# WBA application image, must match sid_aim_ota_header_t / sid_aim_ota_footer_t and the app linker script
WBA_APP_FLASH_BASE = 0x08012000
WBA_OTA_HEADER_OFFSET = 0x188
WBA_FOOTER_MAGIC = 0x94448A29
WBA_FOOTER_SIGNATURE_SIZE = 64
WBA_FOOTER_SIZE = WBA_FOOTER_SIGNATURE_SIZE + 4 + 4  # signature, magic, CRC


class SignKeyError(Exception):
    """Key file missing or malformed."""


def resolve_key_path(cli_key=None, default_path=DEFAULT_KEY_PATH):
    """Returns (path, explicit). --key wins, then $SMAC_FW_SIGN_KEY, then default_path.

    An explicitly given path (CLI or env) must exist; the default path may be missing (caller decides).
    """
    for explicit in (cli_key, os.environ.get(KEY_ENV_VAR) or None):
        if explicit:
            if not os.path.isfile(explicit):
                raise SignKeyError(f"signing key file not found: {explicit}")
            return os.path.abspath(explicit), True

    return os.path.abspath(default_path), False


def _pem_block(text, name):
    begin = f"-----BEGIN {name}-----"
    end = f"-----END {name}-----"
    if begin not in text:
        return None
    body = text.split(begin, 1)[1].split(end, 1)[0]
    return base64.b64decode("".join(body.split()), validate=True)


def load_seed(path):
    """Private 32-byte seed from a key file."""
    with open(path, "r", encoding="utf-8") as f:
        seed = _pem_block(f.read(), "ED25519 PRIVATE KEY")
    if seed is None or len(seed) != 32:
        raise SignKeyError(f"{path}: no valid ED25519 PRIVATE KEY block")
    return seed


def load_public_key(path):
    """Public key from a key file; derived from the private seed (needs PyNaCl) if the file has no public block."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    pub = _pem_block(text, "ED25519 PUBLIC KEY")
    if pub is not None:
        if len(pub) != PUB_KEY_SIZE:
            raise SignKeyError(f"{path}: ED25519 PUBLIC KEY block is not {PUB_KEY_SIZE} bytes")
        return pub

    from nacl.signing import SigningKey

    return bytes(SigningKey(load_seed(path)).verify_key)


def load_signing_key(path):
    """nacl SigningKey from a key file, checked against its public block if present."""
    from nacl.signing import SigningKey

    sk = SigningKey(load_seed(path))

    with open(path, "r", encoding="utf-8") as f:
        pub = _pem_block(f.read(), "ED25519 PUBLIC KEY")
    if pub is not None and pub != bytes(sk.verify_key):
        raise SignKeyError(f"{path}: public key does not match the private key")

    return sk


def fingerprint(pub):
    """Same value as the device's INFO/BOOT_KEY frame: first 8 bytes of SHA-256(public key), hex."""
    return hashlib.sha256(pub).digest()[:FP_SIZE].hex()


def describe_key(pub):
    """Full public key (as the WBA bootloader logs it) and fingerprint (as the cloud sees it)."""
    return f"pub={pub.hex().upper()} fp={fingerprint(pub)}"


def otp_record(pub):
    """48-byte OTP key record (3 ST-style slots) for the given public key."""
    if len(pub) != PUB_KEY_SIZE:
        raise ValueError(f"public key must be {PUB_KEY_SIZE} bytes")

    payload = bytes([OTP_FORMAT_V1]) + pub
    payload += zlib.crc32(payload).to_bytes(4, "little")
    payload += b"\xff" * (OTP_PAYLOAD_SIZE - len(payload))

    return b"".join(payload[n * OTP_SLOT_DATA_SIZE:(n + 1) * OTP_SLOT_DATA_SIZE] + bytes([OTP_IDX_BASE + n])
                    for n in range(OTP_SLOTS))


def parse_otp(dump):
    """Port of boot_key_otp_read(): returns (status, public key or None) for a 512-byte OTP read-back."""
    if len(dump) != FLASH_OTP_SIZE:
        raise ValueError(f"OTP dump must be {FLASH_OTP_SIZE} bytes, got {len(dump)}")

    # first record wins
    first = next((s for s in range(0, FLASH_OTP_SIZE, OTP_SLOT_SIZE)
                  if dump[s + OTP_SLOT_DATA_SIZE] == OTP_IDX_BASE), None)
    if first is None:
        return OTP_NOT_PROVISIONED, None

    if first + OTP_RECORD_SIZE > FLASH_OTP_SIZE:
        return OTP_INVALID, None

    payload = b""
    for n in range(OTP_SLOTS):
        slot = dump[first + n * OTP_SLOT_SIZE:first + (n + 1) * OTP_SLOT_SIZE]
        if slot[OTP_SLOT_DATA_SIZE] != OTP_IDX_BASE + n:
            return OTP_INVALID, None
        payload += slot[:OTP_SLOT_DATA_SIZE]

    if payload[0] != OTP_FORMAT_V1:
        return OTP_INVALID, None

    crc_offset = 1 + PUB_KEY_SIZE
    if int.from_bytes(payload[crc_offset:crc_offset + 4], "little") != zlib.crc32(payload[:crc_offset]):
        return OTP_INVALID, None

    return OTP_OK, payload[1:crc_offset]


def wba_image_footer_offset(image):
    """Offset of the OTA footer in a WBA OTA image (.bin starting at APP_FLASH), checked by its magic word."""
    if len(image) < WBA_OTA_HEADER_OFFSET + 4:
        raise ValueError("WBA image too small to hold the OTA header")

    footer_addr, = struct.unpack_from("<I", image, WBA_OTA_HEADER_OFFSET)
    offset = footer_addr - WBA_APP_FLASH_BASE
    if offset < 0 or offset + WBA_FOOTER_SIZE > len(image):
        raise ValueError(f"OTA footer address 0x{footer_addr:08X} is outside the image")

    magic, = struct.unpack_from("<I", image, offset + WBA_FOOTER_SIGNATURE_SIZE)
    if magic != WBA_FOOTER_MAGIC:
        raise ValueError(f"bad OTA footer magic 0x{magic:08X}")

    return offset


def verify_wba_image(image, pub):
    """True if the footer signature verifies with pub, as app_wba_authenticate() checks it (Ed25519 over the
    SHA-512 of the image up to the footer)."""
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey

    offset = wba_image_footer_offset(image)
    digest = hashlib.sha512(image[:offset]).digest()
    signature = bytes(image[offset:offset + WBA_FOOTER_SIGNATURE_SIZE])

    try:
        VerifyKey(pub).verify(digest, signature)
    except BadSignatureError:
        return False

    return True
