"""sid_reg_wait as a package: put smac_tools/run_ui/tools on sys.path, then `import sid_reg_wait`.

  import sid_reg_wait
  line = sid_reg_wait.wait_registration(timeout=300)     # raises sid_reg_wait.SidRegWaitError

See sid_reg_wait.py (the CLI) and README.md.
"""

from .sid_reg_wait import (DEFAULT_BAUD, DEFAULT_PASS, DEFAULT_TIMEOUT, SidRegWaitError, close_logs, collect, find_port,
                           list_ports, main, open_logs, open_port, port_devices, reset_device, wait_registration, watch)

__all__ = ["wait_registration", "watch", "collect", "find_port", "port_devices", "open_logs", "close_logs",
           "reset_device", "list_ports", "open_port", "main", "SidRegWaitError", "DEFAULT_PASS", "DEFAULT_TIMEOUT",
           "DEFAULT_BAUD"]
