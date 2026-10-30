#!/usr/bin/env python3
"""
spi_flash_image.py

Builds a raw image of the external SPI NOR flash with the SID and GEN2 factory containers placed in the WBA
bootloader's factory slots, for programming the chip directly at the factory.

    python3 spi_flash_image.py --sid container_SID_....bin --gen2 container_GEN2_....bin [-o spi_flash_factory.bin]

SPI flash layout (fixed in the bootloader, apps/st/stm32wba/sid_smartac_wba_bootloader/Core/Src/storage_external.c;
nothing on the flash describes it):

    0x000000  1.25 MB  factory SID container
    0x140000  1.25 MB  factory GEN2 container
    0x280000  1.25 MB  OTA container (written by the app)
    0x3C0000  256 KB   USERFS LittleFS (app only)

Each container starts at offset 0 of its slot and the rest of the slot is 0xFF (erased). The image ends at the
end of the GEN2 slot unless --size is given; with --size it is padded with 0xFF, which also leaves the OTA and
USERFS regions erased. Without --size the programmer must erase the rest of the chip (or the chip must be blank).

Each container gets the same checks the bootloader runs before installing it (app_container.c): the magic matches
the slot, the size fields add up and fit the slot, and the CRC32. With a key (-k, $SMAC_FW_SIGN_KEY, or --dev-key
for the development key) the container's Ed25519 signature and the WBA app's signature are also checked; this
needs PyNaCl (e.g. smac_tools/container/venv/bin/python). Without a key the signatures are not checked.

Also writes <output>.metadata.json (image sha256, per-slot container type/version/size/crc/sha256) and, with
--hex BASE, an Intel HEX copy of the image at address BASE.
"""

import argparse
import hashlib
import json
import os
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "signing"))
import sign_key  # noqa: E402

# !!!!! keep in sync with storage_external.c / app_container.c in sid_smartac_wba_bootloader
SECTOR_SIZE = 4096
SLOT_SIZE = (1024 + 256) * 1024
SLOT_OFFSETS = {
    "SID": 0 * SLOT_SIZE,
    "GEN2": 1 * SLOT_SIZE,
    "OTA": 2 * SLOT_SIZE,
}
USERFS_OFFSET = 3 * SLOT_SIZE
FACTORY_SLOTS = ("SID", "GEN2")
DEFAULT_IMAGE_SIZE = SLOT_OFFSETS["OTA"]  # end of the GEN2 slot
MAX_IMAGE_SIZE = 16 * 1024 * 1024  # 3-byte SPI addresses
HEX_ADDRESS_LIMIT = 1 << 32  # Intel HEX extended linear addresses are 32-bit
ERASED = 0xFF

CONTAINER_MAGIC = {
    0x51DEC0DE: "SID",
    0x6E22ED0C: "GEN2",
}

# container_header_t: crc, sign[64], magic, version, attr (size:24, :6, hasWLx:1, hasWBA:1), little-endian
HEADER_FORMAT = "<I64sIII"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
SIGNED_OFFSET = 4 + 64  # the signature covers magic .. end
ATTR_SIZE_MASK = 0x00FFFFFF
ATTR_HAS_WLX = 1 << 30
ATTR_HAS_WBA = 1 << 31

DEFAULT_OUTPUT = "spi_flash_factory.bin"


class InputError(Exception):
    pass


def format_version(version):
    return ".".join(str((version >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def parse_container(data):
    """Header fields and the (name, offset, size) of each image, without any checks beyond the header length."""
    if len(data) < HEADER_SIZE:
        raise InputError(f"too small for a container header ({len(data)} < {HEADER_SIZE} bytes)")

    crc, signature, magic, version, attr = struct.unpack_from(HEADER_FORMAT, data, 0)
    container = {
        "crc": crc,
        "signature": signature,
        "magic": magic,
        "type": CONTAINER_MAGIC.get(magic),
        "version": version,
        "size": attr & ATTR_SIZE_MASK,
        "has_wlx": bool(attr & ATTR_HAS_WLX),
        "has_wba": bool(attr & ATTR_HAS_WBA),
        "images": [],
    }

    offset = HEADER_SIZE
    for name, present in (("WLx", container["has_wlx"]), ("WBA", container["has_wba"])):
        if not present:
            continue
        if offset + 4 > len(data):
            raise InputError(f"{name} image size field at 0x{offset:X} is past the end of the file")
        image_size, = struct.unpack_from("<I", data, offset)
        container["images"].append((name, offset + 4, image_size))
        offset += 4 + image_size

    container["computed_size"] = offset
    return container


def check_container(data, slot):
    """Mirrors the bootloader's _container_header_check() and install CRC check. Returns the parsed container."""
    container = parse_container(data)

    if container["type"] is None:
        raise InputError(f"unknown container magic 0x{container['magic']:08X}")
    if container["type"] != slot:
        raise InputError(f"{container['type']} container cannot go into the {slot} slot "
                         f"(the bootloader rejects it as incompatible)")

    size = container["size"]
    if size == 0 or size > SLOT_SIZE or size % 4:
        raise InputError(f"invalid container size {size} (must be non-zero, <= {SLOT_SIZE} and a multiple of 4)")
    if not container["images"]:
        raise InputError("container has no images")
    if container["computed_size"] != size:
        raise InputError(f"container size mismatch: header says {size}, images add up to "
                         f"{container['computed_size']}")
    if len(data) < size:
        raise InputError(f"file is truncated: {len(data)} bytes, header says {size}")

    crc = zlib.crc32(data[4:size])
    if crc != container["crc"]:
        raise InputError(f"CRC mismatch: header 0x{container['crc']:08X}, computed 0x{crc:08X}")

    return container


def verify_signatures(data, container, pub):
    """Container signature (Ed25519 over SHA-512 of magic .. end) and the WBA app's own signature."""
    try:
        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey
    except ImportError:
        raise InputError("checking signatures needs PyNaCl (e.g. run with smac_tools/container/venv/bin/python)")

    digest = hashlib.sha512(data[SIGNED_OFFSET:container["size"]]).digest()
    try:
        VerifyKey(pub).verify(digest, container["signature"])
    except BadSignatureError:
        raise InputError(f"container is NOT signed with {sign_key.describe_key(pub)}")

    for name, offset, size in container["images"]:
        if name != "WBA":
            continue
        try:
            signed = sign_key.verify_wba_image(data[offset:offset + size], pub)
        except ValueError as e:
            raise InputError(f"WBA image: {e}")
        if not signed:
            raise InputError(f"WBA image is NOT signed with {sign_key.describe_key(pub)}")


def load_container(path, slot, pub):
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as e:
        raise InputError(f"{path}: {e.strerror}")

    try:
        container = check_container(data, slot)
        if pub is not None:
            verify_signatures(data, container, pub)
    except InputError as e:
        raise InputError(f"{path}: {e}")

    if len(data) > container["size"]:
        print(f"[WARNING] {path}: {len(data) - container['size']} trailing byte(s) after the container are "
              f"not packed")

    container["path"] = path
    container["data"] = data[:container["size"]]
    return container


def build_image(containers, size):
    """containers: {slot: container}. Returns the image, erased everywhere except the containers."""
    image = bytearray([ERASED]) * size
    for slot, container in containers.items():
        offset = SLOT_OFFSETS[slot]
        image[offset:offset + len(container["data"])] = container["data"]
    return bytes(image)


def parse_size(text):
    """Hex/decimal byte count with an optional K or M suffix, e.g. 0x400000, 4M, 4096K."""
    text = text.strip().upper()
    multiplier = 1
    if text.endswith("K") or text.endswith("M"):
        multiplier = 1024 if text[-1] == "K" else 1024 * 1024
        text = text[:-1]
    try:
        size = int(text, 0) * multiplier
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a size")

    if size < DEFAULT_IMAGE_SIZE or size > MAX_IMAGE_SIZE or size % SECTOR_SIZE:
        raise argparse.ArgumentTypeError(
            f"size must be 0x{DEFAULT_IMAGE_SIZE:X}..0x{MAX_IMAGE_SIZE:X} and a multiple of 0x{SECTOR_SIZE:X}")
    return size


def parse_hex_base(text):
    """Hex/decimal Intel HEX base address; the image must also fit below 4 GB, checked once --size is known."""
    try:
        base = int(text, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not an address")

    if base < 0 or base >= HEX_ADDRESS_LIMIT:
        raise argparse.ArgumentTypeError(f"base must be 0x0..0x{HEX_ADDRESS_LIMIT - 1:X}")
    return base


def resolve_public_key(cli_key, dev_key):
    """-k, then $SMAC_FW_SIGN_KEY, then (only with --dev-key) the development key; None = don't check."""
    if dev_key:
        path = sign_key.DEFAULT_KEY_PATH
        if not os.path.isfile(path):
            raise InputError(f"development key not found: {path}")
    elif cli_key or os.environ.get(sign_key.KEY_ENV_VAR):
        path, _ = sign_key.resolve_key_path(cli_key)
    else:
        return None, None

    try:
        return path, sign_key.load_public_key(path)
    except ImportError:
        raise InputError(f"{path} has no public key block; deriving it needs PyNaCl")


def write_intel_hex(path, base, data):
    def record(rtype, addr16, payload):
        body = bytes([len(payload), addr16 >> 8, addr16 & 0xFF, rtype]) + payload
        return ":" + (body + bytes([(-sum(body)) & 0xFF])).hex().upper() + "\n"

    if base < 0 or base + len(data) > HEX_ADDRESS_LIMIT:
        raise ValueError(f"0x{base:X} + {len(data)} bytes does not fit in 32-bit Intel HEX addresses")

    lines = []
    upper = None
    i = 0
    while i < len(data):
        address = base + i
        if address >> 16 != upper:
            upper = address >> 16
            lines.append(record(0x04, 0, upper.to_bytes(2, "big")))
        # a data record must not cross a 64 KB boundary (possible when base is not 16-byte aligned)
        count = min(16, len(data) - i, 0x10000 - (address & 0xFFFF))
        lines.append(record(0x00, address & 0xFFFF, data[i:i + count]))
        i += count
    lines.append(record(0x01, 0, b""))

    with open(path, "w", encoding="ascii") as f:
        f.writelines(lines)


def write_metadata(path, image, containers, pub):
    metadata = {
        "size": len(image),
        "sha256": hashlib.sha256(image).hexdigest(),
        "slots": {},
    }
    if pub is not None:
        metadata["signing_key_fp"] = sign_key.fingerprint(pub)

    for slot, container in containers.items():
        metadata["slots"][slot] = {
            "offset": f"0x{SLOT_OFFSETS[slot]:06X}",
            "file": container["path"].name,
            "version": format_version(container["version"]),
            "size": container["size"],
            "crc": f"0x{container['crc']:08X}",
            "sha256": hashlib.sha256(container["data"]).hexdigest(),
            "images": [name for name, _offset, _size in container["images"]],
        }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
        f.write("\n")


def print_layout(image_size, containers):
    print(f"[INFO] SPI flash image: {image_size} bytes (0x000000 - 0x{image_size - 1:06X})")
    for slot, offset in SLOT_OFFSETS.items():
        end = offset + SLOT_SIZE
        if offset >= image_size:
            print(f"[INFO]   {slot:<6} 0x{offset:06X} - 0x{end - 1:06X}  not in image")
            continue
        container = containers.get(slot)
        if container is None:
            print(f"[INFO]   {slot:<6} 0x{offset:06X} - 0x{end - 1:06X}  erased")
            continue
        images = ", ".join(f"{name} {size} B" for name, _offset, size in container["images"])
        print(f"[INFO]   {slot:<6} 0x{offset:06X} - 0x{end - 1:06X}  {container['path'].name}")
        print(f"[INFO]            v{format_version(container['version'])}, {container['size']} B used "
              f"({images}), {SLOT_SIZE - container['size']} B free, crc 0x{container['crc']:08X}")
    if image_size > USERFS_OFFSET:
        print(f"[INFO]   USERFS 0x{USERFS_OFFSET:06X} - 0x{USERFS_OFFSET + 256 * 1024 - 1:06X}  erased")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sid", required=True, help="SID factory container (container.py -t SID)")
    parser.add_argument("--gen2", required=True, help="GEN2 factory container (container.py -t GEN2)")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT, help=f"output image (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--size", type=parse_size, default=DEFAULT_IMAGE_SIZE,
                        help=f"image size, padded with 0xFF, e.g. 4M or 0x1000000 "
                             f"(default: 0x{DEFAULT_IMAGE_SIZE:X}, end of the GEN2 slot)")
    key = parser.add_mutually_exclusive_group()
    key.add_argument("-k", "--key", help="check signatures with this key file (default: $SMAC_FW_SIGN_KEY if set)")
    key.add_argument("--dev-key", action="store_true",
                     help="check signatures with the development key (sid_smartac_wba_bootloader/"
                          "development_sign_key.pem)")
    parser.add_argument("--hex", type=parse_hex_base, metavar="BASE",
                        help="also write the image at address BASE as Intel HEX, named as the output with a .hex "
                             "extension (e.g. out.bin -> out.hex)")
    args = parser.parse_args()
    if args.hex is not None and args.hex + args.size > HEX_ADDRESS_LIMIT:
        parser.error(f"--hex: a 0x{args.size:X} byte image at 0x{args.hex:X} ends past the 32-bit Intel HEX "
                     f"address range (base must be <= 0x{HEX_ADDRESS_LIMIT - args.size:X})")
    if args.hex is not None and Path(args.output).suffix.lower() == ".hex":
        parser.error("--hex: the output already ends in .hex, so the HEX copy would overwrite the raw image "
                     "(name the output e.g. .bin)")

    try:
        key_path, pub = resolve_public_key(args.key, args.dev_key)
        if pub is None:
            print("[INFO] No key given (-k, $SMAC_FW_SIGN_KEY or --dev-key): signatures are NOT checked")
        else:
            print(f"[INFO] Checking signatures with {key_path}")
            print(f"[INFO]   {sign_key.describe_key(pub)}")

        containers = {
            "SID": load_container(args.sid, "SID", pub),
            "GEN2": load_container(args.gen2, "GEN2", pub),
        }
        image = build_image(containers, args.size)

        output = Path(args.output)
        output.write_bytes(image)
        metadata_path = output.with_name(output.name + ".metadata.json")
        write_metadata(metadata_path, image, containers, pub)
        hex_path = None
        if args.hex is not None:
            hex_path = output.with_suffix(".hex")
            write_intel_hex(hex_path, args.hex, image)
    except (InputError, sign_key.SignKeyError, OSError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    print_layout(len(image), containers)
    if args.size > DEFAULT_IMAGE_SIZE:
        print("[WARNING] The image covers the OTA/USERFS regions: programming it erases them")
    else:
        print("[INFO] The rest of the chip (OTA, USERFS) must be erased before or when programming")
    print(f"[INFO] Written {output} (sha256 {hashlib.sha256(image).hexdigest()})")
    print(f"[INFO] Written {metadata_path}")
    if hex_path is not None:
        print(f"[INFO] Written {hex_path} (base 0x{args.hex:08X})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
