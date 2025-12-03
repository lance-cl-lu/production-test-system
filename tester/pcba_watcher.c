#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <sys/stat.h>
#include <curl/curl.h>

#define SHARED_FILE "../shared/pcba_test.txt"
#define API_URL "http://localhost:8000/api/pcba/events"
#define CHECK_INTERVAL 1  // 每秒檢查一次

// 測試階段
const char *stages[] = {"wifi", "firmware", "touch", "bluetooth", "speaker"};
const int num_stages = 5;

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

// POST JSON 到後端
int post_event(const char *json_payload) {
    CURL *curl = curl_easy_init();
    if (!curl) {
        fprintf(stderr, "Failed to init curl\n");
        return -1;
    }

    struct curl_slist *headers = NULL;
    headers = curl_slist_append(headers, "Content-Type: application/json");

    curl_easy_setopt(curl, CURLOPT_URL, API_URL);
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

// 執行單一測試階段
void run_test_stage(const char *stage, const char *serial) {
    char json[512];
    char timestamp[32];
    now_iso(timestamp, sizeof(timestamp));
    
    printf("[PCBA] Testing %s for %s...\n", stage, serial);
    
    // 先送 testing 狀態
    snprintf(json, sizeof(json),
        "{\"serial\":\"%s\",\"stage\":\"%s\",\"status\":\"testing\",\"timestamp\":\"%s\"}",
        serial, stage, timestamp);
    post_event(json);
    
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
    
    post_event(json);
    printf("[PCBA] %s: %s\n", stage, status);
}

// 執行完整測試流程
void run_full_test(const char *serial) {
    printf("\n========================================\n");
    printf("開始測試序號: %s\n", serial);
    printf("========================================\n");
    
    for (int i = 0; i < num_stages; i++) {
        run_test_stage(stages[i], serial);
    }
    
    printf("========================================\n");
    printf("測試完成: %s\n", serial);
    printf("========================================\n\n");
}

int main() {
    srand((unsigned int)time(NULL));
    
    struct stat st_old = {0}, st_new;
    char serial[128];
    
    // 初始化 curl
    curl_global_init(CURL_GLOBAL_ALL);
    
    printf("PCBA 測試監看程式啟動...\n");
    printf("監看檔案: %s\n", SHARED_FILE);
    printf("API 端點: %s\n", API_URL);
    printf("等待測試請求...\n\n");
    
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
            // 讀取序號
            FILE *f = fopen(SHARED_FILE, "r");
            if (f) {
                if (fgets(serial, sizeof(serial), f)) {
                    // 移除換行符
                    serial[strcspn(serial, "\r\n")] = 0;
                    
                    if (strlen(serial) > 0) {
                        // 執行測試
                        run_full_test(serial);
                    }
                }
                fclose(f);
            }
            
            st_old = st_new;
        }
    }
    
    curl_global_cleanup();
    return 0;
}
