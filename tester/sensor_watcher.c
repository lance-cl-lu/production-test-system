/*
 * sensor_watcher.c
 *
 * Sensor IQC 測試監看程式
 *
 * 序號讀取已串接 UART（7 個測試階段仍為模擬）
 * serial port 在啟動時開一次並常駐，避免反覆開關 tty 造成裝置重置
 *
 * 編譯：make sensor_watcher
 * 執行：cd tester && ./sensor_watcher [--port /dev/ttyX] [--debug]
 *
 * 流程：
 *   1. 輪詢 ../shared/sensor_test.txt，等待後端寫入 "SEARCH" 或 "TEST <SERIAL>"
 *   2. SEARCH 讀取 WLE / WBA 兩組序號；TEST 依序跑 7 個測試階段
 *   3. 結果以 HTTP POST 送到後端，再由後端 WebSocket 廣播給前端
 */

#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <sys/stat.h>
#include <curl/curl.h>

#include "uart_hvf.h"
#include "uart_hvf_sensors.h"

#define SHARED_FILE "../shared/sensor_test.txt"
#define API_EVENTS_URL "http://localhost:8000/api/sensor/events"
#define API_SERIAL_FOUND_URL "http://localhost:8000/api/sensor/serial-found"
#define CHECK_INTERVAL 1

// 設為 1.0 讓模擬全數通過，先確認管線；之後可調低來測 FAIL 顯示
#define PASS_RATIO 1.0

// 換板子後裝置的開機訊息可能斷續輸出，要求較長的靜默才視為吐完
#define BOARD_SWAP_IDLE_MS 800

static int uart_fd = -1;
static volatile sig_atomic_t keep_running = 1;

static void handle_signal(int signum) {
    (void)signum;
    keep_running = 0;
}

const char *stages[] = {
    "getSensorIC", "sht41", "ens210", "lps22df", "bme690",
    "getHumidity", "getTemperature",
    "getPressure", "testLeak", "testButton", "testLED", "testBuzzer", "testSPI",
};
const int num_stages = 13;

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

    if (strcmp(stage, "testBuzzer") != 0) {
        send_event(serial, stage, "testing", NULL);
    }

    if (strcmp(stage, "getSensorIC") == 0) {
        uart_hvf_sensor_result_t sensors;
        int probe_ok = uart_hvf_probe_sensors(uart_fd, &sensors) == 0;
        const char *status = probe_ok && sensors.probe_completed ? "pass" : "fail";

        snprintf(detail, sizeof(detail),
                 "\"sht41\":%s,\"ens210\":%s,\"lps22df\":%s,\"bme690\":%s,\"probe_completed\":%s",
                 sensors.sht41 ? "true" : "false",
                 sensors.ens210 ? "true" : "false",
                 sensors.lps22df ? "true" : "false",
                 sensors.bme690 ? "true" : "false",
                 sensors.probe_completed ? "true" : "false");
        send_event(serial, stage, status, detail);
        printf("%s  {%s}\n", status, detail);
        return;
    }

    if (strcmp(stage, "sht41") == 0 || strcmp(stage, "ens210") == 0 ||
        strcmp(stage, "lps22df") == 0 || strcmp(stage, "bme690") == 0) {
        uart_hvf_sensor_measurement_t measurement;
        memset(&measurement, 0, sizeof(measurement));
        int measure_result = uart_hvf_measure_sensor(uart_fd, stage, &measurement);
        const char *status = measure_result == 0 && measurement.ok ? "pass" : "fail";
        int offset = snprintf(detail, sizeof(detail), "\"sensor\":\"%s\",\"detected\":%s",
                              stage, status[0] == 'p' ? "true" : "false");

        if (measurement.temperature_valid) {
            offset += snprintf(detail + offset, sizeof(detail) - (size_t)offset,
                               ",\"temperature\":%.2f", measurement.temperature);
        }
        if (measurement.humidity_valid) {
            offset += snprintf(detail + offset, sizeof(detail) - (size_t)offset,
                               ",\"humidity\":%.2f", measurement.humidity);
        }
        if (measurement.pressure_valid) {
            offset += snprintf(detail + offset, sizeof(detail) - (size_t)offset,
                               ",\"pressure\":%.2f", measurement.pressure);
        }
        if (measurement.gas_resistance_valid) {
            snprintf(detail + offset, sizeof(detail) - (size_t)offset,
                     ",\"gas_resistance\":%.2f", measurement.gas_resistance);
        }
        send_event(serial, stage, status, detail);
        printf("%s  {%s}\n", status, detail);
        return;
    }

    if (strcmp(stage, "testBuzzer") == 0 || strcmp(stage, "testSPI") == 0) {
        int result = strcmp(stage, "testBuzzer") == 0
            ? uart_hvf_test_buzzer(uart_fd, 3000)
            : uart_hvf_test_spi(uart_fd);
        if (strcmp(stage, "testBuzzer") == 0 && result == 0) {
            send_event(serial, stage, "testing", NULL);
            printf("testing  {\"test\":\"testBuzzer\",\"awaiting_user_confirmation\":true}\n");
            return;
        }

        const char *status = result == 0 ? "pass" : "fail";
        snprintf(detail, sizeof(detail), "\"test\":\"%s\",\"executed\":true", stage);
        send_event(serial, stage, status, detail);
        printf("%s  {%s}\n", status, detail);
        return;
    }

    sleep(1);  // 模擬量測耗時；接 UART 後換成實際交握

    const char *status = pass_or_fail(PASS_RATIO);

    if (strcmp(stage, "getHumidity") == 0) {
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

// 依序讀取 WLE 與 WBA 兩組序號，一併回報給後端
void handle_search_command(void) {
    char serial_wle[128];
    char serial_wba[128];
    char payload[384];

    printf("\n[SEARCH] Flushing UART input...\n");
    // 換板子時裝置會吐一段開機訊息，先清乾淨再下指令
    uart_hvf_flush_input(uart_fd, BOARD_SWAP_IDLE_MS);

    printf("[SEARCH] Reading serials from device...\n");

    if (uart_hvf_read_stm32_id(uart_fd, 0, serial_wle, sizeof(serial_wle)) != 0) {
        printf("[SEARCH] Failed to read WLE serial\n\n");
        return;
    }
    printf("[SEARCH] WLE = %s\n", serial_wle);

    if (uart_hvf_read_stm32_id(uart_fd, 1, serial_wba, sizeof(serial_wba)) != 0) {
        printf("[SEARCH] Failed to read WBA serial\n\n");
        return;
    }
    printf("[SEARCH] WBA = %s\n", serial_wba);

    snprintf(payload, sizeof(payload),
             "{\"serial_wle\":\"%s\",\"serial_wba\":\"%s\"}",
             serial_wle, serial_wba);

    if (post_json(API_SERIAL_FOUND_URL, payload) == 0) {
        printf("[SEARCH] Sent to backend\n\n");
    } else {
        printf("[SEARCH] Failed to send serials\n\n");
    }
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

static int is_valid_stage(const char *stage) {
    for (int i = 0; i < num_stages; i++) {
        // printf("[DEBUG] stages[%d]='%s', stage='%s'\n", i, stages[i], stage);
        if (strcmp(stages[i], stage) == 0) {

            return 1;
        }
    }
    return 0;
}

void process_command(const char *line) {
    char clean_line[256];
    char serial[128];
    char stage[64];

    strncpy(clean_line, line, sizeof(clean_line) - 1);
    clean_line[sizeof(clean_line) - 1] = '\0';
    clean_line[strcspn(clean_line, "\r\n")] = 0;

    if (strlen(clean_line) == 0) {
        return;
    }

    if (sscanf(clean_line, "STAGE %63s %127s", stage, serial) == 2) {
        if (!is_valid_stage(stage)) {
            printf("[WARN] Unknown stage: %s\n", stage);
            return;
        }
        printf("\n[STAGE] %s for %s\n", stage, serial);
        run_test_stage(stage, serial);
        printf("\n");
    } else if (sscanf(clean_line, "TEST %127s", serial) == 1) {
        handle_test_command(serial);
    } else if (strncmp(clean_line, "SEARCH", 6) == 0) {
        handle_search_command();
    } else {
        printf("[WARN] Unrecognized command: %s\n", clean_line);
    }
}

static void print_usage(const char *prog) {
    fprintf(stderr, "usage: %s [--port /dev/ttyX] [--debug]\n", prog);
    fprintf(stderr, "  --port   serial port (default: %s)\n", UART_HVF_DEFAULT_PORT);
}

int main(int argc, char **argv) {
    const char *port = UART_HVF_DEFAULT_PORT;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
            port = argv[++i];
        } else if (strcmp(argv[i], "--debug") == 0 || strcmp(argv[i], "-d") == 0) {
            uart_hvf_set_debug(1);
        } else {
            print_usage(argv[0]);
            return 2;
        }
    }

    srand((unsigned int)time(NULL));

    setvbuf(stdout, NULL, _IOLBF, 0);  // 輸出導向檔案時仍即時可見

    struct stat st_old = {0}, st_new;
    char line[256];

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    uart_fd = uart_hvf_open(port);
    if (uart_fd < 0) {
        fprintf(stderr, "Failed to open serial port: %s\n", port);
        return 1;
    }

    curl_global_init(CURL_GLOBAL_ALL);

    printf("========================================\n");
    printf("Sensor IQC 監看程式\n");
    printf("========================================\n");
    printf("Serial port: %s\n", port);
    printf("監看檔案: %s\n", SHARED_FILE);
    printf("事件 API : %s\n", API_EVENTS_URL);
    printf("等待指令 (SEARCH / TEST <SERIAL>)... Ctrl-C 結束\n\n");

    stat(SHARED_FILE, &st_old);

    while (keep_running) {
        sleep(CHECK_INTERVAL);

        if (!keep_running) {
            break;
        }

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

    printf("\nShutting down...\n");
    uart_hvf_close(uart_fd);
    curl_global_cleanup();
    return 0;
}
