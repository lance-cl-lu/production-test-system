import serial
import fwt_mac
import logging
import argparse
import fwt_services

def main():
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            root.removeHandler(handler)
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] [%(levelname)s]:%(message)s', # Define message format
    )
    
    logger = logging.getLogger(__name__)
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="SerialMAC Frame Sender/Receiver")
    parser.add_argument("port", help="Serial port to use (e.g., /dev/ttyACM0)")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baud rate for the serial port")
    #add argument for the container file to upload the format is --upload sid/gen2/ota <container_file>
    parser.add_argument("--upload", nargs=2, metavar=('TYPE', 'FILE'), help="Upload a container file to the device. TYPE should be either 'SID','GEN2',OTA.")

    boot_group = parser.add_mutually_exclusive_group()
    boot_group.add_argument("--reboot", action="store_true", help="Send a command to reboot the device.")
    boot_group.add_argument("--boot", action="store_true", help="Send a command to exit serial DFU mode and boot the installed application.")

    args = parser.parse_args()

    # Initialize SerialMAC
    try:
        mac = fwt_mac.SerialMAC(port=args.port, baudrate=args.baudrate)
        logger.info(f"Opened serial port {args.port} at {args.baudrate} baud.")

        # Attempt to enter DFU mode
        if fwt_services.dfu_enter(mac) == False:
            print("Failed to enter DFU mode after multiple attempts.")
            import sys
            sys.exit(1)
            
        if args.upload:
            container_type, container_file = args.upload
            with open(container_file, "rb") as f:
                container_data = f.read()
                if fwt_services.dfu_upload_container(mac, container_data, container_type) == False:
                    logger.error("Failed to upload the container.")

        if args.reboot:
            if fwt_services.dfu_reboot(mac) == False:
                logger.error("Failed to reboot the device.")
        elif args.boot:
            if fwt_services.dfu_exit(mac) == False:
                logger.error("Failed to exit DFU mode.")

    except serial.SerialException as e:
        logger.error(f"Failed to open serial port: {e}")
        
if __name__ == "__main__":
    main()
