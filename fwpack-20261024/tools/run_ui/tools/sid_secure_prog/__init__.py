"""sid_secure_prog as a package: put smac_tools/run_ui/tools on sys.path, then `import sid_secure_prog`.

  import sid_secure_prog
  result = sid_secure_prog.program("wle.hex", "wba.hex", "sign_key_pub.pem", "spi_flash_factory.bin")

See sid_secure_prog.py (the CLI) and README.md.
"""

from .sid_secure_prog import (SidSecureProgError, check_boot, factory_signatures, free_otp_slot, main, offline_checks,
                              otp_plan, program, read_hex)

__all__ = ["program", "offline_checks", "check_boot", "factory_signatures", "otp_plan", "free_otp_slot", "read_hex",
           "main", "SidSecureProgError"]
