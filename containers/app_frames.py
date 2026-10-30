from enum import Enum
from protocol_errors import OFF_ERROR_STRINGS
import logging

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SmacDfuCmd(Enum):
    NOP = 1
    BOOT_CTL = 2
    GET_INFO = 3
    CONTAINER = 4
    EXTM = 5
    REBOOT = 6

# Command attribute flags
CMD_ATTR_RESP = 1 << 0  # Response flag
CMD_ATTR_ERR = 1 << 1   # Error flag

class SmacDfuState(Enum):
    INACTIVE = 0
    ACTIVE = 1

class SmacDfuPdu:
    def __init__(self, version=1, attrib=0, err=0, code=None, data=b''):
        if len(data) > 128:
            raise ValueError("Data must be a bytes object with a maximum length of 128")

        self.version = version
        self.attrib = attrib
        self.err = err
        self.code = code
        self.data = data

    @classmethod
    def from_bytes(cls, byte_data):        
        if len(byte_data) < 4:
            raise ValueError("Byte data is too short to contain a valid PDU")

        version, attrib, err, code = byte_data[:4]
        data = byte_data[4:]
        return cls(version, attrib, err, code, data)

    def to_bytes(self):
        header = bytes([self.version, self.attrib, self.err, self.code])
        return header + self.data

    def get_sdu(self):
        """Retrieve the SDU (Service Data Unit) from the PDU."""
        return self.data

    def get_version(self):
        """Retrieve the version field."""
        return self.version

    def get_attrib(self):
        """Retrieve the attribute field."""
        return self.attrib

    def get_error(self):
        """Retrieve the error field."""
        return self.err
    
    def get_error_string(self):
        """Retrieve the error string based on the error code."""
        return OFF_ERROR_STRINGS.get(self.err, "UNKNOWN_ERROR")

    def get_code(self):
        """Retrieve the code field."""
        return self.code

    def __repr__(self):
        return (
            f"SmacDfuPdu(version={self.version}, attrib={self.attrib}, "
            f"err={self.err}, code={self.code}, data={self.data})"
        )


class SmacDfuExtmReq(Enum):
    ERASE = 1
    WRITE = 2
    VERIFY = 3
    
    
class SmacDfuContainerSlot(Enum):
    SID = 1
    GEN2 = 2
    OTA = 3

class SmacDfuExtMemErase:
    def __init__(self, slot, op = SmacDfuExtmReq.ERASE):
        self.op = op
        self.slot = slot

    @classmethod
    def from_bytes(cls, byte_data):
        """Construct an instance of SmacDfuExtMemErase from raw bytes."""
        if len(byte_data) < 2:
            raise ValueError("Byte data is too short to contain a valid SmacDfuExtMemErase SDU")

        op, slot = byte_data[:2]
        return cls(op, slot)

    def to_bytes(self):
        """Convert the SmacDfuExtMemErase SDU to raw bytes."""
        return bytes([self.op.value, self.slot.value])

    def __repr__(self):
        return f"SmacDfuExtMemErase(op={self.op}, slot={self.slot})"

class SmacDfuExtMemWrite:
    def __init__(self, slot, offset, size, data, op = SmacDfuExtmReq.WRITE):
        if not isinstance(data, bytes):
            raise ValueError("Data must be a bytes object")
        if len(data) != size:
            raise ValueError("Size of data does not match the specified size")

        self.op = SmacDfuExtmReq(op)  # Operation (smac_dfu_extm_req_t)
        self.slot = slot  # Slot (smac_dfu_container_slot_t)
        self.offset = offset  # Offset (uint32_t)
        self.size = size  # Size (uint8_t)
        self.data = data  # Data (uint8_t[])

    @classmethod
    def from_bytes(cls, byte_data):
        """Construct an instance of SmacDfuExtMemWrite from raw bytes."""
        if len(byte_data) < 7:
            raise ValueError("Byte data is too short to contain a valid SmacDfuExtMemWrite SDU")

        op, slot = byte_data[:2]
        offset = int.from_bytes(byte_data[2:6], 'little')
        size = byte_data[6]
        data = byte_data[7:]

        if len(data) != size:
            raise ValueError("Data length does not match the specified size")

        return cls(slot, offset, size, data, op)

    def to_bytes(self):
        """Convert the SmacDfuExtMemWrite SDU to raw bytes."""
        header = bytes([self.op.value, self.slot.value])
        offset_bytes = self.offset.to_bytes(4, 'little')
        size_byte = bytes([self.size])
        return header + offset_bytes + size_byte + self.data

    def __repr__(self):
        return (
            f"SmacDfuExtMemWrite(op={self.op}, slot={self.slot}, offset={self.offset}, "
            f"size={self.size}, data={self.data})"
        )


