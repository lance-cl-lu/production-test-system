/*
 * sensor_watcher.c
 *
 * Sensor IQC 測試監看程式
 *
 * 序號讀取與 Sensor/HVF 測試均串接 UART
 * serial port 在啟動時開一次並常駐，避免反覆開關 tty 造成裝置重置
 *
 * 編譯：make sensor_watcher
 * 執行：cd tester && ./sensor_watcher [--port /dev/ttyX] [--debug] [--simulate]
 *
 * 流程：
 *   1. 輪詢 ../shared/sensor_test.txt，等待後端寫入 "SEARCH" 或 "TEST <SERIAL>"
 *   2. SEARCH 讀取 WLE / WBA；TEST/STAGE 都先探測 Sensor IC 再執行
 *   3. 結果以 HTTP POST 送到後端，再由後端 WebSocket 廣播給前端
 */

#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <fcntl.h>
#include <curl/curl.h>

#include "uart_hvf.h"
#include "uart_hvf_sensors.h"

#define SHARED_FILE "../shared/sensor_test.txt"
#define API_EVENTS_URL "http://localhost:8000/api/sensor/events"
#define API_SERIAL_FOUND_URL "http://localhost:8000/api/sensor/serial-found"
#define CHECK_INTERVAL 1
#define WATCHER_LOCK_FILE "/tmp/production-test-system-sensor-watcher.lock"

// 設為 1.0 讓模擬全數通過，先確認管線；之後可調低來測 FAIL 顯示
#define PASS_RATIO 1.0

// 換板子後裝置的開機訊息可能斷續輸出，要求較長的靜默才視為吐完
#define BOARD_SWAP_IDLE_MS 800

static int uart_fd = -1;
static int watcher_lock_fd = -1;
static int simulate_mode = 0;
static volatile sig_atomic_t keep_running = 1;

static int stat_mtime_equal(const struct stat *a, const struct stat *b) {
#ifdef __APPLE__
    return a->st_mtimespec.tv_sec == b->st_mtimespec.tv_sec &&
           a->st_mtimespec.tv_nsec == b->st_mtimespec.tv_nsec;
#else
    return a->st_mtim.tv_sec == b->st_mtim.tv_sec &&
           a->st_mtim.tv_nsec == b->st_mtim.tv_nsec;
#endif
}

static void handle_signal(int signum) {
    (void)signum;
    keep_running = 0;
}

const char *stages[] = {
    "getSensorIC", "sht41", "ens210", "lps22df", "bme690",
    "testButton", "testGreenLED", "testOrangeLED", "testBuzzer", "testSPI",
};
const int num_stages = 10;

static uart_hvf_sensor_result_t last_sensor_probe;
static char last_serial_wba[128] = "";
static char sensor_probe_serial[128] = "";
static int sensor_probe_valid = 0;

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
    char json[1024];
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
    const int uart_available = (uart_fd >= 0);

    printf("[TEST] %-16s ... ", stage);
    fflush(stdout);

    if (strcmp(stage, "testBuzzer") != 0 &&
        strcmp(stage, "testGreenLED") != 0 &&
        strcmp(stage, "testOrangeLED") != 0 &&
        strcmp(stage, "testGreenLEDOff") != 0 &&
        strcmp(stage, "testOrangeLEDOff") != 0) {
        send_event(serial, stage, "testing", NULL);
    }

    if (simulate_mode) {
        printf("[SIMULATE] ");
    } else if (!uart_available) {
        fprintf(stderr, "[WARN] UART unavailable for stage '%s'\n", stage);
    }

    if (strcmp(stage, "getSensorIC") == 0) {
        if (simulate_mode) {
            memset(&last_sensor_probe, 0, sizeof(last_sensor_probe));
            last_sensor_probe.ens210 = 1;
            last_sensor_probe.lps22df = 1;
            last_sensor_probe.bme690 = 1;
            last_sensor_probe.probe_completed = 1;
            sensor_probe_valid = 1;
            snprintf(sensor_probe_serial, sizeof(sensor_probe_serial), "%s", serial);
            snprintf(detail, sizeof(detail),
                     "\"sht41\":false,\"ens210\":true,\"lps22df\":true,\"bme690\":true,\"probe_completed\":true");
            send_event(serial, stage, "pass", detail);
            printf("pass  {%s}\n", detail);
            return;
        }
        if (!uart_available) {
            snprintf(detail, sizeof(detail),
                     "\"sht41\":false,\"ens210\":false,\"lps22df\":false,\"bme690\":false,\"probe_completed\":false");
            send_event(serial, stage, "fail", detail);
            printf("fail  {%s}\n", detail);
            return;
        }

        uart_hvf_sensor_result_t sensors;
        memset(&sensors, 0, sizeof(sensors));
        int probe_ok = uart_hvf_probe_sensors(uart_fd, &sensors) == 0;
        last_sensor_probe = sensors;
        const char *status = probe_ok && sensors.probe_completed ? "pass" : "fail";
        sensor_probe_valid = probe_ok && sensors.probe_completed;
        if (sensor_probe_valid) {
            snprintf(sensor_probe_serial, sizeof(sensor_probe_serial), "%s", serial);
        } else {
            sensor_probe_serial[0] = '\0';
        }

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
        if (simulate_mode) {
            int offset = snprintf(detail, sizeof(detail),
                                  "\"sensor\":\"%s\",\"detected\":true", stage);
            if (strcmp(stage, "sht41") == 0 || strcmp(stage, "ens210") == 0 ||
                strcmp(stage, "bme690") == 0) {
                offset += snprintf(detail + offset, sizeof(detail) - (size_t)offset,
                                   ",\"temperature\":%.2f,\"humidity\":%.2f",
                                   22.0 + (rand() % 80) / 10.0,
                                   40.0 + (rand() % 200) / 10.0);
            }
            if (strcmp(stage, "lps22df") == 0 || strcmp(stage, "bme690") == 0) {
                offset += snprintf(detail + offset, sizeof(detail) - (size_t)offset,
                                   ",\"pressure\":%.2f", 995.0 + (rand() % 250) / 10.0);
            }
            if (strcmp(stage, "bme690") == 0) {
                snprintf(detail + offset, sizeof(detail) - (size_t)offset,
                         ",\"gas_resistance\":%.2f", 8000.0 + (rand() % 4000));
            }
            send_event(serial, stage, "pass", detail);
            printf("pass  {%s}\n", detail);
            return;
        }
        if (!uart_available) {
            snprintf(detail, sizeof(detail), "\"sensor\":\"%s\",\"detected\":false", stage);
            send_event(serial, stage, "fail", detail);
            printf("fail  {%s}\n", detail);
            return;
        }

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
        if (simulate_mode) {
            if (strcmp(stage, "testBuzzer") == 0) {
                send_event(serial, stage, "testing", NULL);
                printf("testing  {\"test\":\"testBuzzer\",\"awaiting_user_confirmation\":true}\n");
                return;
            }
            const char *status = pass_or_fail(PASS_RATIO);
            snprintf(detail, sizeof(detail), "\"test\":\"%s\",\"executed\":true", stage);
            send_event(serial, stage, status, detail);
            printf("%s  {%s}\n", status, detail);
            return;
        }
        if (!uart_available) {
            snprintf(detail, sizeof(detail), "\"test\":\"%s\",\"executed\":false", stage);
            send_event(serial, stage, "fail", detail);
            printf("fail  {%s}\n", detail);
            return;
        }

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

    if (strcmp(stage, "testOrangeLED") == 0 || strcmp(stage, "testGreenLED") == 0) {
        if (simulate_mode) {
            int led_index = strcmp(stage, "testOrangeLED") == 0 ? 1 : 2;
            send_event(serial, stage, "testing", NULL);
            printf("testing  {\"led_color\":\"%s\",\"led_index\":%d,\"awaiting_user_confirmation\":true}\n",
                   led_index == 1 ? "orange" : "blue", led_index);
            return;
        }
        if (!uart_available) {
            snprintf(detail, sizeof(detail), "\"led_color\":\"%s\",\"executed\":false",
                     strcmp(stage, "testOrangeLED") == 0 ? "orange" : "green");
            send_event(serial, stage, "fail", detail);
            printf("fail  {%s}\n", detail);
            return;
        }

        int led_index = strcmp(stage, "testOrangeLED") == 0 ? 1 : 2;
        int result = uart_hvf_test_led(uart_fd, led_index);
        if (result == 0) {
            send_event(serial, stage, "testing", NULL);
            printf("testing  {\"led_color\":\"%s\",\"led_index\":%d,\"awaiting_user_confirmation\":true}\n",
                   led_index == 1 ? "orange" : "blue", led_index);
            return;
        }

        snprintf(detail, sizeof(detail), "\"led_color\":\"%s\",\"led_index\":%d",
                 led_index == 1 ? "orange" : "blue", led_index);
        send_event(serial, stage, "fail", detail);
        printf("fail  {%s}\n", detail);
        return;
    }

    if (strcmp(stage, "testOrangeLEDOff") == 0 || strcmp(stage, "testGreenLEDOff") == 0) {
        if (simulate_mode) {
            printf("[LED] %s index=%d => simulated ok\n",
                   stage,
                   strcmp(stage, "testOrangeLEDOff") == 0 ? 1 : 2);
            return;
        }
        if (!uart_available) {
            printf("[LED] %s => skipped (UART unavailable)\n", stage);
            return;
        }

        int led_index = strcmp(stage, "testOrangeLEDOff") == 0 ? 1 : 2;
        int result = uart_hvf_set_led(uart_fd, led_index, 0);
        printf("[LED] %s index=%d => %s\n",
               stage, led_index, result == 0 ? "ok" : "fail");
        return;
    }

    if (strcmp(stage, "testButton") == 0) {
        if (simulate_mode) {
            const char *status = pass_or_fail(PASS_RATIO);
            snprintf(detail, sizeof(detail), "\"press_count\":%d,\"window_s\":%d",
                     strcmp(status, "pass") == 0 ? 1 : 0, 3);
            send_event(serial, stage, status, detail);
            printf("%s  {%s}\n", status, detail);
            return;
        }
        if (!uart_available) {
            snprintf(detail, sizeof(detail), "\"press_count\":0,\"window_s\":0");
            send_event(serial, stage, "fail", detail);
            printf("fail  {%s}\n", detail);
            return;
        }

        int wait_seconds = 3;
        int result = uart_hvf_test_button(uart_fd, wait_seconds);
        const char *status = result == 0 ? "pass" : "fail";
        snprintf(detail, sizeof(detail), "\"press_count\":%d,\"window_s\":%d",
                 result == 0 ? 1 : 0, wait_seconds);
        send_event(serial, stage, status, detail);
        printf("%s  {%s}\n", status, detail);
        return;
    }

    send_event(serial, stage, "fail", "\"error\":\"unsupported stage\"");
    printf("fail  {unsupported stage}\n");
}

// 依序讀取 WLE 與 WBA 兩組序號，一併回報給後端
void handle_search_command(void) {
    char serial_wle[128];
    char serial_wba[128];
    char payload[384];

    // SEARCH 代表可能已換板，舊板的 Sensor IC 探測結果不可沿用。
    sensor_probe_valid = 0;
    sensor_probe_serial[0] = '\0';
    memset(&last_sensor_probe, 0, sizeof(last_sensor_probe));

    if (simulate_mode) {
        printf("\n[SEARCH] Generating simulated serials...\n");
        snprintf(serial_wle, sizeof(serial_wle), "SIM-WLE-%ld", (long)time(NULL));
        snprintf(serial_wba, sizeof(serial_wba), "SIM-WBA-%ld", (long)time(NULL));
    } else {
        if (uart_fd < 0) {
            printf("\n[SEARCH] UART unavailable; cannot read serials\n\n");
            return;
        }

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
    }

    snprintf(last_serial_wba, sizeof(last_serial_wba), "%s", serial_wba);

    snprintf(payload, sizeof(payload),
             "{\"serial_wle\":\"%s\",\"serial_wba\":\"%s\"}",
             serial_wle, serial_wba);

    if (post_json(API_SERIAL_FOUND_URL, payload) == 0) {
        printf("[SEARCH] Sent to backend\n\n");
    } else {
        printf("[SEARCH] Failed to send serials\n\n");
    }
}

static int sensor_is_detected(const char *stage) {
    if (strcmp(stage, "sht41") == 0) return last_sensor_probe.sht41;
    if (strcmp(stage, "ens210") == 0) return last_sensor_probe.ens210;
    if (strcmp(stage, "lps22df") == 0) return last_sensor_probe.lps22df;
    if (strcmp(stage, "bme690") == 0) return last_sensor_probe.bme690;
    return 1;
}

static int stage_requires_sensor_probe(const char *stage) {
    return strcmp(stage, "sht41") == 0 ||
           strcmp(stage, "ens210") == 0 ||
           strcmp(stage, "lps22df") == 0 ||
           strcmp(stage, "bme690") == 0;
}

static void send_test_complete(const char *serial, const char *mode,
                               const char *requested_stage,
                               const char *expected_json) {
    char detail[640];
    snprintf(detail, sizeof(detail),
             "\"run_mode\":\"%s\",\"requested_stage\":\"%s\","
             "\"serial_wba\":\"%s\",\"expected_stages\":%s",
             mode, requested_stage ? requested_stage : "", last_serial_wba, expected_json);
    send_event(serial, "testComplete", "pass", detail);
}

void handle_test_command(const char *serial) {
    printf("\n========================================\n");
    printf("[TEST] Starting sensor test: %s\n", serial);
    printf("========================================\n");

    memset(&last_sensor_probe, 0, sizeof(last_sensor_probe));
    run_test_stage("getSensorIC", serial);

    char expected[384] = "[\"getSensorIC\"";
    const char *ordered_stages[] = {
        "sht41", "ens210", "lps22df", "bme690",
        "testButton", "testGreenLED", "testOrangeLED", "testBuzzer", "testSPI"
    };
    for (size_t i = 0; i < sizeof(ordered_stages) / sizeof(ordered_stages[0]); i++) {
        const char *stage = ordered_stages[i];
        if (!sensor_is_detected(stage)) {
            printf("[TEST] %-16s ... skipped (not detected)\n", stage);
            continue;
        }
        strncat(expected, ",\"", sizeof(expected) - strlen(expected) - 1);
        strncat(expected, stage, sizeof(expected) - strlen(expected) - 1);
        strncat(expected, "\"", sizeof(expected) - strlen(expected) - 1);
        run_test_stage(stage, serial);
    }
    strncat(expected, "]", sizeof(expected) - strlen(expected) - 1);
    send_test_complete(serial, "full", "", expected);

    printf("========================================\n");
    printf("[TEST] Completed: %s\n\n", serial);
}

static void handle_stage_command(const char *stage, const char *serial) {
    if (strcmp(stage, "getSensorIC") == 0) {
        memset(&last_sensor_probe, 0, sizeof(last_sensor_probe));
        run_test_stage("getSensorIC", serial);
        send_test_complete(serial, "single", stage, "[\"getSensorIC\"]");
        return;
    }

    int probed_for_this_stage = 0;
    // simulate 的非感測器單項測試不需要先跑 getSensorIC。
    // 實機模式保留原本流程，確保測試前已完成裝置探測。
    const int needs_probe = !simulate_mode || stage_requires_sensor_probe(stage);
    if (needs_probe &&
        (!sensor_probe_valid || strcmp(sensor_probe_serial, serial) != 0)) {
        memset(&last_sensor_probe, 0, sizeof(last_sensor_probe));
        run_test_stage("getSensorIC", serial);
        probed_for_this_stage = 1;
    }

    if (!sensor_is_detected(stage)) {
        char detail[160];
        snprintf(detail, sizeof(detail),
                 "\"sensor\":\"%s\",\"detected\":false,\"error\":\"sensor not detected\"", stage);
        send_event(serial, stage, "fail", detail);
    } else {
        run_test_stage(stage, serial);
    }

    char expected[192];
    if (probed_for_this_stage) {
        snprintf(expected, sizeof(expected), "[\"getSensorIC\",\"%s\"]", stage);
    } else {
        snprintf(expected, sizeof(expected), "[\"%s\"]", stage);
    }
    send_test_complete(serial, "single", stage, expected);
}

static int is_valid_stage(const char *stage) {
    if (strcmp(stage, "testGreenLEDOff") == 0 || strcmp(stage, "testOrangeLEDOff") == 0) {
        return 1;
    }

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
        if (strcmp(stage, "testGreenLEDOff") == 0 || strcmp(stage, "testOrangeLEDOff") == 0) {
            run_test_stage(stage, serial);
        } else {
            handle_stage_command(stage, serial);
        }
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
    fprintf(stderr, "usage: %s [--port /dev/ttyX] [--debug] [--simulate]\n", prog);
    fprintf(stderr, "  --port   serial port (default: %s)\n", UART_HVF_DEFAULT_PORT);
    fprintf(stderr, "  --simulate  run without UART hardware and generate passing test data\n");
}

int main(int argc, char **argv) {
    const char *port = UART_HVF_DEFAULT_PORT;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
            port = argv[++i];
        } else if (strcmp(argv[i], "--debug") == 0 || strcmp(argv[i], "-d") == 0) {
            uart_hvf_set_debug(1);
        } else if (strcmp(argv[i], "--simulate") == 0) {
            simulate_mode = 1;
        } else {
            print_usage(argv[0]);
            return 2;
        }
    }

    srand((unsigned int)time(NULL));

    watcher_lock_fd = open(WATCHER_LOCK_FILE, O_CREAT | O_RDWR, 0666);
    if (watcher_lock_fd < 0 || flock(watcher_lock_fd, LOCK_EX | LOCK_NB) != 0) {
        fprintf(stderr, "[ERROR] Another sensor_watcher is already running\n");
        if (watcher_lock_fd >= 0) close(watcher_lock_fd);
        return 1;
    }

    setvbuf(stdout, NULL, _IOLBF, 0);  // 輸出導向檔案時仍即時可見

    struct stat st_old = {0}, st_new;
    char line[256];

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    if (!simulate_mode) {
        uart_fd = uart_hvf_open(port);
        if (uart_fd < 0) {
            fprintf(stderr, "[WARN] Failed to open serial port: %s\n", port);
        }
    }

    curl_global_init(CURL_GLOBAL_ALL);

    printf("========================================\n");
    printf("Sensor IQC 監看程式\n");
    printf("========================================\n");
    printf("Mode       : %s\n", simulate_mode ? "SIMULATE (no hardware)" : "HARDWARE");
    printf("Serial port: %s\n", simulate_mode ? "disabled" : port);
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

        // UI 可能在同一秒內連續寫入 LED Off 與下一個測項，
        // 只比較秒會漏掉後一筆，因此必須連奈秒一起比較。
        if (stat_mtime_equal(&st_new, &st_old)) {
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
    flock(watcher_lock_fd, LOCK_UN);
    close(watcher_lock_fd);
    curl_global_cleanup();
    return 0;
}
