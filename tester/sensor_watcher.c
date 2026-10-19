/*
 * sensor_watcher.c
 *
 * Sensor IQC 測試監看程式
 *
 * 序號讀取與 Sensor/HVF 測試均串接 UART；可為 WLE/WBA 各指定獨立 UART
 * serial port 在啟動時開一次並常駐，避免反覆開關 tty 造成裝置重置
 *
 * 編譯：make sensor_watcher
 * 執行：cd tester && ./sensor_watcher [--port WLE_UART] [--port2 WBA_UART] [--debug] [--simulate]
 *
 * 流程：
 *   1. 輪詢 ../shared/sensor_test.txt，等待後端寫入 "SEARCH" 或 "TEST <SERIAL>"
 *   2. SEARCH 讀取 WLE / WBA；TEST 先探測 Sensor IC，單項 Sensor 測試才會自動探測
 *   3. 結果以 HTTP POST 送到後端，再由後端 WebSocket 廣播給前端
 */

#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <pthread.h>
#include <sys/socket.h>
#include <unistd.h>
#endif
#include "platform_http.h"
#include "platform_io.h"
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

static platform_uart_t uart_fd = PLATFORM_UART_INVALID;
static platform_uart_t uart_fd2 = PLATFORM_UART_INVALID;
static int dual_uart_mode = 0;
static int consoles_detected = 0;
static platform_lock_t watcher_lock = {.value = -1};
static int simulate_mode = 0;
static volatile sig_atomic_t keep_running = 1;
static const char *command_file = SHARED_FILE;
static const char *lock_file = WATCHER_LOCK_FILE;
static char api_events_url[512] = API_EVENTS_URL;
static char api_serial_found_url[512] = API_SERIAL_FOUND_URL;
static char api_uart_detection_result_url[512] = "http://localhost:8000/api/sensor/detect-uart/result";
static char active_port_wle[256] = "";
static char active_port_wba[256] = "";

#define UART_STATUS_HOST "127.0.0.1"
#define UART_STATUS_PORT 8766

int post_json(const char *url, const char *json_payload);

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

static int detect_console_layout(const char **port, const char **port2) {
    char mcu1[8] = "";
    char mcu2[8] = "";
    int detected1 = uart_hvf_detect_mcu(uart_fd, mcu1, sizeof(mcu1)) == 0;
    consoles_detected = 0;

    if (!dual_uart_mode) {
        if (detected1 && strcmp(mcu1, "WLE") == 0) {
            consoles_detected = 1;
            printf("[UART] %s detected as WLE; legacy WBA IPC passthrough enabled\n", *port);
            return 0;
        } else {
            fprintf(stderr, "[UART][ERROR] Expected WLE console on %s, detected %s; SEARCH is disabled\n",
                    *port, detected1 ? mcu1 : "unknown");
            return -1;
        }
    }

    int detected2 = uart_hvf_detect_mcu(uart_fd2, mcu2, sizeof(mcu2)) == 0;
    printf("[UART] %s: %s; %s: %s\n", *port, detected1 ? mcu1 : "unknown",
           *port2, detected2 ? mcu2 : "unknown");

    if (!detected1 || !detected2 || strcmp(mcu1, mcu2) == 0) {
        fprintf(stderr, "[UART][ERROR] Two distinct WLE/WBA consoles were not detected; SEARCH is disabled\n");
        return -1;
    }
    if (strcmp(mcu1, "WBA") == 0) {
        platform_uart_t uart_tmp = uart_fd;
        const char *port_tmp = *port;
        uart_fd = uart_fd2;
        uart_fd2 = uart_tmp;
        *port = *port2;
        *port2 = port_tmp;
        printf("[UART] Console order normalized: %s=WLE, %s=WBA\n", *port, *port2);
    }
    consoles_detected = 1;
    return 0;
}

#ifdef _WIN32
typedef SOCKET uart_status_socket_t;
#define UART_STATUS_INVALID_SOCKET INVALID_SOCKET
#define uart_status_close_socket closesocket
#define UART_STATUS_THREAD_ERROR 1
static DWORD WINAPI uart_status_server_thread(LPVOID unused)
#else
typedef int uart_status_socket_t;
#define UART_STATUS_INVALID_SOCKET (-1)
#define uart_status_close_socket close
#define UART_STATUS_THREAD_ERROR NULL
static void *uart_status_server_thread(void *unused)
#endif
{
    static const char *const allowed_origins[] = {
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
    };
    struct sockaddr_in address;
    uart_status_socket_t server_socket;
    (void)unused;

#ifdef _WIN32
    WSADATA winsock_data;
    if (WSAStartup(MAKEWORD(2, 2), &winsock_data) != 0) {
        fprintf(stderr, "[UART][STATUS] WSAStartup failed\n");
        return UART_STATUS_THREAD_ERROR;
    }
#endif

    server_socket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (server_socket == UART_STATUS_INVALID_SOCKET) {
        fprintf(stderr, "[UART][STATUS] Could not create status endpoint socket\n");
        return UART_STATUS_THREAD_ERROR;
    }

    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_port = htons(UART_STATUS_PORT);
    address.sin_addr.s_addr = inet_addr(UART_STATUS_HOST);
    if (bind(server_socket, (struct sockaddr *)&address, sizeof(address)) != 0 ||
        listen(server_socket, 8) != 0) {
        fprintf(stderr, "[UART][STATUS] Could not bind http://%s:%d\n",
                UART_STATUS_HOST, UART_STATUS_PORT);
        uart_status_close_socket(server_socket);
#ifdef _WIN32
        WSACleanup();
        return 1;
#else
        return NULL;
#endif
    }
    printf("[UART][STATUS] Listening on http://%s:%d/api/uart-status\n",
           UART_STATUS_HOST, UART_STATUS_PORT);

    while (keep_running) {
        struct sockaddr_in client_address;
#ifdef _WIN32
        int client_address_size = sizeof(client_address);
#else
        socklen_t client_address_size = sizeof(client_address);
#endif
        uart_status_socket_t client_socket = accept(
            server_socket, (struct sockaddr *)&client_address, &client_address_size);
        char request[1024] = "";
        char response[2048];
        char origin[160] = "";
        const char *cors_origin = "";
        int received;
        int response_length;

        if (client_socket == UART_STATUS_INVALID_SOCKET) continue;
        received = (int)recv(client_socket, request, (int)sizeof(request) - 1, 0);
        if (received > 0) {
            char *origin_header;
            request[received] = '\0';
            origin_header = strstr(request, "Origin: ");
            if (origin_header != NULL) {
                origin_header += strlen("Origin: ");
                sscanf(origin_header, "%159[^\r\n]", origin);
            }
            for (size_t i = 0; i < sizeof(allowed_origins) / sizeof(allowed_origins[0]); ++i) {
                if (strcmp(origin, allowed_origins[i]) == 0) {
                    cors_origin = origin;
                    break;
                }
            }

            if (strncmp(request, "OPTIONS ", 8) == 0) {
                response_length = snprintf(response, sizeof(response),
                    "HTTP/1.1 204 No Content\r\n"
                    "Access-Control-Allow-Origin: %s\r\n"
                    "Access-Control-Allow-Methods: GET, OPTIONS\r\n"
                    "Access-Control-Allow-Headers: Content-Type\r\n"
                    "Vary: Origin\r\nConnection: close\r\nContent-Length: 0\r\n\r\n",
                    cors_origin);
            } else if (strncmp(request, "GET /api/uart-status ", 21) == 0 ||
                       strncmp(request, "GET /health ", 12) == 0) {
                int detected = dual_uart_mode && consoles_detected;
                char body[768];
                snprintf(body, sizeof(body),
                    "{\"status\":\"%s\",\"port_wle\":\"%s\",\"port_wba\":\"%s\"}",
                    detected ? "success" : "failed",
                    detected ? active_port_wle : "",
                    detected ? active_port_wba : "");
                response_length = snprintf(response, sizeof(response),
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    "Cache-Control: no-store\r\nAccess-Control-Allow-Origin: %s\r\n"
                    "Vary: Origin\r\nConnection: close\r\nContent-Length: %lu\r\n\r\n%s",
                    cors_origin, (unsigned long)strlen(body), body);
            } else {
                static const char not_found[] = "{\"error\":\"not found\"}";
                response_length = snprintf(response, sizeof(response),
                    "HTTP/1.1 404 Not Found\r\nContent-Type: application/json\r\n"
                    "Connection: close\r\nContent-Length: %lu\r\n\r\n%s",
                    (unsigned long)(sizeof(not_found) - 1), not_found);
            }
            if (response_length > 0) (void)send(client_socket, response, response_length, 0);
        }
        uart_status_close_socket(client_socket);
    }
    uart_status_close_socket(server_socket);
#ifdef _WIN32
    WSACleanup();
    return 0;
#else
    return NULL;
#endif
}

static int start_uart_status_server(void) {
#ifdef _WIN32
    HANDLE thread = CreateThread(NULL, 0, uart_status_server_thread, NULL, 0, NULL);
    if (thread == NULL) return -1;
    CloseHandle(thread);
#else
    pthread_t thread;
    if (pthread_create(&thread, NULL, uart_status_server_thread, NULL) != 0) return -1;
    pthread_detach(thread);
#endif
    return 0;
}

static void handle_detect_command(const char *request_id) {
    const char *detected_port_wle = active_port_wle;
    const char *detected_port_wba = active_port_wba;
    char payload[768];
    int result = -1;

    printf("\n[UART] Detecting MCU types on startup UARTs %s and %s...\n",
           active_port_wle, active_port_wba);
    if (dual_uart_mode && uart_fd != PLATFORM_UART_INVALID &&
        uart_fd2 != PLATFORM_UART_INVALID) {
        result = detect_console_layout(&detected_port_wle, &detected_port_wba);
        if (result == 0) {
            snprintf(active_port_wle, sizeof(active_port_wle), "%s", detected_port_wle);
            snprintf(active_port_wba, sizeof(active_port_wba), "%s", detected_port_wba);
        }
    } else {
        fprintf(stderr, "[UART][ERROR] Start sensor_watcher with both --port and --port2 before detection\n");
    }
    snprintf(payload, sizeof(payload),
             "{\"request_id\":\"%s\",\"status\":\"%s\",\"port_wle\":\"%s\",\"port_wba\":\"%s\"}",
             request_id, result == 0 ? "success" : "failed",
             result == 0 ? active_port_wle : "", result == 0 ? active_port_wba : "");
    if (post_json(api_uart_detection_result_url, payload) != 0) {
        fprintf(stderr, "[UART][ERROR] Failed to report UART detection result\n");
    }
    if (result == 0) {
         printf("[UART] Detection successful: WLE=%s, WBA=%s\n\n",
             active_port_wle, active_port_wba);
    } else {
        printf("[UART] Detection failed; testing remains disabled\n\n");
    }
}

static const char *pass_or_fail(double pass_ratio) {
    double r = (double)rand() / (double)RAND_MAX;
    return r < pass_ratio ? "pass" : "fail";
}


static void now_iso(char *buf, size_t len) {
    time_t t = time(NULL);
    struct tm tm;
    platform_utc_time(t, &tm);
    strftime(buf, len, "%Y-%m-%dT%H:%M:%SZ", &tm);
}

int post_json(const char *url, const char *json_payload) {
    char error[256] = "unknown error";
    if (platform_http_post_json(url, json_payload, 5, error, sizeof(error)) != 0) {
        fprintf(stderr, "POST failed: %s\n  payload: %s\n", error, json_payload);
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

    post_json(api_events_url, json);
}

// detail 的 key 必須對應前端 SensorIQC.js 的 testData 欄位才會顯示數值
void run_test_stage(const char *stage, const char *serial) {
    char detail[160] = "";
    const int uart_available = (uart_fd != PLATFORM_UART_INVALID);

    printf("[TEST] %-16s ... ", stage);
    fflush(stdout);

    if (simulate_mode) {
        printf("[SIMULATE] ");
        // 模擬模式：自動測項先發送 testing 狀態讓前端顯示進行中動畫
        if (strcmp(stage, "testGreenLEDOff") != 0 &&
            strcmp(stage, "testOrangeLEDOff") != 0 &&
            strcmp(stage, "testGreenLED") != 0 &&
            strcmp(stage, "testOrangeLED") != 0 &&
            strcmp(stage, "testBuzzer") != 0) {
            send_event(serial, stage, "testing", NULL);
            platform_sleep_ms(800); // 模擬執行時間 (800ms)
        }
    } else {
        if (strcmp(stage, "testBuzzer") != 0 &&
            strcmp(stage, "testGreenLED") != 0 &&
            strcmp(stage, "testOrangeLED") != 0 &&
            strcmp(stage, "testGreenLEDOff") != 0 &&
            strcmp(stage, "testOrangeLEDOff") != 0) {
            send_event(serial, stage, "testing", NULL);
        }
        if (!uart_available) {
            fprintf(stderr, "[WARN] UART unavailable for stage '%s'\n", stage);
        }
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
            platform_sleep_ms(300);
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
            platform_sleep_ms(300);
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
        if (strcmp(stage, "testBuzzer") == 0) {
            if (!simulate_mode) {
                if (!uart_available) {
                    send_event(serial, stage, "fail",
                               "\"test\":\"testBuzzer\",\"executed\":false");
                    printf("fail  {\"test\":\"testBuzzer\",\"executed\":false}\n");
                    return;
                }

                int result = -1;
                for (int attempt = 1; attempt <= 3 && result != 0; attempt++) {
                    result = uart_hvf_test_buzzer(uart_fd, 3000);
                    if (result != 0 && attempt < 3) {
                        printf("[BUZZER] command failed => retry %d/3\n", attempt + 1);
                        platform_sleep_ms(150);
                    }
                }
                if (result != 0) {
                    send_event(serial, stage, "fail",
                               "\"test\":\"testBuzzer\",\"executed\":false");
                    printf("fail  {\"test\":\"testBuzzer\",\"executed\":false}\n");
                    return;
                }
            }

            send_event(serial, stage, "testing", "\"awaiting_user_confirmation\":true");
            printf("testing  {\"test\":\"testBuzzer\",\"awaiting_user_confirmation\":true}\n");
            return;
        }

        if (simulate_mode) {
            const char *status = pass_or_fail(PASS_RATIO);
            snprintf(detail, sizeof(detail), "\"test\":\"%s\",\"executed\":true", stage);
            send_event(serial, stage, status, detail);
            printf("%s  {%s}\n", status, detail);
            platform_sleep_ms(300);
            return;
        }
        if (!uart_available) {
            snprintf(detail, sizeof(detail), "\"test\":\"%s\",\"executed\":false", stage);
            send_event(serial, stage, "fail", detail);
            printf("fail  {%s}\n", detail);
            return;
        }

        int result = uart_hvf_test_spi(uart_fd);
        const char *status = result == 0 ? "pass" : "fail";
        snprintf(detail, sizeof(detail), "\"test\":\"%s\",\"executed\":true", stage);
        send_event(serial, stage, status, detail);
        printf("%s  {%s}\n", status, detail);
        return;
    }

    if (strcmp(stage, "testOrangeLED") == 0 || strcmp(stage, "testGreenLED") == 0) {
        int led_index = strcmp(stage, "testOrangeLED") == 0 ? 1 : 2;
        if (simulate_mode) {
            send_event(serial, stage, "testing", "\"awaiting_user_confirmation\":true");
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

        int result = -1;
        for (int attempt = 1; attempt <= 3 && result != 0; attempt++) {
            result = uart_hvf_test_led(uart_fd, led_index);
            if (result != 0 && attempt < 3) {
                printf("[LED] %s index=%d => retry %d/3\n",
                       stage, led_index, attempt + 1);
                platform_sleep_ms(150);
            }
        }
        if (result == 0) {
            send_event(serial, stage, "testing", "\"awaiting_user_confirmation\":true");
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
        int led_index = strcmp(stage, "testOrangeLEDOff") == 0 ? 1 : 2;
        if (simulate_mode) {
            printf("[LED] %s index=%d => simulated ok\n",
                   stage, led_index);
            snprintf(detail, sizeof(detail),
                     "\"led_index\":%d,\"executed\":true", led_index);
            send_event(serial, stage, "pass", detail);
            return;
        }
        if (!uart_available) {
            printf("[LED] %s => skipped (UART unavailable)\n", stage);
            snprintf(detail, sizeof(detail),
                     "\"led_index\":%d,\"executed\":false", led_index);
            send_event(serial, stage, "fail", detail);
            return;
        }

        int result = -1;
        for (int attempt = 1; attempt <= 3 && result != 0; attempt++) {
            result = uart_hvf_set_led(uart_fd, led_index, 0);
            if (result != 0 && attempt < 3) {
                printf("[LED] %s index=%d => retry %d/3\n",
                       stage, led_index, attempt + 1);
                platform_sleep_ms(150);
            }
        }
        printf("[LED] %s index=%d => %s\n",
               stage, led_index, result == 0 ? "ok" : "fail");
        snprintf(detail, sizeof(detail),
                 "\"led_index\":%d,\"executed\":%s",
                 led_index, result == 0 ? "true" : "false");
        send_event(serial, stage, result == 0 ? "pass" : "fail", detail);
        return;
    }

    if (strcmp(stage, "testButton") == 0) {
        if (simulate_mode) {
            const char *status = pass_or_fail(PASS_RATIO);
            snprintf(detail, sizeof(detail), "\"press_count\":%d,\"window_s\":%d",
                     strcmp(status, "pass") == 0 ? 1 : 0, 5);
            send_event(serial, stage, status, detail);
            printf("%s  {%s}\n", status, detail);
            platform_sleep_ms(300);
            return;
        }
        if (!uart_available) {
            snprintf(detail, sizeof(detail), "\"press_count\":0,\"window_s\":0");
            send_event(serial, stage, "fail", detail);
            printf("fail  {%s}\n", detail);
            return;
        }

        int wait_seconds = 5;
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
        if (!consoles_detected) {
            printf("\n[SEARCH] MCU consoles were not identified at startup; cannot safely read serials\n\n");
            return;
        }
        if (uart_fd == PLATFORM_UART_INVALID) {
            printf("\n[SEARCH] UART unavailable; cannot read serials\n\n");
            return;
        }

        printf("\n[SEARCH] Flushing UART input...\n");
        // 換板子時裝置會吐一段開機訊息，先清乾淨再下指令
        uart_hvf_flush_input(uart_fd, BOARD_SWAP_IDLE_MS);
        if (dual_uart_mode && uart_fd2 != PLATFORM_UART_INVALID) {
            uart_hvf_flush_input(uart_fd2, BOARD_SWAP_IDLE_MS);
        }
        printf("[SEARCH] Reading serials from device...\n");

        if (uart_hvf_read_stm32_id(uart_fd, 0, serial_wle, sizeof(serial_wle)) != 0) {
            printf("[SEARCH] Failed to read WLE serial\n\n");
            return;
        }
        printf("[SEARCH] WLE = %s\n", serial_wle);

        platform_uart_t wba_uart = dual_uart_mode ? uart_fd2 : uart_fd;
        int wba_passthrough = dual_uart_mode ? 0 : 1;
        if (wba_uart == PLATFORM_UART_INVALID ||
            uart_hvf_read_stm32_id(wba_uart, wba_passthrough, serial_wba, sizeof(serial_wba)) != 0) {
            printf("[SEARCH] Failed to read WBA serial\n\n");
            return;
        }
        printf("[SEARCH] WBA = %s\n", serial_wba);
    }

    snprintf(last_serial_wba, sizeof(last_serial_wba), "%s", serial_wba);

    snprintf(payload, sizeof(payload),
             "{\"serial_wle\":\"%s\",\"serial_wba\":\"%s\"}",
             serial_wle, serial_wba);

    if (post_json(api_serial_found_url, payload) == 0) {
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
    // 只有四個 Sensor 單項測試依賴探測結果。LED、Buzzer、Button 與 SPI
    // 都可在讀取序號後直接執行，不應暗中插入 getSensorIC。
    const int needs_probe = stage_requires_sensor_probe(stage);
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

    // LED Off 是原 LED 人工判定流程中的控制命令，不是獨立測項。
    // run_test_stage 已回傳 pass/fail acknowledgement，無須再送 testComplete。
    if (strcmp(stage, "testGreenLEDOff") == 0 ||
        strcmp(stage, "testOrangeLEDOff") == 0) {
        return;
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
    char clean_line[1024];
    char serial[128];
    char stage[64];
    char request_id[40];

    strncpy(clean_line, line, sizeof(clean_line) - 1);
    clean_line[sizeof(clean_line) - 1] = '\0';
    clean_line[strcspn(clean_line, "\r\n")] = 0;

    if (strlen(clean_line) == 0) {
        return;
    }

    if (sscanf(clean_line, "DETECT %39s", request_id) == 1) {
        handle_detect_command(request_id);
        return;
    }

    if (sscanf(clean_line, "STAGE %63s %127s", stage, serial) == 2) {
        if (!simulate_mode && !consoles_detected) {
            fprintf(stderr, "[UART][ERROR] Refusing test: WLE/WBA UART detection has not succeeded\n");
            return;
        }
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
        if (!simulate_mode && !consoles_detected) {
            fprintf(stderr, "[UART][ERROR] Refusing test: WLE/WBA UART detection has not succeeded\n");
            return;
        }
        handle_test_command(serial);
    } else if (strncmp(clean_line, "SEARCH", 6) == 0) {
        handle_search_command();
    } else {
        printf("[WARN] Unrecognized command: %s\n", clean_line);
    }
}

static void print_usage(const char *prog) {
    fprintf(stderr, "usage: %s [--port PORT|auto] [--port2 PORT] [--list-ports] [--command-file PATH] "
                    "[--lock-file PATH] [--api-base-url URL] [--debug] [--simulate]\n", prog);
    fprintf(stderr, "  --port   serial port (default: %s); auto requires exactly one candidate\n",
            UART_HVF_DEFAULT_PORT);
    fprintf(stderr, "  --port2  optional second MCU UART; with --port, SEARCH reads WLE/WBA directly\n");
    fprintf(stderr, "  --list-ports  list detected serial ports and exit\n");
    fprintf(stderr, "  --simulate  run without UART hardware and generate passing test data\n");
}

static int print_uart_ports(char ports[][128], int max_ports) {
    int count = platform_list_uart_ports(ports, max_ports);
    printf("Detected serial ports (%d):\n", count);
    for (int i = 0; i < count; i++) printf("  %s\n", ports[i]);
    return count;
}

int main(int argc, char **argv) {
    const char *port = UART_HVF_DEFAULT_PORT;
    const char *port2 = NULL;
    char detected_ports[64][128];
    int list_ports = 0;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
            port = argv[++i];
        } else if (strcmp(argv[i], "--port2") == 0 && i + 1 < argc) {
            port2 = argv[++i];
            dual_uart_mode = 1;
        } else if (strcmp(argv[i], "--list-ports") == 0) {
            list_ports = 1;
        } else if (strcmp(argv[i], "--command-file") == 0 && i + 1 < argc) {
            command_file = argv[++i];
        } else if (strcmp(argv[i], "--lock-file") == 0 && i + 1 < argc) {
            lock_file = argv[++i];
        } else if (strcmp(argv[i], "--api-base-url") == 0 && i + 1 < argc) {
            const char *base = argv[++i];
            snprintf(api_events_url, sizeof(api_events_url), "%s/api/sensor/events", base);
            snprintf(api_serial_found_url, sizeof(api_serial_found_url),
                     "%s/api/sensor/serial-found", base);
            snprintf(api_uart_detection_result_url, sizeof(api_uart_detection_result_url),
                     "%s/api/sensor/detect-uart/result", base);
        } else if (strcmp(argv[i], "--debug") == 0 || strcmp(argv[i], "-d") == 0) {
            uart_hvf_set_debug(1);
        } else if (strcmp(argv[i], "--simulate") == 0) {
            simulate_mode = 1;
        } else {
            print_usage(argv[0]);
            return 2;
        }
    }

    if (list_ports) {
        print_uart_ports(detected_ports, 64);
        return 0;
    }
    if (!simulate_mode && strcmp(port, "auto") == 0) {
        int count = print_uart_ports(detected_ports, 64);
        if (count != 1) {
            fprintf(stderr, "[ERROR] Auto selection requires exactly one serial port; "
                            "use --port PORT to select one.\n");
            return 2;
        }
        port = detected_ports[0];
    }
    if (!simulate_mode && dual_uart_mode && strcmp(port2, "auto") == 0) {
        fprintf(stderr, "[ERROR] --port2 must name the second MCU UART explicitly.\n");
        return 2;
    }

    srand((unsigned int)time(NULL));

    if (platform_lock_acquire(&watcher_lock, lock_file) != 0) {
        fprintf(stderr, "[ERROR] Another sensor_watcher is already running\n");
        return 1;
    }

    setvbuf(stdout, NULL, _IOLBF, 0);  // 輸出導向檔案時仍即時可見

    platform_file_stamp_t st_old = {0}, st_new = {0};
    char line[1024];

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    if (!simulate_mode) {
        snprintf(active_port_wle, sizeof(active_port_wle), "%s", port);
        snprintf(active_port_wba, sizeof(active_port_wba), "%s", port2 ? port2 : "");
        uart_fd = uart_hvf_open(port);
        if (uart_fd == PLATFORM_UART_INVALID) {
            fprintf(stderr, "[WARN] Failed to open serial port: %s\n", port);
        }
        if (dual_uart_mode) {
            uart_fd2 = uart_hvf_open(port2);
            if (uart_fd2 == PLATFORM_UART_INVALID) {
                fprintf(stderr, "[WARN] Failed to open second MCU serial port: %s\n", port2);
            }
        }
        if (uart_fd != PLATFORM_UART_INVALID &&
            (!dual_uart_mode || uart_fd2 != PLATFORM_UART_INVALID)) {
            detect_console_layout(&port, &port2);
            snprintf(active_port_wle, sizeof(active_port_wle), "%s", port);
            snprintf(active_port_wba, sizeof(active_port_wba), "%s", port2 ? port2 : "");
        }
    }

    platform_http_init();
    if (start_uart_status_server() != 0) {
        fprintf(stderr, "[UART][STATUS] Failed to start local UART status endpoint\n");
    }

    printf("========================================\n");
    printf("Sensor IQC 監看程式\n");
    printf("========================================\n");
    printf("Mode       : %s\n", simulate_mode ? "SIMULATE (no hardware)" : "HARDWARE");
    printf("Serial port: %s\n", simulate_mode ? "disabled" : port);
    if (dual_uart_mode) {
        printf("Serial port 2: %s\n", simulate_mode ? "disabled" : port2);
        printf("ID mode    : direct WLE/WBA consoles\n");
    } else {
        printf("ID mode    : WLE console + IPC passthrough for WBA\n");
    }
    printf("監看檔案: %s\n", command_file);
    printf("事件 API : %s\n", api_events_url);
    printf("等待指令 (SEARCH / TEST <SERIAL>)... Ctrl-C 結束\n\n");

    platform_file_stamp(command_file, &st_old);

    while (keep_running) {
        platform_sleep_ms(CHECK_INTERVAL * 1000U);

        if (!keep_running) {
            break;
        }

        if (platform_file_stamp(command_file, &st_new) != 0) {
            continue;
        }

        // UI 可能在同一秒內連續寫入 LED Off 與下一個測項，
        // 只比較秒會漏掉後一筆，因此必須連奈秒一起比較。
        if (platform_file_stamp_equal(&st_new, &st_old)) {
            continue;
        }

        FILE *f = fopen(command_file, "r");
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
        f = fopen(command_file, "w");
        if (f) {
            fclose(f);
        }
        platform_file_stamp(command_file, &st_old);

        if (strlen(line) > 0) {
            process_command(line);
        }
    }

    printf("\nShutting down...\n");
    uart_hvf_close(uart_fd2);
    uart_hvf_close(uart_fd);
    platform_lock_release(&watcher_lock);
    platform_http_cleanup();
    return 0;
}
