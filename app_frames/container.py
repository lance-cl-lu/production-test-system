import argparse
import base64
import os
import struct
import ctypes
import hashlib
from nacl.signing import SigningKey


# typedef struct
# {
#     uint32_t crc;       // << CRC of the whole container, excluding this field
#     uint8_t  sign[64];  // << Signature of the whole container, excluding crc and this field
#     uint32_t magic;     // << Magic number to identify the container
#     uint32_t version;   // << Version of the container format
#     union
#     {
#         uint32_t size   : 24; // << Size of the firmware image
#         uint32_t        :  6; // << Reserved bits
#         uint32_t hasWLx :  1; // << Whether the container has WLx image
#         uint32_t hasWBA :  1; // << Whether the container has WBA image
#     };
# } __attribute__((packed)) OtaContainerHeader_t;
# The final container may contain up to 2 images: WLE and WBA. first image in the container must be WLE, followed by WBA.
# container image starts with OtaContainerHeader_t, followed by 3 bytes of image file size to be attached first, the image data,
# then 3 bytes of image file size to be attached second, then the image data.

CContainerSignature = ctypes.c_uint8 * 64

class OtaContainerHeader(ctypes.LittleEndianStructure):
    _fields_ = [
        ("crc", ctypes.c_uint32),
        ("sign", CContainerSignature),
        ("magic", ctypes.c_uint32),
        ("version", ctypes.c_uint32),
        ("size", ctypes.c_uint32, 24),
        ("reserved", ctypes.c_uint32, 6),
        ("hasWLx", ctypes.c_uint32, 1),
        ("hasWBA", ctypes.c_uint32, 1),
    ]

    def __init__(self):
        self.crc = 0
        # Ensure signature is exactly 64 bytes
        self.sign = CContainerSignature()
        self.magic = 0
        self.version = 0
        self.size = ctypes.sizeof(OtaContainerHeader)
        self.hasWLx = 0
        self.hasWBA = 0


container_magic = {
    "SID": 0x51DEC0DE,
    "GEN2": 0x6E22ED0C,
}

def ieee_802_3_crc32(data):
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
    return crc ^ 0xFFFFFFFF  # final XOR


def load_signing_key(key_file_path: str) -> SigningKey:
    if not os.path.exists(key_file_path):
        raise FileNotFoundError(
            f'[ERROR] Key file {key_file_path} does not exist')

    with open(key_file_path, 'r', encoding='utf-8') as f:
        raw_key_data = f.read()

    # Extract private key
    try:
        private_key_b64 = raw_key_data.split(
            '-----BEGIN ED25519 PRIVATE KEY-----\n')[1].split('\n-----END ED25519 PRIVATE KEY-----')[0]
        private_key_bytes = base64.b64decode(
            private_key_b64, validate=True)

    except:
        raise Exception('No private key found in the provided key file')

    # Extract public key
    try:
        public_key_b64 = raw_key_data.split(
            '-----BEGIN ED25519 PUBLIC KEY-----\n')[1].split('\n-----END ED25519 PUBLIC KEY-----')[0]
        public_key_bytes = base64.b64decode(public_key_b64, validate=True)

    except IndexError:
        # This is ok, the key file may contain only the private key. The public key can be easily restored from the private key
        public_key_bytes = None
    except:
        raise Exception('Invalid public key format in the provided key file')

    # Create key object
    sk = SigningKey(private_key_bytes)

    # Cross check the public key if it was included into the key file
    if public_key_bytes is not None:
        pk = sk.verify_key
        if pk.encode() != public_key_bytes:
            raise Exception(
                'Provided public key does not correlate with the private key. Ensure they belong to the same key pair')
    
    # Provide back the loaded key
    return sk

def create_container(container_type, wle_file, wba_file, signing_key: SigningKey):
    if wle_file is None and wba_file is None:
        raise ValueError(
            "At least one of WLE or WBA firmware files must be provided")

    if container_type not in container_magic:
        raise ValueError(
            f"Invalid container type. Supported types are: {', '.join(container_magic.keys())}")

    if signing_key is None:
        raise ValueError("Signing key must be provided to sign the container")

    header = OtaContainerHeader()

    print(f"Initial container size: {header.size}")

    image_data = b""

    if wle_file is not None:
        with open(wle_file, "rb") as f:
            wle_data = f.read()
        print(f"WLE image size: {len(wle_data)} bytes")
        header.hasWLx = 1
        header.size += len(wle_data) + 4 # add 4 bytes for the size field
        image_data += len(wle_data).to_bytes(4, "little") + wle_data

    if wba_file is not None:
        with open(wba_file, "rb") as f:
            wba_data = f.read()
        print(f"WBA image size: {len(wba_data)} bytes")
        header.hasWBA = 1
        header.size += len(wba_data) + 4 # add 4 bytes for the size field
        image_data += len(wba_data).to_bytes(4, "little") + wba_data

    header.magic = container_magic[container_type]
    header.version = 1

    # Combine header and image data
    container_data = bytes(header) + image_data
    print(f"Container size before signing and CRC: {len(container_data)} bytes")

    # Exclude CRC and signature fields
    sinature_coverd_data = container_data[4+64:] # skip the first 68 bytes (CRC + signature)
    print(f"Data size covered by the signature: {len(sinature_coverd_data)} bytes")
    container_digest = hashlib.sha512(sinature_coverd_data).digest()
    print(f"SHA-512 digest of the container (excluding CRC and signature): {container_digest.hex()}")

    # Now sign the SHA-512 digest
    sign = signing_key.sign(container_digest).signature
    print(f"Signature: {sign.hex()}")
    header.sign = CContainerSignature.from_buffer_copy(bytearray(sign))
    
    container_data = bytes(header) + image_data
    
    print(f"Container size after signing: {len(container_data)} bytes")

    # Calculate CRC (excluding the CRC field itself)
    header.crc = ieee_802_3_crc32(container_data[4:])
    container_data = bytes(header) + image_data
    
    print(f"Final container size: {len(container_data)} bytes")

    # Write the container to a file
    output_file = f"container_{container_type}.bin"
    with open(output_file, "wb") as f:
        f.write(container_data)

    print(f"Container created: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="SID/Gen2 container processor")

    parser.add_argument(
        "-t", "--type",
        type=str,
        default="SID",
        help=f"The type of the container to create (default: SID). Supported types are: {', '.join(container_magic.keys())}",
    )

    parser.add_argument(
        "--wle",
        type=str,
        help="The WLE firmware file to use for the container"
    )

    parser.add_argument(
        "--wba",
        type=str,
        help="The WBA firmware file to use for the container"
    )

    parser.add_argument(
        "-k", "--key",
        type=str,
        help="The key file to use to sign the container"
    )

    parser.add_argument

    args = parser.parse_args()
    
    signing_key = load_signing_key(args.key)
    
    create_container(args.type, args.wle, args.wba, signing_key)


if __name__ == "__main__":
    main()