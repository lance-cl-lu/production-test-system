#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/time.h>
#include <termios.h>
#include <unistd.h>

#define SERIAL_BAUD B115200
#define IDLE_MS 200
#define WAIT_MS 100

typedef enum {
    TEST_HVF_VERSION,
    TEST_HVF_VERSION_PASSTHROUGH,
    TEST_STM32_ID_INFO,
    TEST_STM32_ID_INFO_PASSTHROUGH,
    TEST_GPIO_BUTTON_PASSTHROUGH,
    TEST_LED_ON_PASSTHROUGH,
    TEST_LED_OFF_PASSTHROUGH,
    TEST_BUZZER_ON_PASSTHROUGH,
    TEST_SENSOR_PROBE_ALL,
    TEST_SENSOR_ENS210,
    TEST_SENSOR_LPS22DF,
    TEST_IPC_SPI_ECHO,
    TEST_DRAIN,
    TEST_UNKNOWN
} test_kind_t;

typedef struct {
    test_kind_t kind;
    const char *name;
    int ok;
    int prompt_seen;
    int led_index;
    int button_wait_seconds;
    int button_changed;
    int button_result_marker_seen;
    int sensor_sht41_ok;
    int sensor_ens210_ok;
    int sensor_lps22df_ok;
    int sensor_bme690_ok;
    int sensor_probe_completed;
    int ens210_humidity_ok;
    int ens210_temperature_ok;
    int ens210_humidity_has_value;
    int ens210_temperature_has_value;
    double ens210_humidity;
    double ens210_temperature;
    int lps22df_pressure_ok;
    int lps22df_temperature_ok;
    int lps22df_pressure_has_value;
    int lps22df_temperature_has_value;
    double lps22df_pressure;
    double lps22df_temperature;
    char version[64];
    char mcu[64];
    char unique_stm32mba_device_id[64];
} test_result_t;

static int debug_enabled = 0;

static void debug_print(const char *fmt, ...) {
    if (!debug_enabled) {
        return;
    }

    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
}

static int wait_for_data(int fd, int timeout_ms) {
    fd_set rfds;
    struct timeval tv;
    FD_ZERO(&rfds);
    FD_SET(fd, &rfds);
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;
    return select(fd + 1, &rfds, NULL, NULL, &tv);
}

static int drain_until_idle(int fd, int idle_ms) {
    int idle_wait = 0;
    unsigned char buf[256];

    while (1) {
        int n = wait_for_data(fd, 50);
        if (n <= 0) {
            idle_wait += 50;
            if (idle_wait >= idle_ms) {
                return 0;
            }
            continue;
        }

        ssize_t r = read(fd, buf, sizeof(buf));
        if (r > 0) {
            idle_wait = 0;
        } else if (r < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            idle_wait += 50;
            if (idle_wait >= idle_ms) {
                return 0;
            }
        } else if (r < 0) {
            return -1;
        }
    }
}

static void write_all(int fd, const char *text) {
    size_t len = strlen(text);
    size_t sent = 0;

    while (sent < len) {
        ssize_t w = write(fd, text + sent, len - sent);
        if (w < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                usleep(10000);
                continue;
            }
            return;
        }
        sent += (size_t)w;
    }
}

static int read_to_buffer(int fd, char *buf, size_t buf_size, int timeout_ms) {
    size_t offset = 0;
    unsigned char tmp[256];
    int deadline = timeout_ms;
    const int slice_ms = 50;

    if (buf_size == 0) {
        return 0;
    }

    while (deadline > 0) {
        int wait_ms = deadline < slice_ms ? deadline : slice_ms;
        int n = wait_for_data(fd, wait_ms);
        if (n <= 0) {
            deadline -= wait_ms;
            continue;
        }

        ssize_t r = read(fd, tmp, sizeof(tmp));
        if (r > 0) {
            size_t remain = buf_size - offset;
            size_t chunk = (size_t)r;
            if (chunk > remain - 1) {
                chunk = remain - 1;
            }
            memcpy(buf + offset, tmp, chunk);
            offset += chunk;
            if (offset >= buf_size - 1) {
                break;
            }
        } else if (r < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            continue;
        }
        deadline -= wait_ms;
    }

    buf[offset] = '\0';
    return (int)offset;
}

static int buffer_contains_error(const char *buffer) {
    return (strstr(buffer, "Error:") != NULL) || (strstr(buffer, "ERROR:") != NULL) ||
           (strstr(buffer, "Invalid") != NULL) || (strstr(buffer, "Unknown command") != NULL);
}

static int send_command_collect(int fd, const char *command, char *response, size_t response_size,
                                int timeout_ms) {
    memset(response, 0, response_size);
    write_all(fd, command);
    write_all(fd, "\r\n");
    usleep(WAIT_MS * 1000);
    read_to_buffer(fd, response, response_size, timeout_ms);
    debug_print("[debug] command '%s' response: %s\n", command, response);
    return buffer_contains_error(response) ? -1 : 0;
}

static int send_command_wait_for_result(int fd, const char *command, char *response,
                                        size_t response_size, int timeout_ms) {
    size_t offset = 0;
    int deadline = timeout_ms;
    unsigned char buffer[256];

    if (response_size == 0U) {
        return 0;
    }

    memset(response, 0, response_size);
    write_all(fd, command);
    write_all(fd, "\r\n");

    while (deadline > 0) {
        int wait_ms = deadline < WAIT_MS ? deadline : WAIT_MS;
        int ready = wait_for_data(fd, wait_ms);

        deadline -= wait_ms;
        if (ready <= 0) {
            continue;
        }

        {
            ssize_t received = read(fd, buffer, sizeof(buffer));
            if (received > 0) {
                size_t remaining = response_size - offset;
                size_t chunk = (size_t)received;

                if (chunk > remaining - 1U) {
                    chunk = remaining - 1U;
                }
                memcpy(response + offset, buffer, chunk);
                offset += chunk;
                response[offset] = '\0';

                if (strstr(response, "<[OK]>") != NULL) {
                    debug_print("[debug] command '%s' response: %s\n", command, response);
                    return 1;
                }
                if (strstr(response, "<[ERROR]>") != NULL) {
                    debug_print("[debug] command '%s' response: %s\n", command, response);
                    return -1;
                }
                if (offset >= response_size - 1U) {
                    break;
                }
            } else if (received < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                break;
            }
        }
    }

    debug_print("[debug] command '%s' did not return <[OK]> or <[ERROR]>: %s\n", command,
                response);
    return 0;
}

static int send_command_wait_for_text(int fd, const char *command, const char *expected_text,
                                      char *response, size_t response_size, int timeout_ms) {
    size_t offset = 0;
    int deadline = timeout_ms;
    unsigned char buffer[256];

    if (response_size == 0U) {
        return 0;
    }

    memset(response, 0, response_size);
    write_all(fd, command);
    write_all(fd, "\r\n");

    while (deadline > 0) {
        int wait_ms = deadline < WAIT_MS ? deadline : WAIT_MS;
        int ready = wait_for_data(fd, wait_ms);

        deadline -= wait_ms;
        if (ready <= 0) {
            continue;
        }

        {
            ssize_t received = read(fd, buffer, sizeof(buffer));
            if (received > 0) {
                size_t remaining = response_size - offset;
                size_t chunk = (size_t)received;

                if (chunk > remaining - 1U) {
                    chunk = remaining - 1U;
                }
                memcpy(response + offset, buffer, chunk);
                offset += chunk;
                response[offset] = '\0';

                if (strstr(response, expected_text) != NULL) {
                    debug_print("[debug] command '%s' response: %s\n", command, response);
                    return 1;
                }
                if (buffer_contains_error(response) || offset >= response_size - 1U) {
                    break;
                }
            } else if (received < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                break;
            }
        }
    }

    debug_print("[debug] command '%s' did not return '%s': %s\n", command, expected_text,
                response);
    return 0;
}

static int send_first_command_with_success_hints(int fd, const char *const *commands,
                                                 size_t command_count, char *response,
                                                 size_t response_size, int timeout_ms,
                                                 const char *debug_label,
                                                 const char *success_hint1,
                                                 const char *success_hint2) {
    size_t i;

    for (i = 0; i < command_count; i++) {
        (void)send_command_collect(fd, commands[i], response, response_size, timeout_ms);
        if ((success_hint1 != NULL && strstr(response, success_hint1) != NULL) ||
            (success_hint2 != NULL && strstr(response, success_hint2) != NULL)) {
            debug_print("[debug] %s used command: %s\n", debug_label, commands[i]);
            return 0;
        }
        if (!buffer_contains_error(response)) {
            debug_print("[debug] %s used command: %s\n", debug_label, commands[i]);
            return 0;
        }
    }

    return -1;
}

static void json_escape_into(const char *in, char *out, size_t out_size) {
    size_t i = 0;
    size_t j = 0;

    if (out_size == 0) {
        return;
    }

    memset(out, 0, out_size);
    while (in[i] != '\0' && j + 2 < out_size) {
        unsigned char c = (unsigned char)in[i];
        if (c == '"') {
            out[j++] = '\\';
            out[j++] = '"';
        } else if (c == '\\') {
            out[j++] = '\\';
            out[j++] = '\\';
        } else if (c == '\n') {
            out[j++] = '\\';
            out[j++] = 'n';
        } else if (c == '\r') {
            out[j++] = '\\';
            out[j++] = 'r';
        } else if (c == '\t') {
            out[j++] = '\\';
            out[j++] = 't';
        } else if (c < 0x20) {
            snprintf(out + j, out_size - j, "\\u%04x", c);
            j += 6;
        } else {
            out[j++] = (char)c;
        }
        i++;
    }
    out[j] = '\0';
}

static int open_port(const char *port, speed_t baud) {
    int fd = open(port, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) {
        return -1;
    }

    struct termios tty;
    memset(&tty, 0, sizeof(tty));
    if (tcgetattr(fd, &tty) != 0) {
        close(fd);
        return -1;
    }

    cfsetispeed(&tty, baud);
    cfsetospeed(&tty, baud);

    tty.c_cflag = (tty.c_cflag & ~CSIZE) | CS8;
    tty.c_cflag |= (CLOCAL | CREAD);
    tty.c_cflag &= ~(PARENB | PARODD | CSTOPB);
    tty.c_cflag &= ~CRTSCTS;

    tty.c_iflag = 0;
    tty.c_oflag = 0;
    tty.c_lflag = 0;

    tty.c_cc[VMIN] = 0;
    tty.c_cc[VTIME] = 0;

    if (tcsetattr(fd, TCSANOW, &tty) != 0) {
        close(fd);
        return -1;
    }

    tcflush(fd, TCIFLUSH);
    return fd;
}

static test_kind_t parse_test_kind(const char *name) {
    if (strcmp(name, "hvf_version") == 0) {
        return TEST_HVF_VERSION;
    }
    if (strcmp(name, "hvf_version_passthrough") == 0 || strcmp(name, "hvf_version_passtrough") == 0) {
        return TEST_HVF_VERSION_PASSTHROUGH;
    }
    if (strcmp(name, "stm32_id_info") == 0) {
        return TEST_STM32_ID_INFO;
    }
    if (strcmp(name, "stm32_id_info_passthrough") == 0) {
        return TEST_STM32_ID_INFO_PASSTHROUGH;
    }
    if (strcmp(name, "gpio_button_passthrough") == 0 || strcmp(name, "gpio_button_passtrough") == 0) {
        return TEST_GPIO_BUTTON_PASSTHROUGH;
    }
    if (strcmp(name, "led_on_passthrough") == 0) {
        return TEST_LED_ON_PASSTHROUGH;
    }
    if (strcmp(name, "led_off_passthrough") == 0) {
        return TEST_LED_OFF_PASSTHROUGH;
    }
    if (strcmp(name, "buzzer_on_passthrough") == 0 || strcmp(name, "buzzer_on_passtrough") == 0) {
        return TEST_BUZZER_ON_PASSTHROUGH;
    }
    if (strcmp(name, "sensor_probe_all") == 0) {
        return TEST_SENSOR_PROBE_ALL;
    }
    if (strcmp(name, "sensor_ens210") == 0) {
        return TEST_SENSOR_ENS210;
    }
    if (strcmp(name, "sensor_lps22df") == 0) {
        return TEST_SENSOR_LPS22DF;
    }
    if (strcmp(name, "ipc_spi_echo") == 0) {
        return TEST_IPC_SPI_ECHO;
    }
    if (strcmp(name, "drain") == 0) {
        return TEST_DRAIN;
    }
    return TEST_UNKNOWN;
}

static void init_result(test_result_t *result, test_kind_t kind, const char *name) {
    memset(result, 0, sizeof(*result));
    result->kind = kind;
    result->name = name;
}

static void trim_ascii_whitespace(char *text) {
    size_t start = 0;
    size_t end;

    while (text[start] != '\0' && (text[start] == '\r' || text[start] == '\n' || text[start] == ' ' || text[start] == '\t')) {
        start++;
    }
    if (start > 0) {
        memmove(text, text + start, strlen(text + start) + 1);
    }

    end = strlen(text);
    while (end > 0 && (text[end - 1] == '\r' || text[end - 1] == '\n' || text[end - 1] == ' ' || text[end - 1] == '\t')) {
        text[--end] = '\0';
    }
}

static void strip_control_chars(char *text) {
    size_t read_index = 0;
    size_t write_index = 0;

    while (text[read_index] != '\0') {
        unsigned char c = (unsigned char)text[read_index++];
        if (c == '\r' || c == '\n' || c == '\t') {
            continue;
        }
        text[write_index++] = (char)c;
    }
    text[write_index] = '\0';
}

static int extract_numeric_hvf_payload(const char *response, double *value) {
    const char *payload = strstr(response, "{[");
    char *end;
    double parsed_value;

    if (payload == NULL) {
        return 0;
    }

    parsed_value = strtod(payload + 2, &end);
    if ((end == payload + 2) || strncmp(end, "]}", 2) != 0) {
        return 0;
    }

    *value = parsed_value;
    return 1;
}

static void emit_result_json(const test_result_t *result) {
    if (result->kind == TEST_GPIO_BUTTON_PASSTHROUGH) {
        printf("{\"test\":\"%s\",\"ok\":%s,\"prompt_seen\":%s,\"data\":{\"seconds\":%d,\"changed\":%s,\"result_marker_seen\":%s}}\n",
               result->name,
               result->ok ? "true" : "false",
               result->prompt_seen ? "true" : "false",
               result->button_wait_seconds,
               result->button_changed ? "true" : "false",
               result->button_result_marker_seen ? "true" : "false");
        return;
    }

    if (result->kind == TEST_SENSOR_PROBE_ALL) {
        int detected_count = 0;
        int missing_count = 0;
        int first = 1;

        printf("{\"test\":\"%s\",\"ok\":%s,\"prompt_seen\":%s,\"data\":{",
               result->name,
               result->ok ? "true" : "false",
               result->prompt_seen ? "true" : "false");

        printf("\"sht41\":%s,\"ens210\":%s,\"lps22df\":%s,\"bme690\":%s,",
               result->sensor_sht41_ok ? "true" : "false",
               result->sensor_ens210_ok ? "true" : "false",
               result->sensor_lps22df_ok ? "true" : "false",
               result->sensor_bme690_ok ? "true" : "false");

        printf("\"detected_sensors\":[");
        if (result->sensor_sht41_ok) {
            printf("\"sht41\"");
            first = 0;
            detected_count++;
        }
        if (result->sensor_ens210_ok) {
            printf("%s\"ens210\"", first ? "" : ",");
            first = 0;
            detected_count++;
        }
        if (result->sensor_lps22df_ok) {
            printf("%s\"lps22df\"", first ? "" : ",");
            first = 0;
            detected_count++;
        }
        if (result->sensor_bme690_ok) {
            printf("%s\"bme690\"", first ? "" : ",");
            detected_count++;
        }
        printf("],");

        first = 1;
        printf("\"missing_sensors\":[");
        if (!result->sensor_sht41_ok) {
            printf("\"sht41\"");
            first = 0;
            missing_count++;
        }
        if (!result->sensor_ens210_ok) {
            printf("%s\"ens210\"", first ? "" : ",");
            first = 0;
            missing_count++;
        }
        if (!result->sensor_lps22df_ok) {
            printf("%s\"lps22df\"", first ? "" : ",");
            first = 0;
            missing_count++;
        }
        if (!result->sensor_bme690_ok) {
            printf("%s\"bme690\"", first ? "" : ",");
            missing_count++;
        }
         printf("],\"detected_count\":%d,\"missing_count\":%d,\"probe_completed\":%s}}\n",
             detected_count,
             missing_count,
             result->sensor_probe_completed ? "true" : "false");
        return;
    }

    if (result->kind == TEST_SENSOR_ENS210) {
        printf("{\"test\":\"%s\",\"ok\":%s,\"prompt_seen\":%s,\"data\":{\"humidity\":",
               result->name,
               result->ok ? "true" : "false",
               result->prompt_seen ? "true" : "false");
        if (result->ens210_humidity_has_value) {
            printf("%.2f", result->ens210_humidity);
        } else {
            printf("null");
        }
        printf(",\"temperature\":");
        if (result->ens210_temperature_has_value) {
            printf("%.2f", result->ens210_temperature);
        } else {
            printf("null");
        }
        printf(",\"temperature_unit\":\"C\"}}\n");
        return;
    }

    if (result->kind == TEST_SENSOR_LPS22DF) {
        printf("{\"test\":\"%s\",\"ok\":%s,\"prompt_seen\":%s,\"data\":{\"pressure\":",
               result->name,
               result->ok ? "true" : "false",
               result->prompt_seen ? "true" : "false");
        if (result->lps22df_pressure_has_value) {
            printf("%.2f", result->lps22df_pressure);
        } else {
            printf("null");
        }
        printf(",\"pressure_unit\":\"h\",\"temperature\":");
        if (result->lps22df_temperature_has_value) {
            printf("%.2f", result->lps22df_temperature);
        } else {
            printf("null");
        }
        printf(",\"temperature_unit\":\"C\"}}\n");
        return;
    }

    if (result->kind == TEST_LED_ON_PASSTHROUGH) {
        printf("{\"test\":\"%s\",\"ok\":%s,\"prompt_seen\":%s,\"data\":{\"led\":%d,\"action\":\"on\"}}\n",
               result->name,
               result->ok ? "true" : "false",
               result->prompt_seen ? "true" : "false",
               result->led_index);
        return;
    }

    if (result->kind == TEST_LED_OFF_PASSTHROUGH) {
        printf("{\"test\":\"%s\",\"ok\":%s,\"prompt_seen\":%s,\"data\":{\"led\":%d,\"action\":\"off\"}}\n",
               result->name,
               result->ok ? "true" : "false",
               result->prompt_seen ? "true" : "false",
               result->led_index);
        return;
    }

    if (result->kind == TEST_BUZZER_ON_PASSTHROUGH) {
        printf("{\"test\":\"%s\",\"ok\":%s,\"prompt_seen\":%s,\"data\":{\"duration_ms\":%d,\"action\":\"on\"}}\n",
               result->name,
               result->ok ? "true" : "false",
               result->prompt_seen ? "true" : "false",
               result->button_wait_seconds);
        return;
    }

    if (result->kind == TEST_IPC_SPI_ECHO) {
        printf("{\"test\":\"%s\",\"ok\":%s,\"prompt_seen\":%s,\"data\":{}}\n",
               result->name,
               result->ok ? "true" : "false",
               result->prompt_seen ? "true" : "false");
        return;
    }

    if ((result->kind == TEST_STM32_ID_INFO) || (result->kind == TEST_STM32_ID_INFO_PASSTHROUGH)) {
     char unique_stm32mba_device_id_json[128];
     json_escape_into(result->unique_stm32mba_device_id, unique_stm32mba_device_id_json, sizeof(unique_stm32mba_device_id_json));

     printf("{\"test\":\"%s\",\"ok\":%s,\"prompt_seen\":%s,\"data\":{\"unique_stm32mba_device_id\":\"%s\"}}\n",
         result->name,
         result->ok ? "true" : "false",
         result->prompt_seen ? "true" : "false",
         unique_stm32mba_device_id_json);
        return;
    }

    char version_json[128];
    char mcu_json[128];
    json_escape_into(result->version, version_json, sizeof(version_json));
    json_escape_into(result->mcu, mcu_json, sizeof(mcu_json));

    printf("{\"test\":\"%s\",\"ok\":%s,\"prompt_seen\":%s,\"data\":{\"version\":\"%s\",\"mcu\":\"%s\"}}\n",
        result->name,
        result->ok ? "true" : "false",
        result->prompt_seen ? "true" : "false",
        version_json,
        mcu_json);
}

static void run_test_drain(int fd, test_result_t *result) {
    init_result(result, TEST_DRAIN, "drain");
    result->ok = (drain_until_idle(fd, IDLE_MS) == 0);
}

static void run_test_hvf_version(int fd, test_result_t *result) {
    char after_enter[256];
    char response[1024];

    init_result(result, TEST_HVF_VERSION, "hvf_version");
    result->ok = 0;
    result->prompt_seen = 0;

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return;
    }

    write_all(fd, "\r");
    usleep(WAIT_MS * 1000);

    memset(after_enter, 0, sizeof(after_enter));
    read_to_buffer(fd, after_enter, sizeof(after_enter), 200);
    debug_print("[debug] after Enter bytes: %s\n", after_enter);
    if (strstr(after_enter, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    write_all(fd, "hvf_version\r\n");
    debug_print("[debug] sent hvf_version\n");
    usleep(WAIT_MS * 1000);

    memset(response, 0, sizeof(response));
    read_to_buffer(fd, response, sizeof(response), 1500);
    debug_print("[debug] raw response: %s\n", response);

    if (strstr(response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    char *payload_start = strstr(response, "{[");
    if (payload_start != NULL) {
        payload_start += 2;
        char *payload_end = strstr(payload_start, "]}");
        if (payload_end != NULL) {
            size_t payload_len = (size_t)(payload_end - payload_start);
            char payload[256];
            if (payload_len >= sizeof(payload)) {
                payload_len = sizeof(payload) - 1;
            }
            memcpy(payload, payload_start, payload_len);
            payload[payload_len] = '\0';

            char *dash = strchr(payload, '-');
            if (dash != NULL) {
                *dash = '\0';
                snprintf(result->version, sizeof(result->version), "%s", payload);
                snprintf(result->mcu, sizeof(result->mcu), "%s", dash + 1);
            } else {
                snprintf(result->version, sizeof(result->version), "%s", payload);
            }

            trim_ascii_whitespace(result->version);
            trim_ascii_whitespace(result->mcu);
            strip_control_chars(result->version);
            strip_control_chars(result->mcu);
        }
    }

    if (strstr(response, "<[OK]>") != NULL) {
        result->ok = 1;
    }
}

static void run_test_stm32_id_info(int fd, test_result_t *result) {
    char after_enter[256];
    char response[1024];

    init_result(result, TEST_STM32_ID_INFO, "stm32_id_info");
    result->ok = 0;
    result->prompt_seen = 0;

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return;
    }

    write_all(fd, "\r");
    usleep(WAIT_MS * 1000);

    memset(after_enter, 0, sizeof(after_enter));
    read_to_buffer(fd, after_enter, sizeof(after_enter), 200);
    debug_print("[debug] after Enter bytes: %s\n", after_enter);
    if (strstr(after_enter, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    write_all(fd, "stm32_id_info\r\n");
    debug_print("[debug] sent stm32_id_info\n");
    usleep(WAIT_MS * 1000);

    memset(response, 0, sizeof(response));
    read_to_buffer(fd, response, sizeof(response), 1500);
    debug_print("[debug] raw response: %s\n", response);

    if (strstr(response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    char *payload_start = strstr(response, "{[");
    if (payload_start != NULL) {
        payload_start += 2;
        char *payload_end = strstr(payload_start, "]}");
        if (payload_end != NULL) {
            size_t payload_len = (size_t)(payload_end - payload_start);
            char payload[256];
            if (payload_len >= sizeof(payload)) {
                payload_len = sizeof(payload) - 1;
            }
            memcpy(payload, payload_start, payload_len);
            payload[payload_len] = '\0';
            snprintf(result->unique_stm32mba_device_id, sizeof(result->unique_stm32mba_device_id), "%s", payload);
            trim_ascii_whitespace(result->unique_stm32mba_device_id);
            strip_control_chars(result->unique_stm32mba_device_id);
        }
    }

    if (strstr(response, "<[OK]>") != NULL) {
        result->ok = 1;
    }
}

static void run_test_stm32_id_info_passthrough(int fd, test_result_t *result) {
    char passthrough_banner[1024];
    char id_response[1024];
    char exit_response[1024];
    static const char *const passthrough_commands[] = {"ipc_passthrough", "passthrough"};
    static const char *const passthrough_exit_commands[] = {"ipc_passthrough_exit", "passthrough_exit"};

    init_result(result, TEST_STM32_ID_INFO_PASSTHROUGH, "stm32_id_info_passthrough");
    result->ok = 0;
    result->prompt_seen = 0;

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return;
    }

    if (send_first_command_with_success_hints(fd, passthrough_commands,
                                              sizeof(passthrough_commands) / sizeof(passthrough_commands[0]),
                                              passthrough_banner, sizeof(passthrough_banner), 1200,
                                              "passthrough", "Entering HVF passthrough", "Press Ctrl+C") != 0) {
        debug_print("[debug] passthrough failed\n");
        return;
    }

    if (strstr(passthrough_banner, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    usleep((WAIT_MS + 50) * 1000);

    if (send_command_collect(fd, "stm32_id_info", id_response, sizeof(id_response), 1500) != 0) {
        debug_print("[debug] stm32_id_info first try failed, retrying\n");
        usleep((WAIT_MS + 100) * 1000);
        (void)send_command_collect(fd, "stm32_id_info", id_response, sizeof(id_response), 1500);
    }
    debug_print("[debug] passthrough id response: %s\n", id_response);

    if (strstr(id_response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    char *payload_start = strstr(id_response, "{[");
    if (payload_start != NULL) {
        payload_start += 2;
        char *payload_end = strstr(payload_start, "]}");
        if (payload_end != NULL) {
            size_t payload_len = (size_t)(payload_end - payload_start);
            char payload[256];
            if (payload_len >= sizeof(payload)) {
                payload_len = sizeof(payload) - 1;
            }
            memcpy(payload, payload_start, payload_len);
            payload[payload_len] = '\0';
            snprintf(result->unique_stm32mba_device_id, sizeof(result->unique_stm32mba_device_id), "%s", payload);
            trim_ascii_whitespace(result->unique_stm32mba_device_id);
            strip_control_chars(result->unique_stm32mba_device_id);
        }
    }

    (void)send_first_command_with_success_hints(fd, passthrough_exit_commands,
                                                sizeof(passthrough_exit_commands) / sizeof(passthrough_exit_commands[0]),
                                                exit_response, sizeof(exit_response), 2500,
                                                "passthrough exit", "IPC_IRQ pulse sent", "Exited HVF passthrough");

    if (strstr(exit_response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    if ((strlen(result->unique_stm32mba_device_id) > 0U) && (strstr(exit_response, "<[OK]>") != NULL)) {
        result->ok = 1;
    }
}

static void run_test_hvf_version_passthrough(int fd, test_result_t *result) {
    char passthrough_banner[1024];
    char version_response[1024];
    char exit_response[1024];
    static const char *const passthrough_commands[] = {"ipc_passthrough", "passthrough"};
    static const char *const passthrough_exit_commands[] = {"ipc_passthrough_exit", "passthrough_exit"};

    init_result(result, TEST_HVF_VERSION_PASSTHROUGH, "hvf_version_passthrough");
    result->ok = 0;
    result->prompt_seen = 0;

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return;
    }

    if (send_first_command_with_success_hints(fd, passthrough_commands,
                                              sizeof(passthrough_commands) / sizeof(passthrough_commands[0]),
                                              passthrough_banner, sizeof(passthrough_banner), 1200,
                                              "passthrough", "Entering HVF passthrough", "Press Ctrl+C") != 0) {
        debug_print("[debug] passthrough failed\n");
        return;
    }

    if (strstr(passthrough_banner, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    usleep((WAIT_MS + 50) * 1000);

    if (send_command_collect(fd, "hvf_version", version_response, sizeof(version_response), 1500) != 0) {
        debug_print("[debug] hvf_version first try failed, retrying\n");
        usleep((WAIT_MS + 100) * 1000);
        (void)send_command_collect(fd, "hvf_version", version_response, sizeof(version_response), 1500);
    }
    debug_print("[debug] passthrough hvf_version response: %s\n", version_response);

    if (strstr(version_response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    {
        char *payload_start = strstr(version_response, "{[");
        if (payload_start != NULL) {
            payload_start += 2;
            char *payload_end = strstr(payload_start, "]}");
            if (payload_end != NULL) {
                size_t payload_len = (size_t)(payload_end - payload_start);
                char payload[256];
                if (payload_len >= sizeof(payload)) {
                    payload_len = sizeof(payload) - 1;
                }
                memcpy(payload, payload_start, payload_len);
                payload[payload_len] = '\0';

                char *dash = strchr(payload, '-');
                if (dash != NULL) {
                    *dash = '\0';
                    snprintf(result->version, sizeof(result->version), "%s", payload);
                    snprintf(result->mcu, sizeof(result->mcu), "%s", dash + 1);
                } else {
                    snprintf(result->version, sizeof(result->version), "%s", payload);
                }

                trim_ascii_whitespace(result->version);
                trim_ascii_whitespace(result->mcu);
                strip_control_chars(result->version);
                strip_control_chars(result->mcu);
            }
        }
    }

    (void)send_first_command_with_success_hints(fd, passthrough_exit_commands,
                                                sizeof(passthrough_exit_commands) / sizeof(passthrough_exit_commands[0]),
                                                exit_response, sizeof(exit_response), 2500,
                                                "passthrough exit", "IPC_IRQ pulse sent", "Exited HVF passthrough");

    if (strstr(exit_response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    if ((strlen(result->version) > 0U) && (strstr(version_response, "<[OK]>") != NULL) &&
        (strstr(exit_response, "<[OK]>") != NULL)) {
        result->ok = 1;
    }
}

static void run_test_gpio_button_passthrough(int fd, test_result_t *result, int wait_seconds) {
    char passthrough_banner[1024];
    char prompt_sync[512];
    char button_response[1024];
    char exit_response[1024];
    char button_command[64];
    char button_command_alt[64];
    int command_attempt;
    static const char *const passthrough_commands[] = {"ipc_passthrough", "passthrough"};
    static const char *const passthrough_exit_commands[] = {"ipc_passthrough_exit", "passthrough_exit"};

    init_result(result, TEST_GPIO_BUTTON_PASSTHROUGH, "gpio_button_passthrough");
    result->ok = 0;
    result->prompt_seen = 0;
    result->button_wait_seconds = wait_seconds;

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return;
    }

    if (send_first_command_with_success_hints(fd, passthrough_commands,
                                              sizeof(passthrough_commands) / sizeof(passthrough_commands[0]),
                                              passthrough_banner, sizeof(passthrough_banner), 1200,
                                              "passthrough", "Entering HVF passthrough", "Press Ctrl+C") != 0) {
        debug_print("[debug] passthrough failed\n");
        return;
    }

    if (strstr(passthrough_banner, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    usleep((WAIT_MS + 120) * 1000);

    snprintf(button_command, sizeof(button_command), "gpio_button %d", wait_seconds);
    snprintf(button_command_alt, sizeof(button_command_alt), "button %d", wait_seconds);
    for (command_attempt = 0; command_attempt < 3; ++command_attempt) {
        /* Sync at prompt before sending long-running button command. */
        memset(prompt_sync, 0, sizeof(prompt_sync));
        write_all(fd, "\r");
        usleep((WAIT_MS + 20) * 1000);
        read_to_buffer(fd, prompt_sync, sizeof(prompt_sync), 300);
        if (strstr(prompt_sync, "hvf>") != NULL) {
            result->prompt_seen = 1;
        }

        (void)send_command_collect(fd, button_command, button_response, sizeof(button_response),
                                   wait_seconds * 1000 + 3200);

        if (strstr(button_response, "hvf>") != NULL) {
            result->prompt_seen = 1;
        }

        if (strstr(button_response, "<[OK]>") != NULL) {
            result->button_result_marker_seen = 1;
            result->button_changed = 1;
            result->ok = 1;
            break;
        }

        if (strstr(button_response, "<[ERROR]>") != NULL) {
            result->button_result_marker_seen = 1;
            result->button_changed = 0;
            break;
        }

        if (strstr(button_response, "Unknown command") != NULL) {
            char alt_response[1024];
            debug_print("[debug] %s unknown, trying alternate command '%s'\n", button_command,
                        button_command_alt);
            (void)send_command_collect(fd, button_command_alt, alt_response, sizeof(alt_response),
                                       wait_seconds * 1000 + 3200);

            if (strstr(alt_response, "hvf>") != NULL) {
                result->prompt_seen = 1;
            }
            if (strstr(alt_response, "<[OK]>") != NULL) {
                result->button_result_marker_seen = 1;
                result->button_changed = 1;
                result->ok = 1;
                break;
            }
            if (strstr(alt_response, "<[ERROR]>") != NULL) {
                result->button_result_marker_seen = 1;
                result->button_changed = 0;
                break;
            }

            result->button_result_marker_seen = 1;
            result->button_changed = 0;
            break;
        }

        debug_print("[debug] %s ambiguous response, retrying\n", button_command);
        usleep((WAIT_MS + 100) * 1000);
    }

    (void)send_first_command_with_success_hints(fd, passthrough_exit_commands,
                                                sizeof(passthrough_exit_commands) / sizeof(passthrough_exit_commands[0]),
                                                exit_response, sizeof(exit_response), 2500,
                                                "passthrough exit", "IPC_IRQ pulse sent", "Exited HVF passthrough");

    if (strstr(exit_response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    if (!result->button_result_marker_seen) {
        debug_print("[debug] gpio_button did not return explicit <[OK]> or <[ERROR]>\n");
    }
}

static void run_test_led_off_passthrough(int fd, test_result_t *result, int led_index) {
    char passthrough_banner[1024];
    char led_response[1024];
    char exit_response[1024];
    char led_cmd[32];
    int led_ok = 0;
    int exit_ok = 0;
    static const char *const passthrough_commands[] = {"ipc_passthrough", "ipc_passtrough", "passthrough"};
    static const char *const passthrough_exit_commands[] = {"ipc_passthrough_exit", "ipc_passtrough_exit", "passthrough_exit"};

    init_result(result, TEST_LED_OFF_PASSTHROUGH, "led_off_passthrough");
    result->ok = 0;
    result->prompt_seen = 0;
    result->led_index = led_index;

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return;
    }

    if (send_first_command_with_success_hints(fd, passthrough_commands,
                                              sizeof(passthrough_commands) / sizeof(passthrough_commands[0]),
                                              passthrough_banner, sizeof(passthrough_banner), 1200,
                                              "passthrough", "Entering HVF passthrough", "Press Ctrl+C") != 0) {
        debug_print("[debug] passthrough failed\n");
        return;
    }

    if (strstr(passthrough_banner, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    usleep((WAIT_MS + 50) * 1000);

    snprintf(led_cmd, sizeof(led_cmd), "led_off %d", led_index);
    if (send_command_collect(fd, led_cmd, led_response, sizeof(led_response), 1200) != 0) {
        debug_print("[debug] %s first try failed, retrying\n", led_cmd);
        usleep((WAIT_MS + 100) * 1000);
        (void)send_command_collect(fd, led_cmd, led_response, sizeof(led_response), 1200);
    }
    debug_print("[debug] led command response: %s\n", led_response);

    if (strstr(led_response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    if (strstr(led_response, "<[OK]>") != NULL) {
        led_ok = 1;
    }

    (void)send_first_command_with_success_hints(fd, passthrough_exit_commands,
                                                sizeof(passthrough_exit_commands) / sizeof(passthrough_exit_commands[0]),
                                                exit_response, sizeof(exit_response), 2500,
                                                "passthrough exit", "IPC_IRQ pulse sent", "Exited HVF passthrough");

    if (strstr(exit_response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    if ((strstr(exit_response, "IPC_IRQ pulse sent") != NULL) ||
        (strstr(exit_response, "Exited HVF passthrough") != NULL) ||
        (strstr(exit_response, "<[OK]>") != NULL)) {
        exit_ok = 1;
    }

    if (!exit_ok) {
        debug_print("[debug] passthrough exit did not return a clear OK marker\n");
    }

    if (led_ok) {
        result->ok = 1;
    }
}

static void run_test_led_on_passthrough(int fd, test_result_t *result, int led_index) {
    char passthrough_banner[1024];
    char led_response[1024];
    char exit_response[1024];
    char led_cmd[32];
    int led_ok = 0;
    int exit_ok = 0;
    static const char *const passthrough_commands[] = {"ipc_passthrough", "ipc_passtrough", "passthrough"};
    static const char *const passthrough_exit_commands[] = {"ipc_passthrough_exit", "ipc_passtrough_exit", "passthrough_exit"};

    init_result(result, TEST_LED_ON_PASSTHROUGH, "led_on_passthrough");
    result->ok = 0;
    result->prompt_seen = 0;
    result->led_index = led_index;

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return;
    }

    if (send_first_command_with_success_hints(fd, passthrough_commands,
                                              sizeof(passthrough_commands) / sizeof(passthrough_commands[0]),
                                              passthrough_banner, sizeof(passthrough_banner), 1200,
                                              "passthrough", "Entering HVF passthrough", "Press Ctrl+C") != 0) {
        debug_print("[debug] passthrough failed\n");
        return;
    }

    if (strstr(passthrough_banner, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    usleep((WAIT_MS + 50) * 1000);

    snprintf(led_cmd, sizeof(led_cmd), "led_on %d", led_index);
    if (send_command_collect(fd, led_cmd, led_response, sizeof(led_response), 1200) != 0) {
        debug_print("[debug] %s first try failed, retrying\n", led_cmd);
        usleep((WAIT_MS + 100) * 1000);
        (void)send_command_collect(fd, led_cmd, led_response, sizeof(led_response), 1200);
    }
    debug_print("[debug] led command response: %s\n", led_response);

    if (strstr(led_response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    if (strstr(led_response, "<[OK]>") != NULL) {
        led_ok = 1;
    }

    (void)send_first_command_with_success_hints(fd, passthrough_exit_commands,
                                                sizeof(passthrough_exit_commands) / sizeof(passthrough_exit_commands[0]),
                                                exit_response, sizeof(exit_response), 2500,
                                                "passthrough exit", "IPC_IRQ pulse sent", "Exited HVF passthrough");

    if (strstr(exit_response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    if ((strstr(exit_response, "IPC_IRQ pulse sent") != NULL) ||
        (strstr(exit_response, "Exited HVF passthrough") != NULL) ||
        (strstr(exit_response, "<[OK]>") != NULL)) {
        exit_ok = 1;
    }

    if (!exit_ok) {
        debug_print("[debug] passthrough exit did not return a clear OK marker\n");
    }

    if (led_ok) {
        result->ok = 1;
    }
}

static void run_test_buzzer_on_passthrough(int fd, test_result_t *result, int duration_ms) {
    char passthrough_banner[1024];
    char buzzer_response[1024];
    char exit_response[1024];
    char buzzer_cmd[32];
    int buzzer_ok = 0;
    int exit_ok = 0;
    int command_timeout_ms;
    static const char *const passthrough_commands[] = {"ipc_passthrough", "ipc_passtrough", "passthrough"};
    static const char *const passthrough_exit_commands[] = {"ipc_passthrough_exit", "ipc_passtrough_exit", "passthrough_exit"};

    init_result(result, TEST_BUZZER_ON_PASSTHROUGH, "buzzer_on_passthrough");
    result->ok = 0;
    result->prompt_seen = 0;
    result->button_wait_seconds = duration_ms;

    command_timeout_ms = duration_ms + 3000;
    if (command_timeout_ms < 4000) {
        command_timeout_ms = 4000;
    }

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return;
    }

    if (send_first_command_with_success_hints(fd, passthrough_commands,
                                              sizeof(passthrough_commands) / sizeof(passthrough_commands[0]),
                                              passthrough_banner, sizeof(passthrough_banner), 1200,
                                              "passthrough", "Entering HVF passthrough", "Press Ctrl+C") != 0) {
        debug_print("[debug] passthrough failed\n");
        return;
    }

    if (strstr(passthrough_banner, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    usleep((WAIT_MS + 50) * 1000);

    snprintf(buzzer_cmd, sizeof(buzzer_cmd), "buzzer_on %d", duration_ms);
    if (send_command_collect(fd, buzzer_cmd, buzzer_response, sizeof(buzzer_response), command_timeout_ms) != 0) {
        debug_print("[debug] %s first try failed, retrying (timeout=%d ms)\n", buzzer_cmd, command_timeout_ms);
        usleep((WAIT_MS + 100) * 1000);
        (void)send_command_collect(fd, buzzer_cmd, buzzer_response, sizeof(buzzer_response), command_timeout_ms);
    }
    debug_print("[debug] buzzer command response: %s\n", buzzer_response);

    if (strstr(buzzer_response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    if (strstr(buzzer_response, "<[OK]>") != NULL) {
        buzzer_ok = 1;
    }

    (void)send_first_command_with_success_hints(fd, passthrough_exit_commands,
                                                sizeof(passthrough_exit_commands) / sizeof(passthrough_exit_commands[0]),
                                                exit_response, sizeof(exit_response), 2500,
                                                "passthrough exit", "IPC_IRQ pulse sent", "Exited HVF passthrough");

    if (strstr(exit_response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    if ((strstr(exit_response, "IPC_IRQ pulse sent") != NULL) ||
        (strstr(exit_response, "Exited HVF passthrough") != NULL) ||
        (strstr(exit_response, "<[OK]>") != NULL)) {
        exit_ok = 1;
    }

    if (!exit_ok) {
        debug_print("[debug] passthrough exit did not return a clear OK marker\n");
    }

    if (buzzer_ok && exit_ok) {
        result->ok = 1;
    }
}

static int sensor_probe_response_is_ok(const char *response) {
    return strstr(response, "<[OK]>") != NULL;
}

static int sensor_probe_response_is_error(const char *response) {
    return (strstr(response, "<[ERROR]>") != NULL) || (strstr(response, "ERROR") != NULL) ||
           (strstr(response, "Unknown command") != NULL) || (strstr(response, "Error:") != NULL);
}

static int run_single_sensor_probe(int fd, const char *sensor_name, int *prompt_seen,
                                   int *has_result_marker) {
    char command[64];
    char response[1024];
    int attempt;

    snprintf(command, sizeof(command), "sensor_probe %s", sensor_name);

    for (attempt = 0; attempt < 2; ++attempt) {
        (void)send_command_collect(fd, command, response, sizeof(response), 1500);
        if (strstr(response, "hvf>") != NULL) {
            *prompt_seen = 1;
        }

        if (sensor_probe_response_is_ok(response)) {
            *has_result_marker = 1;
            return 1;
        }
        if (sensor_probe_response_is_error(response)) {
            *has_result_marker = 1;
            return 0;
        }

        debug_print("[debug] %s ambiguous response, retrying\n", command);
        usleep((WAIT_MS + 80) * 1000);
    }

    return 0;
}

static void run_test_sensor_probe_all(int fd, test_result_t *result) {
    char after_enter[256];
    int marker_count = 0;
    int marker_seen = 0;

    init_result(result, TEST_SENSOR_PROBE_ALL, "sensor_probe_all");
    result->ok = 0;
    result->prompt_seen = 0;

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return;
    }

    write_all(fd, "\r");
    usleep(WAIT_MS * 1000);
    memset(after_enter, 0, sizeof(after_enter));
    read_to_buffer(fd, after_enter, sizeof(after_enter), 300);
    if (strstr(after_enter, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    marker_seen = 0;
    result->sensor_sht41_ok = run_single_sensor_probe(fd, "sht41", &result->prompt_seen, &marker_seen);
    marker_count += marker_seen;

    marker_seen = 0;
    result->sensor_ens210_ok = run_single_sensor_probe(fd, "ens210", &result->prompt_seen, &marker_seen);
    marker_count += marker_seen;

    marker_seen = 0;
    result->sensor_lps22df_ok = run_single_sensor_probe(fd, "lps22df", &result->prompt_seen, &marker_seen);
    marker_count += marker_seen;

    marker_seen = 0;
    result->sensor_bme690_ok = run_single_sensor_probe(fd, "bme690", &result->prompt_seen, &marker_seen);
    marker_count += marker_seen;

    result->sensor_probe_completed = (marker_count == 4);
    result->ok = result->sensor_probe_completed;
}

static void run_test_sensor_ens210(int fd, test_result_t *result) {
    char response[1024];

    init_result(result, TEST_SENSOR_ENS210, "sensor_ens210");
    result->ok = 0;
    result->prompt_seen = 0;

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return;
    }

    result->ens210_temperature_ok =
        (send_command_wait_for_result(fd, "sensor_temperature_get ens210 C", response,
                                      sizeof(response), 1500) == 1);
    if (strstr(response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    if (!result->ens210_temperature_ok) {
        return;
    }
    result->ens210_temperature_has_value =
        extract_numeric_hvf_payload(response, &result->ens210_temperature);

    result->ens210_humidity_ok =
        (send_command_wait_for_result(fd, "sensor_humidity_get ens210", response,
                                      sizeof(response), 1500) == 1);
    if (strstr(response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    if (!result->ens210_humidity_ok) {
        return;
    }
    result->ens210_humidity_has_value = extract_numeric_hvf_payload(response, &result->ens210_humidity);

    result->ok = result->ens210_temperature_has_value && result->ens210_humidity_has_value;
}

static void run_test_sensor_lps22df(int fd, test_result_t *result) {
    char response[1024];

    init_result(result, TEST_SENSOR_LPS22DF, "sensor_lps22df");
    result->ok = 0;
    result->prompt_seen = 0;

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return;
    }

    result->lps22df_pressure_ok =
        (send_command_wait_for_result(fd, "sensor_pressure_get lps22df h", response,
                                      sizeof(response), 1500) == 1);
    if (strstr(response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    if (!result->lps22df_pressure_ok) {
        return;
    }
    result->lps22df_pressure_has_value = extract_numeric_hvf_payload(response, &result->lps22df_pressure);

    result->lps22df_temperature_ok =
        (send_command_wait_for_result(fd, "sensor_temperature_get lps22df C", response,
                                      sizeof(response), 1500) == 1);
    if (strstr(response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }
    if (!result->lps22df_temperature_ok) {
        return;
    }
    result->lps22df_temperature_has_value =
        extract_numeric_hvf_payload(response, &result->lps22df_temperature);

    result->ok = result->lps22df_pressure_has_value && result->lps22df_temperature_has_value;
}

static void run_test_ipc_spi_echo(int fd, test_result_t *result) {
    char response[2048];
    int enter_count;

    init_result(result, TEST_IPC_SPI_ECHO, "ipc_spi_echo");
    result->ok = 0;
    result->prompt_seen = 0;

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return;
    }

    if (send_command_wait_for_text(fd, "ipc_passthrough", "Entering HVF passthrough", response,
                                   sizeof(response), 2000) != 1) {
        return;
    }

    for (enter_count = 0; enter_count < 3; enter_count++) {
        write_all(fd, "\r");
        usleep(WAIT_MS * 1000);
    }
    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] failed to drain after passthrough Enter keys\n");
        return;
    }

    if (send_command_wait_for_result(fd, "ipc_spi_rx_echo_auto", response, sizeof(response),
                                     35000) != 1) {
        return;
    }

    if (strstr(response, "hvf>") != NULL) {
        result->prompt_seen = 1;
    }

    if (send_command_wait_for_result(fd, "ipc_spi_tx_echo", response, sizeof(response), 35000) !=
        1) {
        return;
    }

    result->ok = 1;
}

static void print_usage(const char *prog) {
    fprintf(stderr,
            "usage: %s [--port /dev/ttyX] [--test hvf_version|hvf_version_passthrough|stm32_id_info|stm32_id_info_passthrough|gpio_button_passthrough|led_on_passthrough|led_off_passthrough|buzzer_on_passthrough|sensor_probe_all|sensor_ens210|sensor_lps22df|ipc_spi_echo|drain] [--led 1|2] [--seconds N] [--ms N] [--debug]\n",
            prog);
    fprintf(stderr,
            "note: gpio_button_passthrough requires --seconds N (1..300), e.g. --test gpio_button_passthrough --seconds 3\n");
    fprintf(stderr,
            "note: buzzer_on_passthrough defaults to --ms 3000, e.g. --test buzzer_on_passthrough --ms 3000\n");
}

int main(int argc, char **argv) {
    const char *port = "/dev/tty.usbserial-0001";
    const char *test_name = "hvf_version";
    test_kind_t test_kind = TEST_HVF_VERSION;
    int led_index = 1;
    int wait_seconds = 3;
    int buzzer_duration_ms = 3000;
    int seconds_explicitly_set = 0;

    if (argc == 1) {
        print_usage(argv[0]);
        return 0;
    }

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--debug") == 0 || strcmp(argv[i], "-d") == 0) {
            debug_enabled = 1;
        } else if (strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
            port = argv[++i];
        } else if (strcmp(argv[i], "--test") == 0 && i + 1 < argc) {
            test_name = argv[++i];
            test_kind = parse_test_kind(test_name);
        } else if (strcmp(argv[i], "--led") == 0 && i + 1 < argc) {
            led_index = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--seconds") == 0 && i + 1 < argc) {
            wait_seconds = atoi(argv[++i]);
            seconds_explicitly_set = 1;
        } else if (strcmp(argv[i], "--ms") == 0 && i + 1 < argc) {
            buzzer_duration_ms = atoi(argv[++i]);
        } else if (argv[i][0] == '-') {
            print_usage(argv[0]);
            return 2;
        } else {
            port = argv[i];
        }
    }

    if ((led_index != 1) && (led_index != 2)) {
        fprintf(stderr, "invalid --led value: %d (allowed: 1 or 2)\n", led_index);
        return 2;
    }

    if ((wait_seconds < 1) || (wait_seconds > 300)) {
        fprintf(stderr, "invalid --seconds value: %d (allowed: 1..300)\n", wait_seconds);
        return 2;
    }

    if ((buzzer_duration_ms < 1) || (buzzer_duration_ms > 60000)) {
        fprintf(stderr, "invalid --ms value: %d (allowed: 1..60000)\n", buzzer_duration_ms);
        return 2;
    }

    if ((test_kind == TEST_GPIO_BUTTON_PASSTHROUGH) && !seconds_explicitly_set) {
        fprintf(stderr, "gpio_button_passthrough requires --seconds N (1..300)\n");
        return 2;
    }

    if (test_kind == TEST_UNKNOWN) {
        print_usage(argv[0]);
        fprintf(stderr, "unknown test: %s\n", test_name);
        return 2;
    }

    int fd = open_port(port, SERIAL_BAUD);
    if (fd < 0) {
        if (debug_enabled) {
            fprintf(stderr, "[debug] failed to open %s\n", port);
        }
        test_result_t result;
        init_result(&result, test_kind, test_name);
        emit_result_json(&result);
        return 1;
    }

    debug_print("[debug] opening %s\n", port);

    test_result_t result;
    if (test_kind == TEST_DRAIN) {
        run_test_drain(fd, &result);
    } else if (test_kind == TEST_HVF_VERSION_PASSTHROUGH) {
        run_test_hvf_version_passthrough(fd, &result);
    } else if (test_kind == TEST_GPIO_BUTTON_PASSTHROUGH) {
        run_test_gpio_button_passthrough(fd, &result, wait_seconds);
    } else if (test_kind == TEST_SENSOR_PROBE_ALL) {
        run_test_sensor_probe_all(fd, &result);
    } else if (test_kind == TEST_SENSOR_ENS210) {
        run_test_sensor_ens210(fd, &result);
    } else if (test_kind == TEST_SENSOR_LPS22DF) {
        run_test_sensor_lps22df(fd, &result);
    } else if (test_kind == TEST_IPC_SPI_ECHO) {
        run_test_ipc_spi_echo(fd, &result);
    } else if (test_kind == TEST_LED_ON_PASSTHROUGH) {
        run_test_led_on_passthrough(fd, &result, led_index);
    } else if (test_kind == TEST_LED_OFF_PASSTHROUGH) {
        run_test_led_off_passthrough(fd, &result, led_index);
    } else if (test_kind == TEST_BUZZER_ON_PASSTHROUGH) {
        run_test_buzzer_on_passthrough(fd, &result, buzzer_duration_ms);
    } else if (test_kind == TEST_STM32_ID_INFO_PASSTHROUGH) {
        run_test_stm32_id_info_passthrough(fd, &result);
    } else if (test_kind == TEST_STM32_ID_INFO) {
        run_test_stm32_id_info(fd, &result);
    } else {
        run_test_hvf_version(fd, &result);
    }

    close(fd);
    debug_print("[debug] closed port\n");

    emit_result_json(&result);
    return result.ok ? 0 : 1;
}
