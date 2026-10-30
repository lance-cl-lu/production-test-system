# Production Tester

生產測試程式模擬器

## 工具概覽

本目錄包含多個測試工具：

- **tester.py**：Python 測試腳本（批次測試與連續測試）
- **pcba_watcher.c**：整合 UID 搜尋與測試流程的監看程式（詳見 `README_WATCHER.md`）
- **sensor_watcher.c**：Sensor IQC 跨平台共用測試流程；macOS/Linux 與 Windows
  使用不同 platform adapter，但共用 UART 協定、測試順序與 Backend JSON
- **uart_hvf_probe**：UART 探測工具，以 JSON 回報結果
- **trigger_pcba.sh**：一鍵觸發 PCBA 測試的 Shell 腳本
- **Makefile**：編譯 C 程式工具

Windows 的編譯、COM port 選擇及跨平台行為比對方式請見
[`WINDOWS_SENSOR_WATCHER.md`](WINDOWS_SENSOR_WATCHER.md)。

## 安裝

```bash
pip install -r requirements.txt
```

## 設定

複製 `.env.example` 為 `.env` 並配置參數:

```bash
cp .env.example .env
```

## 使用方式

### 1. 單次測試

### 觸發檔案格式（pcba_test.txt）

Watcher 監聽 `../shared/pcba_test.txt`。為了簡化操作，統一以下格式：

- 單行指令：`SERIAL <序號> <動作>`
- `<動作>` 支援：`START`、`STOP`

範例：

```
SERIAL NL-20251204-0001 START
SERIAL NL-20251204-0001 STOP
SERIAL GW-ABCDEF123456 START
```

注意事項：
- 建議每次觸發覆寫整個檔案內容為單一指令，避免混淆。
- Watcher 每次檔案變更時讀取當前最後一行指令並送至後端 API。

### 一鍵觸發腳本

提供 `tester/trigger_pcba.sh`，支援互動模式與參數模式：

用法：

```
# 互動模式（依序輸入序號與動作）
./trigger_pcba.sh

# 參數模式
./trigger_pcba.sh <SERIAL> <START|STOP>

# 範例
./trigger_pcba.sh NL-20251204-0001 START
./trigger_pcba.sh GW-ABCDEF123456 STOP
```

執行前請賦予執行權限：

```
chmod +x ./trigger_pcba.sh
```

腳本行為：
- 會將 `SERIAL <SERIAL> <ACTION>` 寫入 `../shared/pcba_test.txt`（覆寫）。
- 寫入後 `touch` 檔案，讓 watcher 立即偵測到變更。
- 會在終端印出已觸發內容方便確認。

### 後端連線檢查

Watcher 會將指令轉送至後端 `http://localhost:8000/api/pcba/events`。請確保後端服務已啟動並可連線。

### 疑難排解

- 若 watcher 無反應，確認 `../shared/pcba_test.txt` 路徑與權限。
- 若後端未收到事件，確認後端服務與防火牆設定。
執行一次測試並上傳資料:
```bash
python tester.py single
```

### 2. 批次測試
執行指定數量的測試:
```bash
python tester.py batch 20
```

### 3. 連續測試模式
模擬產線持續運作，每隔指定秒數執行測試:
```bash
# 預設每5秒測試一次
python tester.py continuous

# 自訂間隔（例如每3秒）
python tester.py continuous 3
```

## 測試資料說明

程式會自動生成以下測試資料:
- **序號**: 格式 `SN{日期}{流水號}`
- **電壓**: 4.8V - 5.2V (規格: 5V ±2%)
- **電流**: 0.45A - 0.55A (規格: 0.5A ±4%)
- **溫度**: 20°C - 35°C (規格: ≤32°C)
- **測試結果**: 所有參數符合規格為 PASS，否則為 FAIL

## 環境變數

- `API_URL`: FastAPI 後端 API 網址
- `DEVICE_ID`: 測試設備 ID
- `TEST_STATION`: 測試站別名稱

---

## sensor_watcher（Sensor IQC）

### 編譯與執行

```bash
cd tester
make sensor_watcher
./sensor_watcher

# WLE 與 WBA 各自接到獨立 UART 時，SEARCH 直接使用兩邊的 console 讀取序號
./sensor_watcher --port /dev/tty.usbserial-WLE --port2 /dev/tty.usbserial-WBA

# 自動偵測 UART 數量：一個 port 用 WLE + IPC passthrough；兩個 ports 用 WLE/WBA 各自直連
./sensor_watcher --auto

"/Applications/STMicroelectronics/STM32Cube/STM32CubeProgrammer/STM32CubeProgrammer.app/Contents/Resources/bin/STM32_Programmer_CLI" \
  -c "port=SWD index=0 freq=1000" \
  -w "/Users/lance/work/Github/production-test-system/fwpack-special/intertek001.bin" \
  0x080FE000 -v

# 沒有實際硬體時，不會開啟 UART，並產生模擬序號與通過的測試資料
./sensor_watcher --simulate
```

SmartAC-5G qFvV9zFbwgx8nCJsoK9m

`--simulate` 會保留共享檔案與 HTTP/WebSocket 的完整流程，只將 UART 硬體交互換成模擬資料，適合本機開發與前後端整合測試。

指定一個 UART 時維持舊流程：`--port` 連接 WLE，讀 WBA 序號時透過 IPC passthrough。`--auto` 會先列出 serial ports：只找到一個時將它當作 WLE UART 並使用 IPC passthrough；找到兩個時自動偵測哪個是 WLE/WBA，之後在各自 console 直接下 `stm32_id_info`。其他 port 數量會停止並提示，避免猜測。也可明確指定兩個 UART：`--port` 指定 WLE、`--port2` 指定 WBA。

硬體模式啟動後、開始監看指令前，watcher 會在每個已設定的 UART 各執行一次 `hvf_version`，以回應 payload 的 MCU 名稱辨識 WLE/WBA（韌體後綴 `mle` 對應 WLE，`mba` 對應 WBA），並記住 UART 對應。雙 UART 即使參數順序相反也會自動調整；無法辨識或兩個 UART 回報相同 MCU 時會停用 `SEARCH`，避免回報錯誤序號。這次啟動辨識結果會沿用到 watcher 結束，不會每次 SEARCH 重跑版本查詢。

> 必須在 `tester/` 目錄下執行，程式以相對路徑 `../shared/sensor_test.txt` 監看指令。

### 整體架構

Backend 啟動時會先檢查 `http://127.0.0.1:8766/health`。若 watcher 尚未執行，且 Backend 主機上找得到 `tester/sensor_watcher`（Windows 為 `sensor_watcher.exe`），就會以 `--auto` 啟動；Backend 關閉時也會停止自己啟動的 watcher。若執行檔放在其他位置，可在 Backend 設定 `SENSOR_WATCHER_EXECUTABLE`；設為 `AUTO_START_SENSOR_WATCHER=false` 可停用自動啟動。

Sensor IQC 的 UART Detection 標題旁也會顯示 watcher 狀態，並提供 **Start** / **Restart**。Restart 會停止監聽 `8766` 的 watcher 程序，再重新以 `--auto` 啟動；若執行中的程序無法確認為設定的 watcher 執行檔，Backend 會拒絕終止它。

Docker Backend 無法直接操作主機的序列埠，也不包含 watcher 執行檔，因此不會代替主機啟動 watcher。這種部署仍需在接有測試板的主機執行 watcher，或在該主機以原生方式執行 Backend。兩者透過【共享檔案】與【HTTP 回報】解耦：

```mermaid
flowchart LR
    FE["Frontend :3000"]
    BE["Backend :8000<br/>(container)"]
    F["shared/sensor_test.txt<br/>(volume mount)"]
    W["sensor_watcher<br/>(macOS host)"]

    FE -->|POST /api/sensor/*| BE
    BE -->|寫入指令| F
    F -.->|每秒輪詢 mtime| W
    W -->|POST 回報結果| BE
    BE -.->|WebSocket 廣播| FE
```

下行（觸發）走檔案，上行（回報）走 HTTP。watcher 跑在 host 而非容器內，才能直接存取 `/dev/tty.usb*`。

### 流程一：讀取序號

```mermaid
sequenceDiagram
    participant FE as SensorIQC
    participant BE as Backend
    participant F as sensor_test.txt
    participant W as sensor_watcher

    FE->>BE: POST /api/sensor/read-serial
    BE->>F: 寫入 "SEARCH"
    W->>F: 偵測到指令，讀取後清空
    W->>W: ./uart_hvf_probe --test stm32_id_info
    W->>BE: POST /api/sensor/serial-found {serial}
    BE-->>FE: WS {type:"sensor_serial_found"}
    FE->>FE: 自動填入輸入框
```

### 流程二：執行測試

```mermaid
sequenceDiagram
    participant FE as SensorIQC
    participant BE as Backend
    participant F as sensor_test.txt
    participant W as sensor_watcher

    FE->>BE: POST /api/sensor/start-test {serial}
    BE->>F: 寫入 "TEST <serial>"
    BE-->>FE: 200 {status:"triggered"}
    W->>F: 偵測到指令，讀取後清空
    loop 7 個測試階段
        W->>BE: POST /api/sensor/events {status:"testing"}
        BE-->>FE: WS 廣播
        W->>BE: POST /api/sensor/events {status:"pass"|"fail"}
        BE-->>FE: WS 廣播
    end
    FE->>BE: POST /api/test-records/ 儲存結果
```

### 觸發檔案格式（sensor_test.txt）

第一行為指令，第二行為時間戳（目前未使用）：

```
TEST SN-1787021410029
2026-08-18T15:30:10.029123
```

```
SEARCH
2026-08-18T15:30:10.029123
```

watcher 讀取後會立即清空檔案，避免重複觸發。因此直接 `cat shared/sensor_test.txt` 通常看到空內容是正常的。

### 手動測試

不經過前端，直接觸發 watcher：

```bash
echo "TEST SN-MANUAL-001" > ../shared/sensor_test.txt
echo "SEARCH" > ../shared/sensor_test.txt
```

不經過 watcher，直接驗證後端與前端：

```bash
curl -X POST http://localhost:8000/api/sensor/events \
  -H 'Content-Type: application/json' \
    -d '{"serial":"SN-MANUAL-001","stage":"getSensorIC","status":"pass","detail":{"ens210":true,"lps22df":true,"bme690":true,"sht41":false}}'
```

> 前端有 `serial === serialNumber` 的過濾，SN 對不上會被靜默丟棄。

### 測試階段與回報格式

`stage` 必須是下列七者之一，`status` 只能是 `pending` / `testing` / `pass` / `fail`，否則後端回 422：

| stage | detail key | 前端顯示 |
|---|---|---|
| `getSensorIC` | `ens210`, `lps22df`, `bme690`, `sht41` | ✓ |
| `getHumidity` | `humidity` | ✓ |
| `getTemperature` | `temperature` | ✓ |
| `getPressure` | `pressure` | ✓ |
| `testLeak` | `leak_rate` | – |
| `testButton` | `press_count` | – |
| `testGreenLED` | `led_color`, `lux` | – |
| `testOrangeLED` | `led_color`, `lux` | – |

### 接入真實 UART

讀取序號已串接 `uart_hvf_probe`：

```bash
./uart_hvf_probe --port /dev/tty.usbserial-0001 --test stm32_id_info
```

```json
{"test":"stm32_id_info","ok":true,"prompt_seen":true,"data":{"unique_stm32mba_device_id":"203930573546500300250015"}}
```

watcher 以 `popen()` 執行該指令，檢查 `ok` 後從 `data` 取出 `unique_stm32mba_device_id` 作為序號。

尚待接入的是測試階段：`run_test_stage()` 裡的 `sleep(1)` 與 `rand()` 換成實際 UART 交握即可，其餘骨架（輪詢、POST、JSON 組裝）不用動。

> 建議在 `main()` 開一次 serial port 並常駐，不要每個 stage 重開 —— 連續開關 tty 會讓很多裝置重置。

### 設定

| 常數 | 說明 |
|---|---|
| `PROBE_PORT` | serial port，目前寫死 `/dev/tty.usbserial-0001` |
| `PROBE_SERIAL_TEST` | 讀序號的 test 名稱 |
| `PROBE_SERIAL_FIELD` | 從 `data` 取出的欄位名 |
| `PASS_RATIO` | 設為 `1.0` 讓模擬全數通過；調低可測試 FAIL 顯示 |
| `SHARED_FILE` | 監看的指令檔路徑 |
| `API_EVENTS_URL` | 測試事件回報端點 |
| `API_SERIAL_FOUND_URL` | 序號回報端點 |

### 疑難排解

| 症狀 | 原因 |
|---|---|
| watcher 完全沒反應 | 未在 `tester/` 目錄下執行，相對路徑對不上 |
| `Probe reported ok=false` | 裝置未連接、port 錯誤或裝置未就緒 |
| `POST rejected by backend: HTTP 422` | `stage` 或 `status` 拼錯 |
| `POST failed: Connection refused` | 後端未啟動 |
| watcher 有跡、前端無反應 | serial 對不上，或 WebSocket 未連線 |
