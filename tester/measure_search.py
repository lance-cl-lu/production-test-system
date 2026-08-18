"""量測 SEARCH 從觸發到完成的分段耗時（暫用，量完可刪）。"""
import subprocess
import sys
import time

LOG = "/tmp/sw_measure.log"
SHARED = "../shared/sensor_test.txt"

log_file = open(LOG, "w")
proc = subprocess.Popen(["./sensor_watcher"], stdout=log_file, stderr=subprocess.STDOUT)
time.sleep(3)

try:
    with open(SHARED, "w") as f:
        f.write("SEARCH\n")
    t0 = time.time()

    t_detect = None
    t_wle = None
    t_end = None

    while time.time() - t0 < 30:
        text = open(LOG, errors="ignore").read()
        if t_detect is None and "Reading serials" in text:
            t_detect = time.time()
        if t_wle is None and "WLE =" in text:
            t_wle = time.time()
        if "Sent to backend" in text or "Failed to read" in text:
            t_end = time.time()
            break
        time.sleep(0.02)

    if t_end is None:
        print("timeout")
        sys.exit(1)

    print(f"寫檔 -> 偵測到指令 : {t_detect - t0:5.2f}s   (檔案輪詢)")
    print(f"偵測到 -> WLE 讀完 : {t_wle - t_detect:5.2f}s   (UART direct)")
    print(f"WLE -> WBA 讀完    : {t_end - t_wle:5.2f}s   (UART passthrough)")
    print(f"總計               : {t_end - t0:5.2f}s")
finally:
    proc.terminate()
    proc.wait(timeout=5)
    log_file.close()
