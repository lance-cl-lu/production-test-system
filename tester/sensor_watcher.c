/*
 * sensor_watcher.c
 *
 * Sensor IQC 測試監看程式（模擬版，尚未接 UART）
 *
 * 編譯：make sensor_watcher
 * 執行：cd tester && ./sensor_watcher
 *
 * 流程：
 *   1. 輪詢 ../shared/sensor_test.txt，等待後端寫入 "TEST <SERIAL>"
 *   2. 依序跑 7 個測試階段，每階段先回報 testing 再回報 pass/fail
 *   3. 結果以 HTTP POST 送到後端，再由後端 WebSocket 廣播給前端
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <sys/stat.h>
#include <curl/curl.h>

#define SHARED_FILE "../shared/sensor_test.txt"
#define API_EVENTS_URL "http://localhost:8000/api/sensor/events"
#define CHECK_INTERVAL 1

// 設為 1.0 讓模擬全數通過，先確認管線；之後可調低來測 FAIL 顯示
#define PASS_RATIO 1.0

const char *stages[] = {
    "getUUID", "getHumidity", "getTemperature",
    "getPressure", "testLeak", "testButton", "testLED",
};
const int num_stages = 7;

static const char *pass_or_fail(double pass_ratio) {
    double r = (double)rand() / (double)RAND_MAX;
    return r < pass_ratio ? "pass" : "fail";
}

static void now_iso(char *buf, size_t len) {
    time_t t = time(NULL);
    struct tm tm;
    gmtime_r(&t, &tm);
    strftime(buf, len, "%Y-%m-%dT%H:%M:%SZ", &tm);
}

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
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 5L);

    CURLcode res = curl_easy_perform(curl);

    long http_code = 0;
    if (res == CURLE_OK) {
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
    }

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        fprintf(stderr, "POST failed: %s\n", curl_easy_strerror(res));
        return -1;
    }
    if (http_code < 200 || http_code >= 300) {
        fprintf(stderr, "POST rejected by backend: HTTP %ld\n  payload: %s\n",
                http_code, json_payload);
        return -1;
    }
    return 0;
}

static void send_event(const char *serial, const char *stage,
                       const char *status, const char *detail_fields) {
    char json[512];
    char timestamp[32];
    now_iso(timestamp, sizeof(timestamp));

    snprintf(json, sizeof(json),
             "{\"serial\":\"%s\",\"stage\":\"%s\",\"status\":\"%s\","
             "\"detail\":{%s},\"timestamp\":\"%s\"}",
             serial, stage, status, detail_fields ? detail_fields : "", timestamp);

    post_json(API_EVENTS_URL, json);
}

// detail 的 key 必須對應前端 SensorIQC.js 的 testData 欄位才會顯示數值
void run_test_stage(const char *stage, const char *serial) {
    char detail[160] = "";

    printf("[TEST] %-16s ... ", stage);
    fflush(stdout);

    send_event(serial, stage, "testing", NULL);
    sleep(1);  // 模擬量測耗時；接 UART 後換成實際交握

    const char *status = pass_or_fail(PASS_RATIO);

    if (strcmp(stage, "getUUID") == 0) {
        snprintf(detail, sizeof(detail), "\"uuid\":\"SM-%08X\"", rand());
    } else if (strcmp(stage, "getHumidity") == 0) {
        snprintf(detail, sizeof(detail), "\"humidity\":%.1f", 40.0 + (rand() % 300) / 10.0);
    } else if (strcmp(stage, "getTemperature") == 0) {
        snprintf(detail, sizeof(detail), "\"temperature\":%.1f", 20.0 + (rand() % 150) / 10.0);
    } else if (strcmp(stage, "getPressure") == 0) {
        snprintf(detail, sizeof(detail), "\"pressure\":%.1f", 990.0 + (rand() % 400) / 10.0);
    } else if (strcmp(stage, "testLeak") == 0) {
        snprintf(detail, sizeof(detail), "\"leak_rate\":%.3f", (rand() % 50) / 1000.0);
    } else if (strcmp(stage, "testButton") == 0) {
        snprintf(detail, sizeof(detail), "\"press_count\":%d", 3);
    } else if (strcmp(stage, "testLED") == 0) {
        snprintf(detail, sizeof(detail), "\"lux\":%d", 100 + (rand() % 400));
    }

    send_event(serial, stage, status, detail);
    printf("%s  {%s}\n", status, detail);
}

void handle_test_command(const char *serial) {
    printf("\n========================================\n");
    printf("[TEST] Starting sensor test: %s\n", serial);
    printf("========================================\n");

    for (int i = 0; i < num_stages; i++) {
        run_test_stage(stages[i], serial);
    }

    printf("========================================\n");
    printf("[TEST] Completed: %s\n\n", serial);
}

void process_command(const char *line) {
    char clean_line[256];
    char serial[128];

    strncpy(clean_line, line, sizeof(clean_line) - 1);
    clean_line[sizeof(clean_line) - 1] = '\0';
    clean_line[strcspn(clean_line, "\r\n")] = 0;

    if (strlen(clean_line) == 0) {
        return;
    }

    if (sscanf(clean_line, "TEST %127s", serial) == 1) {
        handle_test_command(serial);
    } else {
        printf("[WARN] Unrecognized command: %s\n", clean_line);
    }
}

int main(void) {
    srand((unsigned int)time(NULL));

    struct stat st_old = {0}, st_new;
    char line[256];

    curl_global_init(CURL_GLOBAL_ALL);

    printf("========================================\n");
    printf("Sensor IQC 監看程式（模擬模式）\n");
    printf("========================================\n");
    printf("監看檔案: %s\n", SHARED_FILE);
    printf("事件 API : %s\n", API_EVENTS_URL);
    printf("等待指令 (TEST <SERIAL>)...\n\n");

    stat(SHARED_FILE, &st_old);

    while (1) {
        sleep(CHECK_INTERVAL);

        if (stat(SHARED_FILE, &st_new) != 0) {
            continue;
        }

        if (st_new.st_mtime == st_old.st_mtime) {
            continue;
        }

        FILE *f = fopen(SHARED_FILE, "r");
        if (!f) {
            st_old = st_new;
            continue;
        }

        line[0] = '\0';
        if (!fgets(line, sizeof(line), f)) {
            line[0] = '\0';
        }
        fclose(f);

        // 清空檔案，避免同一指令被重複觸發
        f = fopen(SHARED_FILE, "w");
        if (f) {
            fclose(f);
        }
        stat(SHARED_FILE, &st_old);

        if (strlen(line) > 0) {
            process_command(line);
        }
    }

    curl_global_cleanup();
    return 0;
}
