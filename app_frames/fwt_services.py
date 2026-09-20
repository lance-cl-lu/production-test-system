
import app_frames
import fwt_mac
import logging

logger = logging.getLogger(__name__)

slot_id = {
    "SID": app_frames.SmacDfuContainerSlot.SID,
    "GEN2": app_frames.SmacDfuContainerSlot.GEN2,
    "OTA": app_frames.SmacDfuContainerSlot.OTA,
}

def dfu_enter(mac: fwt_mac.SerialMAC):
    # Create a DFU command PDU for entering DFU mode
    dfu_cmd = app_frames.SmacDfuPdu(
        version=1,
        attrib=0,
        err=0,
        code=app_frames.SmacDfuCmd.BOOT_CTL.value,
        data=bytes([app_frames.SmacDfuState.ACTIVE.value])
    )
        
    # try up to 100 times to activate DFU mode
    for _ in range(10000):
        try:
            logger.info("Sending command to enter DFU mode...")

            mac.send_frame(dfu_cmd.to_bytes())
            received_sdu = mac.receive_frame(timeout=100) 
            resp_pdu = app_frames.SmacDfuPdu.from_bytes(received_sdu)
            
            if (resp_pdu.code == app_frames.SmacDfuCmd.BOOT_CTL.value):
                if (resp_pdu.attrib & app_frames.CMD_ATTR_RESP) == 0:
                    logger.error("No RESP flag set in the response while entering DFU mode")
                    return False
            
                if (resp_pdu.attrib & app_frames.CMD_ATTR_ERR) != 0:
                    logger.error(f"Device reported error {resp_pdu.get_error()} while entering DFU mode: {resp_pdu.get_error_string()}")
                    return False
                
                logger.info("Device entered DFU mode successfully.")
                return True                    
            else:
                logger.debug(f"Unexpected response opcode={resp_pdu.get_code()} from the device while entering DFU mode")
                
        except Exception as e:
            # print what the exception text and continue trying until we exhaust all attempts
            logger.error(f"Exception: {e}")
            
    logger.error("Failed to enter DFU mode after multiple attempts.")

    return False

def dfu_reboot(mac: fwt_mac.SerialMAC):
    # Create a DFU command PDU for rebooting the device
    dfu_cmd = app_frames.SmacDfuPdu(
        version=1,
        attrib=0,
        err=0,
        code=app_frames.SmacDfuCmd.REBOOT.value,
        data=b''
    )

    try:
        logger.info("Sending command to reboot the device...")

        mac.send_frame(dfu_cmd.to_bytes())
        received_sdu = mac.receive_frame(timeout=1000)
        resp_pdu = app_frames.SmacDfuPdu.from_bytes(received_sdu)

        if resp_pdu.code != app_frames.SmacDfuCmd.REBOOT.value:
            logger.error(f"Received an unexpected response opcode={resp_pdu.get_code()} from the device while requesting reboot.")
            return False

        if (resp_pdu.attrib & app_frames.CMD_ATTR_RESP) == 0:
            logger.error("No RESP flag set in the response while requesting reboot")
            return False

        if (resp_pdu.attrib & app_frames.CMD_ATTR_ERR) != 0:
            logger.error(f"Device reported error {resp_pdu.get_error()} while rebooting: {resp_pdu.get_error_string()}")
            return False

        logger.info("Device acknowledged the reboot command, it should be rebooting now.")
        return True
    except Exception as e:
        logger.error(f"Exception while requesting reboot: {e}")
        return False

def dfu_exit(mac: fwt_mac.SerialMAC):
    # Create a DFU command PDU for exiting serial DFU mode, which lets the bootloader proceed to boot the
    # installed application instead of waiting for further DFU commands.
    dfu_cmd = app_frames.SmacDfuPdu(
        version=1,
        attrib=0,
        err=0,
        code=app_frames.SmacDfuCmd.BOOT_CTL.value,
        data=bytes([app_frames.SmacDfuState.INACTIVE.value])
    )

    try:
        logger.info("Sending command to exit serial DFU mode...")

        mac.send_frame(dfu_cmd.to_bytes())
        received_sdu = mac.receive_frame(timeout=1000)
        resp_pdu = app_frames.SmacDfuPdu.from_bytes(received_sdu)

        if resp_pdu.code != app_frames.SmacDfuCmd.BOOT_CTL.value:
            logger.error(f"Received an unexpected response opcode={resp_pdu.get_code()} from the device while exiting DFU mode.")
            return False

        if (resp_pdu.attrib & app_frames.CMD_ATTR_RESP) == 0:
            logger.error("No RESP flag set in the response while exiting DFU mode")
            return False

        if (resp_pdu.attrib & app_frames.CMD_ATTR_ERR) != 0:
            logger.error(f"Device reported error {resp_pdu.get_error()} while exiting DFU mode: {resp_pdu.get_error_string()}")
            return False

        logger.info("Device exited DFU mode, it should be booting the application now.")
        return True
    except Exception as e:
        logger.error(f"Exception while exiting DFU mode: {e}")
        return False

def dfu_upload_container(mac: fwt_mac.SerialMAC, container_data: bytes, type: str):
    slot = slot_id[type]
    sdu_erase = app_frames.SmacDfuExtMemErase(slot=slot)
    
    logger.info(f"Erasing container slot {type}...")
    
    pdu_erase = app_frames.SmacDfuPdu(
        code=app_frames.SmacDfuCmd.EXTM.value,
        data=sdu_erase.to_bytes()
    )
    
    # Send erase command first
    mac.send_frame(pdu_erase.to_bytes())
    v = mac.receive_frame(timeout=15000) # Wait for 15000 ms for a response
    resp_pdu = app_frames.SmacDfuPdu.from_bytes(v)
    
    if (resp_pdu.code == app_frames.SmacDfuCmd.EXTM.value):
        if (resp_pdu.attrib & app_frames.CMD_ATTR_ERR) != 0:
            logger.error(f"Device reported error {resp_pdu.get_error()} while erasing the container slot: {resp_pdu.get_error_string()}")
            return False
        
        if (resp_pdu.attrib & app_frames.CMD_ATTR_RESP) != 0:
            logger.info("Container slot erased successfully, proceeding with upload...")
        else:
            logger.error("No RESP flag set in the response")
            return False
    else:
        logger.error(f"Received an unexpected response opcode={resp_pdu.get_code()} from the device.")
        return False
    
    logger.info(f"Uploading container to slot {type}...")
    
    # send the container data in chunks of up to 64 bytes
    chunk_size = 64
    offset = 0
    prev_percent_complete = -1
    remaning_data_size = len(container_data)
    
    while remaning_data_size > 0:
        chunk_size = min(chunk_size, remaning_data_size)
        chunk = container_data[offset:offset+chunk_size]
        
        sdu_write = app_frames.SmacDfuExtMemWrite(slot, offset=offset, size=len(chunk), data=chunk)
            
        pdu_write = app_frames.SmacDfuPdu(
            code=app_frames.SmacDfuCmd.EXTM.value,
            data=sdu_write.to_bytes()
        )
        
        mac.send_frame(pdu_write.to_bytes())
        v = mac.receive_frame(timeout=5000) # Wait for 5000 ms for a response
        resp_pdu = app_frames.SmacDfuPdu.from_bytes(v)
        
        if (resp_pdu.code == app_frames.SmacDfuCmd.EXTM.value):
            if (resp_pdu.attrib & app_frames.CMD_ATTR_ERR) != 0:
                logger.error(f"Device reported error {resp_pdu.get_error()} while writing chunk at offset {offset}: {resp_pdu.get_error_string()}")
                return False
            if (resp_pdu.attrib & app_frames.CMD_ATTR_RESP) != 0:
                logger.debug(f"Chunk at offset {offset} written successfully.")
            else:
                logger.error(f"No RESP flag set in the response for chunk at offset {offset}")
                return False
        else:
            logger.error(f"Received an unexpected response opcode={resp_pdu.get_code()} from the device for chunk at offset {i}.")
            return False
        
        offset += len(chunk)
        remaning_data_size -= len(chunk)
        
        percent_complete = int((offset / len(container_data)) * 100)
        if percent_complete % 10 == 0 and percent_complete != prev_percent_complete:
            logger.info(f"Uploading... {offset}/{len(container_data)} bytes ({percent_complete}%)")
            prev_percent_complete = percent_complete
        
    return True