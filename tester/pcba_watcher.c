/*
 * pcba_watcher.c
 * 
 * PCBA 測試監看程式（整合 UID 搜尋功能）
 * 
 * 編譯方式：
 *   make pcba_watcher
 * 或：
 *   gcc -O2 -Wall -I$(brew --prefix curl)/include -L$(brew --prefix curl)/lib \
 *       -o pcba_watcher pcba_watcher.c -lcurl
 * 
 * 功能：
 * 1. 監聽 ../shared/pcba_test.txt 檔案變更
 * 2. 處理兩種指令：
 *    - SEARCH：產生虛擬 UID 並透過 HTTP POST 回傳給後端
 *    - TEST <UID>：執行完整測試流程並回報結果
 * 3. 所有結果透過 HTTP POST 傳送至後端，再透過 WebSocket 廣播給前端
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <sys/stat.h>
#include <curl/curl.h>

#define SHARED_FILE "../shared/pcba_test.txt"
#define API_EVENTS_URL "http://localhost:8000/api/pcba/events"
#define API_UID_FOUND_URL "http://localhost:8000/api/pcba/uid-found"
#define CHECK_INTERVAL 1  // 每秒檢查一次

// 測試階段
const char *stages[] = {"wifi", "firmware", "touch", "bluetooth", "speaker"};
const int num_stages = 5;

// 產生虛擬 UID（格式：NL-YYYYMMDD-XXXX）
void generate_virtual_uid(char* uid, size_t max_len) {
    time_t now = time(NULL);
    struct tm* t = localtime(&now);
    int random_suffix = rand() % 10000;
    
    snprintf(uid, max_len, "NL-%04d%02d%02d-%04d",
             t->tm_year + 1900,
             t->tm_mon + 1,
             t->tm_mday,
             random_suffix);
}

// 簡單隨機 PASS/FAIL
static const char* pass_or_fail(double pass_ratio) {
    double r = (double)rand() / (double)RAND_MAX;
    return r < pass_ratio ? "pass" : "fail";
}

static void now_iso(char *buf, size_t len) {
    time_t t = time(NULL);
    struct tm tm;
    gmtime_r(&t, &tm);
    strftime(buf, len, "%Y-%m-%dT%H:%M:%SZ", &tm);
}

// POST JSON 到指定 URL
int post_json(const char *url, const char *json_payload) {
    CURL *curl = curl_easy_init();
    if (!curl) {
        fprintf(stderr, "Failed to init curl\n");
        return -1;
    }

    struct curl_slist *headers = NULL;
    headers = curl_slist_append(headers, "Content-Type: application/json");

    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_payload);
    curl_easy_setopt(curl, CURLOPT_VERBOSE, 0L);

    CURLcode res = curl_easy_perform(curl);
    
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        fprintf(stderr, "POST failed: %s\n", curl_easy_strerror(res));
        return -1;
    }
    
    return 0;
}

// 處理 SEARCH 指令：產生並回傳虛擬 UID
void handle_search_command() {
    char uid[64];
    char json[256];
    
    printf("\n[SEARCH] Generating virtual UID...\n");
    
    // 模擬搜尋延遲
    sleep(1);
    
    // 產生虛擬 UID
    generate_virtual_uid(uid, sizeof(uid));
    printf("[SEARCH] Generated UID: %s\n", uid);
    
    // 構建 JSON 並 POST 到 uid-found 端點
    snprintf(json, sizeof(json), "{\"uid\":\"%s\"}", uid);
    
    printf("[SEARCH] Sending UID to backend: %s\n", API_UID_FOUND_URL);
    if (post_json(API_UID_FOUND_URL, json) == 0) {
        printf("[SEARCH] ✓ UID sent successfully\n");
    } else {
        printf("[SEARCH] ✗ Failed to send UID\n");
    }
    printf("\n");
}

// 執行單一測試階段
void run_test_stage(const char *stage, const char *serial) {
    char json[512];
    char timestamp[32];
    now_iso(timestamp, sizeof(timestamp));
    
    printf("[TEST] Testing %s for %s...\n", stage, serial);
    
    // 先送 testing 狀態
    snprintf(json, sizeof(json),
        "{\"serial\":\"%s\",\"stage\":\"%s\",\"status\":\"testing\",\"timestamp\":\"%s\"}",
        serial, stage, timestamp);
    post_json(API_EVENTS_URL, json);
    
    // 模擬測試延遲
    sleep(1);
    
    // 產生測試結果
    const char *status = NULL;
    char detail[128] = "";
    
    if (strcmp(stage, "wifi") == 0) {
        int rssi = -30 - (rand() % 40);
        status = pass_or_fail(0.85);
        snprintf(detail, sizeof(detail), "\"rssi\":%d", rssi);
    } else if (strcmp(stage, "firmware") == 0) {
        status = pass_or_fail(0.95);
        snprintf(detail, sizeof(detail), "\"version\":\"1.%d.%d\"", rand() % 10, rand() % 20);
    } else if (strcmp(stage, "touch") == 0) {
        int passed = 0;
        for (int i = 0; i < 3; i++) {
            if (strcmp(pass_or_fail(0.9), "pass") == 0) passed++;
        }
        status = (passed == 3) ? "pass" : "fail";
        snprintf(detail, sizeof(detail), "\"passed\":%d,\"total\":3", passed);
    } else if (strcmp(stage, "bluetooth") == 0) {
        int rssi = -40 - (rand() % 30);
        status = pass_or_fail(0.9);
        snprintf(detail, sizeof(detail), "\"rssi\":%d", rssi);
    } else if (strcmp(stage, "speaker") == 0) {
        int spl = 70 + (rand() % 20);
        status = pass_or_fail(0.8);
        snprintf(detail, sizeof(detail), "\"spl_db\":%d", spl);
    }
    
    now_iso(timestamp, sizeof(timestamp));
    snprintf(json, sizeof(json),
        "{\"serial\":\"%s\",\"stage\":\"%s\",\"status\":\"%s\",\"detail\":{%s},\"timestamp\":\"%s\"}",
        serial, stage, status, detail, timestamp);
    
    post_json(API_EVENTS_URL, json);
    printf("[TEST] %s: %s\n", stage, status);
}

// 處理 TEST 指令：執行完整測試流程
void handle_test_command(const char *serial) {
    printf("\n========================================\n");
    printf("[TEST] Starting test for: %s\n", serial);
    printf("========================================\n");
    
    for (int i = 0; i < num_stages; i++) {
        run_test_stage(stages[i], serial);
    }
    
    printf("========================================\n");
    printf("[TEST] Test completed: %s\n", serial);
    printf("========================================\n\n");
}

// 解析並處理指令
void process_command(const char *line) {
    char command[128];
    char serial[128];
    
    // 移除換行符
    char clean_line[256];
    strncpy(clean_line, line, sizeof(clean_line) - 1);
    clean_line[sizeof(clean_line) - 1] = '\0';
    clean_line[strcspn(clean_line, "\r\n")] = 0;
    
    if (strlen(clean_line) == 0) {
        return;
    }
    
    // 嘗試解析 "TEST <SERIAL>" 格式
    if (sscanf(clean_line, "TEST %s", serial) == 1) {
        handle_test_command(serial);
    }
    // 檢查是否為 SEARCH 指令
    else if (strncmp(clean_line, "SEARCH", 6) == 0) {
        handle_search_command();
    }
    // 舊格式相容：單純序號視為 TEST 指令
    else if (strlen(clean_line) > 0) {
        printf("[INFO] Legacy format detected, treating as TEST command\n");
        handle_test_command(clean_line);
    }
}

int main() {
    srand((unsigned int)time(NULL));
    
    struct stat st_old = {0}, st_new;
    char line[256];
    
    // 初始化 curl
    curl_global_init(CURL_GLOBAL_ALL);
    
    printf("========================================\n");
    printf("PCBA 測試監看程式啟動\n");
    printf("========================================\n");
    printf("監看檔案: %s\n", SHARED_FILE);
    printf("測試事件 API: %s\n", API_EVENTS_URL);
    printf("UID 回報 API: %s\n", API_UID_FOUND_URL);
    printf("\n支援指令：\n");
    printf("  SEARCH          - 產生虛擬 UID\n");
    printf("  TEST <SERIAL>   - 執行測試流程\n");
    printf("========================================\n");
    printf("等待指令...\n\n");
    
    // 取得初始檔案狀態
    stat(SHARED_FILE, &st_old);
    
    while (1) {
        sleep(CHECK_INTERVAL);
        
        if (stat(SHARED_FILE, &st_new) != 0) {
            // 檔案不存在，繼續等待
            continue;
        }
        
        // 檢查檔案是否有更新
        if (st_new.st_mtime != st_old.st_mtime) {
            // 讀取指令
            FILE *f = fopen(SHARED_FILE, "r");
            if (f) {
                if (fgets(line, sizeof(line), f)) {
                    // 只處理非空白指令
                    // 去除換行符
                    line[strcspn(line, "\r\n")] = 0;
                    if (strlen(line) > 0) {
                        process_command(line);
                    }
                }
                fclose(f);
                
                // 清空檔案內容，避免重複處理
                f = fopen(SHARED_FILE, "w");
                if (f) {
                    fclose(f);
                }
                
                // 清空後重新取得檔案狀態
                stat(SHARED_FILE, &st_old);
            } else {
                st_old = st_new;
            }
        }
    }
    
    curl_global_cleanup();
    return 0;
}
