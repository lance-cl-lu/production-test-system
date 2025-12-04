# PCBA 測試監看程式

這個 C 程式會監看 `shared/pcba_test.txt` 檔案的變化，當前端觸發測試時自動執行。

## 編譯

需要安裝 libcurl：

```bash
# macOS
brew install curl

# 編譯（方式一：直接 gcc）
cd tester
gcc -o pcba_watcher pcba_watcher.c -lcurl

# 若遇到找不到 curl headers 或 libraries，可指定 Homebrew 的 include/lib 路徑：
gcc -I"$(brew --prefix curl)/include" -L"$(brew --prefix curl)/lib" -o pcba_watcher pcba_watcher.c -lcurl

# 編譯（方式二：使用 Makefile）
make
```

Makefile 目標（於 `tester/Makefile`）：

```
# 預設：建置二進位
make

# 乾淨重建
make clean && make
```

## 執行

```bash
# 在專案根目錄執行
cd /Users/lance/Documents/GitHub/production-test-system/tester
./pcba_watcher

# 或使用 Makefile 的 run 目標（若已提供）
make run
```

程式會持續運行並顯示：
```
PCBA 測試監看程式啟動...
監看檔案: ../shared/pcba_test.txt
API 端點: http://localhost:8000/api/pcba/events
等待測試請求...
```

## 使用流程

1. 啟動此 C 程式（在 Mac 上）
2. 打開網頁 `http://localhost:3001/pcba-iqc`
3. 輸入序號，例如：`NL20231203007`
4. 按「開始測試」
5. C 程式自動檢測到請求，開始測試
6. 測試結果即時顯示在網頁上
7. 完成後自動儲存到資料庫

## 測試流程

每個序號會依序執行 5 個測試項目：
1. WiFi
2. Firmware
3. Touch
4. Bluetooth  
5. Speaker

每個項目會：
- 先送 `testing` 狀態
- 模擬測試 1 秒
- 送最終結果 `pass` 或 `fail`

## 停止程式

按 `Ctrl+C` 停止監看程式。
