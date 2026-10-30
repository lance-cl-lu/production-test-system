# serial frame used to send data over a serial bus
# struct {
#    uint8_t ver; // version of the frame format, currently 0x01
#    uint8_t len; // length of the payload
#    uint8_t reserved; // reserved byte, must be 0x00
#    uint8_t crc; // CRC-8 of the payload
# } __attribute__((packed)) mac_frame_header_t;
#
# MAC PDU frame format:
# struct {
#     mac_frame_header_t header;
#     uint8_t sdu[256 + 2]; // variable length payload, max 256 bytes + 2 bytes for CRC-16
# } __attribute__((packed)) mac_frame_t;
# PHY synchronization sequence LE: 0x55AAAA55
# Parser waits for the synchronization sequence, then reads the header and verifies its CRC, then reads the payload based on the length in the header, then verifies the CRC-16 of the payload. If all checks pass, the payload is processed, otherwise the frame is discarded and the parser waits for the next synchronization sequence.

import serial
import struct
import crcmod.predefined
import time
import logging

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MAC")

class SerialMAC:
    SYNC_SEQUENCE = b'\x55\xAA\xAA\x55'
    HEADER_FORMAT = '<BBB'
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    MAX_PAYLOAD_SIZE = 256

    def __init__(self, port, baudrate=115200):
        self.serial = serial.Serial(port, baudrate, timeout= (1 / baudrate) * 20) 
        self.crc8 = crcmod.mkCrcFun(0x107, initCrc=0x00, xorOut=0x00, rev=False)
        self.crc16 = crcmod.mkCrcFun(0x11021, initCrc=0x0000, xorOut=0x0000, rev=False)

    def send_frame(self, sdu):
        logger.debug(f"send_frame() pdu=[{sdu.hex()}]")
        
        if len(sdu) > self.MAX_PAYLOAD_SIZE:
            raise ValueError("SDU size exceeds maximum payload size")
        
        # Calculate CRC-16 for the payload
        payload_crc = struct.pack('<H', self.crc16(sdu))
        payload = sdu + payload_crc

        # Create header
        header = struct.pack(
            self.HEADER_FORMAT,
            0x01,  # version
            len(sdu),
            0x00   # reserved
        )

        # Calculate CRC-8 for the header
        header_crc = self.crc8(header)
        header += struct.pack('B', header_crc)

        # Send synchronization sequence, header, and payload
        self.serial.write(self.SYNC_SEQUENCE + header + payload)
        self.serial.flush()

    def receive_frame(self, timeout=None):
        """Receive a frame with an optional timeout in milliseconds (1 ms resolution)."""
        start_time = time.monotonic()
        rx_window = bytearray()

        while True:
            # Check for timeout
            if timeout is not None and (time.monotonic() - start_time) * 1000 >= timeout:
                raise TimeoutError("SYNC timeout. Buffer: [" + rx_window.hex() + "]")

            # Read one byte and append to RX window
            rx_window += self.serial.read(1)

            # Ensure RX window does not exceed SYNC_SEQUENCE length
            if len(rx_window) > len(self.SYNC_SEQUENCE):
                rx_window.pop(0)

            # Check if RX window matches SYNC_SEQUENCE
            if rx_window == self.SYNC_SEQUENCE:
                break

        header = bytearray()
        # Read and parse header
        while True:
            if timeout is not None and (time.monotonic() - start_time) * 1000 >= timeout:
                raise TimeoutError("HEADER timeout. Buffer: [" + header.hex() + "]")
            
            header += self.serial.read(1)
            
            if len(header) == self.HEADER_SIZE + 1:  # Header size + CRC-8
                break
            
        if len(header) < self.HEADER_SIZE + 1:
            raise ValueError("HEADER incomplete. Buffer: [" + header.hex() + "]")

        ver, length, reserved, header_crc = struct.unpack('<BBB', header[:self.HEADER_SIZE]) + (header[-1],)

        # Verify header CRC
        if header_crc != self.crc8(header[:self.HEADER_SIZE]):
            raise ValueError("HEADER CRC: expected {:02X}, got {:02X}. Buffer: [{}]".format(self.crc8(header[:self.HEADER_SIZE]), header_crc, header.hex()))
        
        # Read payload
        payload = bytearray()
        while True:
            if timeout is not None and (time.monotonic() - start_time) * 1000 >= timeout:
                raise TimeoutError("PAYLOAD timeout. Buffer: [" + payload.hex() + "]")
            
            payload += self.serial.read(1)
            
            if len(payload) >= length + 2:  # Payload length + CRC-16
                break
            
        if len(payload) < length + 2:
            raise ValueError("PAYLOAD incomplete. Buffer: [" + payload.hex() + "]")

        sdu, payload_crc = payload[:-2], payload[-2:]

        # Verify payload CRC
        if struct.unpack('<H', payload_crc)[0] != self.crc16(sdu):
            raise ValueError("PAYLOAD CRC: expected {:04X}, got {:04X}. Buffer: [{}]".format(self.crc16(sdu), struct.unpack('<H', payload_crc)[0], payload.hex()))
        
        logger.debug(f"receive_frame(): header [version={ver}, length={length}, reserved={reserved}, header_crc={header_crc:02X}]")
        logger.debug(f"receive_frame(): payload [sdu={sdu.hex()}, payload_crc={payload_crc.hex()}]")

        return sdu


