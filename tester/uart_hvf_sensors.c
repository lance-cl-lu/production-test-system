#include "uart_hvf_sensors.h"

#include "uart_hvf.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/time.h>
#include <unistd.h>

#define SENSOR_IDLE_MS 200
#define SENSOR_WAIT_MS 100
#define SPI_RX_TIMEOUT_MS 12000
#define SPI_TX_TIMEOUT_MS 12000

static void spi_debug_dump(const char *label, const char *response) {
    fprintf(stderr, "[SPI][debug] %s: %s\n", label,
            (response != NULL && response[0] != '\0') ? response : "<empty>");
}

typedef struct {
    int fd;
    char response[1024];
} sensor_probe_context_t;

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
        int ready = wait_for_data(fd, 50);
        if (ready <= 0) {
            idle_wait += 50;
            if (idle_wait >= idle_ms) {
                return 0;
            }
            continue;
        }

        ssize_t received = read(fd, buf, sizeof(buf));
        if (received > 0) {
            idle_wait = 0;
        } else if (received < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            idle_wait += 50;
            if (idle_wait >= idle_ms) {
                return 0;
            }
        } else if (received < 0) {
            return -1;
        }
    }
}

static void write_all(int fd, const char *text) {
    size_t length = strlen(text);
    size_t sent = 0;

    while (sent < length) {
        ssize_t written = write(fd, text + sent, length - sent);
        if (written < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                usleep(10000);
                continue;
            }
            return;
        }
        sent += (size_t)written;
    }
}

static int read_to_buffer(int fd, char *buffer, size_t buffer_size, int timeout_ms) {
    size_t offset = 0;
    unsigned char chunk[256];
    int remaining_ms = timeout_ms;

    while (remaining_ms > 0 && buffer_size > 0) {
        int wait_ms = remaining_ms < 50 ? remaining_ms : 50;
        int ready = wait_for_data(fd, wait_ms);
        if (ready <= 0) {
            remaining_ms -= wait_ms;
            continue;
        }

        ssize_t received = read(fd, chunk, sizeof(chunk));
        if (received > 0) {
            size_t remaining = buffer_size - offset;
            size_t copy_length = (size_t)received;
            if (copy_length >= remaining) {
                copy_length = remaining - 1;
            }
            memcpy(buffer + offset, chunk, copy_length);
            offset += copy_length;
            if (offset >= buffer_size - 1) {
                break;
            }
        }
        remaining_ms -= wait_ms;
    }

    if (buffer_size > 0) {
        buffer[offset] = '\0';
    }
    return (int)offset;
}

static int run_sensor_probe(sensor_probe_context_t *context, const char *sensor_name) {
    char command[64];

    snprintf(command, sizeof(command), "sensor_probe %s\r\n", sensor_name);
    memset(context->response, 0, sizeof(context->response));
    write_all(context->fd, command);
    usleep(SENSOR_WAIT_MS * 1000);
    read_to_buffer(context->fd, context->response, sizeof(context->response), 1500);

    if (strstr(context->response, "<[OK]>") != NULL) {
        return 1;
    }
    if (strstr(context->response, "<[ERROR]>") != NULL ||
        strstr(context->response, "ERROR") != NULL ||
        strstr(context->response, "Unknown command") != NULL ||
        strstr(context->response, "Error:") != NULL) {
        return 0;
    }

    return 0;
}

static int extract_numeric_payload(const char *response, double *value) {
    const char *payload = strstr(response, "{[");
    char *end;

    if (payload == NULL) {
        return 0;
    }

    *value = strtod(payload + 2, &end);
    return end != payload + 2 && strncmp(end, "]}", 2) == 0;
}

static int run_measurement_command(sensor_probe_context_t *context,
                                   const char *command, double *value) {
    snprintf(context->response, sizeof(context->response), "");
    write_all(context->fd, command);
    write_all(context->fd, "\r\n");
    usleep(SENSOR_WAIT_MS * 1000);
    read_to_buffer(context->fd, context->response, sizeof(context->response), 1500);

    if (strstr(context->response, "<[OK]>") == NULL) {
        return 0;
    }
    return extract_numeric_payload(context->response, value);
}

int uart_hvf_probe_sensor(int fd, const char *sensor_name) {
    sensor_probe_context_t context = {.fd = fd};

    if (sensor_name == NULL || drain_until_idle(fd, SENSOR_IDLE_MS) != 0) {
        return -1;
    }

    return run_sensor_probe(&context, sensor_name);
}

int uart_hvf_measure_sensor(int fd, const char *sensor_name,
                            uart_hvf_sensor_measurement_t *result) {
    sensor_probe_context_t context = {.fd = fd};

    if (sensor_name == NULL || result == NULL ||
        drain_until_idle(fd, SENSOR_IDLE_MS) != 0) {
        return -1;
    }
    memset(result, 0, sizeof(*result));

    if (strcmp(sensor_name, "sht41") == 0 || strcmp(sensor_name, "ens210") == 0) {
        char command[96];
        snprintf(command, sizeof(command), "sensor_temperature_get %s C", sensor_name);
        result->temperature_valid = run_measurement_command(
            &context, command, &result->temperature);
        snprintf(command, sizeof(command), "sensor_humidity_get %s", sensor_name);
        result->humidity_valid = run_measurement_command(
            &context, command, &result->humidity);
        result->ok = result->temperature_valid && result->humidity_valid;
    } else if (strcmp(sensor_name, "lps22df") == 0) {
        result->temperature_valid = run_measurement_command(
            &context, "sensor_temperature_get lps22df C", &result->temperature);
        result->pressure_valid = run_measurement_command(
            &context, "sensor_pressure_get lps22df h", &result->pressure);
        result->ok = result->temperature_valid && result->pressure_valid;
    } else if (strcmp(sensor_name, "bme690") == 0) {
        result->temperature_valid = run_measurement_command(
            &context, "sensor_temperature_get bme690 C", &result->temperature);
        result->pressure_valid = run_measurement_command(
            &context, "sensor_pressure_get bme690 h", &result->pressure);
        result->humidity_valid = run_measurement_command(
            &context, "sensor_humidity_get bme690", &result->humidity);
        result->gas_resistance_valid = run_measurement_command(
            &context, "sensor_gas_resistance_get", &result->gas_resistance);
        result->ok = result->temperature_valid && result->pressure_valid &&
                     result->humidity_valid && result->gas_resistance_valid;
    } else {
        return -1;
    }

    return 0;
}

static int run_command_until_ok(int fd, const char *command, int timeout_ms) {
    char response[2048];
    int elapsed = 0;
    const int slice_ms = 100;
    size_t used = 0;

    write_all(fd, command);
    write_all(fd, "\r\n");

    memset(response, 0, sizeof(response));
    while (elapsed < timeout_ms) {
        int wait_ms = timeout_ms - elapsed;
        if (wait_ms > slice_ms) {
            wait_ms = slice_ms;
        }

        if (used >= sizeof(response) - 1U) {
            return -1;
        }

        int got = read_to_buffer(fd, response + used, sizeof(response) - used, wait_ms);
        if (got > 0) {
            used += (size_t)got;
        }

        if (strstr(response, "<[OK]>") != NULL) {
            return 0;
        }
        if (strstr(response, "<[ERROR]>") != NULL ||
            strstr(response, "Unknown command") != NULL) {
            return -1;
        }

        // 某些韌體會直接回到 prompt 但不帶結果標記，避免一路等到 timeout。
        if (strstr(response, "hvf>") != NULL) {
            return -1;
        }

        elapsed += wait_ms;
    }

    return -1;
}

static int run_command_until_ok_capture(int fd, const char *command, int timeout_ms,
                                        char *response_out, size_t response_out_size) {
    char response[2048];
    int elapsed = 0;
    const int slice_ms = 100;
    size_t used = 0;

    if (response_out != NULL && response_out_size > 0U) {
        response_out[0] = '\0';
    }

    write_all(fd, command);
    write_all(fd, "\r\n");

    memset(response, 0, sizeof(response));
    while (elapsed < timeout_ms) {
        int wait_ms = timeout_ms - elapsed;
        if (wait_ms > slice_ms) {
            wait_ms = slice_ms;
        }

        if (used >= sizeof(response) - 1U) {
            break;
        }

        int got = read_to_buffer(fd, response + used, sizeof(response) - used, wait_ms);
        if (got > 0) {
            used += (size_t)got;
        }

        if (strstr(response, "<[OK]>") != NULL) {
            if (response_out != NULL && response_out_size > 0U) {
                snprintf(response_out, response_out_size, "%s", response);
            }
            return 0;
        }
        if (strstr(response, "<[ERROR]>") != NULL ||
            strstr(response, "Unknown command") != NULL) {
            if (response_out != NULL && response_out_size > 0U) {
                snprintf(response_out, response_out_size, "%s", response);
            }
            return -1;
        }
        if (strstr(response, "hvf>") != NULL) {
            if (response_out != NULL && response_out_size > 0U) {
                snprintf(response_out, response_out_size, "%s", response);
            }
            return -1;
        }

        elapsed += wait_ms;
    }

    if (response_out != NULL && response_out_size > 0U) {
        snprintf(response_out, response_out_size, "%s", response);
    }
    return -1;
}

static int send_command_capture(int fd, const char *command, char *response, size_t response_size,
                                int timeout_ms) {
    if (response_size == 0U) {
        return -1;
    }
    memset(response, 0, response_size);
    write_all(fd, command);
    write_all(fd, "\r\n");
    read_to_buffer(fd, response, response_size, timeout_ms);
    return 0;
}

static int response_has_error_marker(const char *response) {
    return strstr(response, "<[ERROR]>") != NULL ||
           strstr(response, "Unknown command") != NULL ||
           strstr(response, "ERROR") != NULL ||
           strstr(response, "Error:") != NULL;
}

static int enter_passthrough(int fd) {
    char response[1024];
    static const char *const passthrough_commands[] = {
        "ipc_passthrough", "ipc_passtrough", "passthrough"
    };

    int entered = 0;
    for (size_t i = 0; i < sizeof(passthrough_commands) / sizeof(passthrough_commands[0]); ++i) {
        (void)send_command_capture(fd, passthrough_commands[i], response, sizeof(response), 2000);
        if (strstr(response, "Entering HVF passthrough") != NULL ||
            strstr(response, "Press Ctrl+C") != NULL) {
            entered = 1;
            break;
        }
        if (!response_has_error_marker(response)) {
            entered = 1;
            break;
        }
    }

    if (!entered) {
        return -1;
    }

    for (int i = 0; i < 3; i++) {
        write_all(fd, "\r");
        usleep(SENSOR_WAIT_MS * 1000);
    }
    return drain_until_idle(fd, SENSOR_IDLE_MS);
}

static void exit_passthrough(int fd) {
    char response[1024];
    static const char *const passthrough_exit_commands[] = {
        "ipc_passthrough_exit", "ipc_passtrough_exit", "passthrough_exit"
    };

    for (size_t i = 0; i < sizeof(passthrough_exit_commands) / sizeof(passthrough_exit_commands[0]); ++i) {
        (void)send_command_capture(fd, passthrough_exit_commands[i], response, sizeof(response), 2500);
        if (strstr(response, "IPC_IRQ pulse sent") != NULL ||
            strstr(response, "Exited HVF passthrough") != NULL ||
            strstr(response, "<[OK]>") != NULL) {
            return;
        }
        if (!response_has_error_marker(response)) {
            return;
        }
    }
}

int uart_hvf_test_buzzer(int fd, int duration_ms) {
    char command[64];
    int result;

    if (drain_until_idle(fd, SENSOR_IDLE_MS) != 0 || enter_passthrough(fd) != 0) {
        return -1;
    }
    snprintf(command, sizeof(command), "buzzer_on %d", duration_ms);
    result = run_command_until_ok(fd, command, duration_ms + 4000);
    exit_passthrough(fd);
    return result;
}

int uart_hvf_test_spi(int fd) {
    char response[2048];
    int result = -1;
    static const char *const spi_passthrough_commands[] = {
        "ipc_passthrough", "ipc_passtrough"
    };

    if (drain_until_idle(fd, SENSOR_IDLE_MS) != 0) {
        return -1;
    }

    // 實機流程：ipc_passthrough -> Enter x3 -> ipc_spi_rx_echo_auto。
    // 這個指令結束後韌體會自行回到 WLE console，因此不要再下 exit 指令。
    int entered = 0;
    for (size_t i = 0; i < sizeof(spi_passthrough_commands) / sizeof(spi_passthrough_commands[0]); ++i) {
        if (send_command_capture(fd, spi_passthrough_commands[i], response, sizeof(response), 2000) != 0) {
            continue;
        }
        spi_debug_dump("passthrough response", response);
        if (strstr(response, "Entering HVF passthrough") != NULL ||
            strstr(response, "Press Ctrl+C") != NULL ||
            !response_has_error_marker(response)) {
            entered = 1;
            break;
        }
    }

    if (!entered) {
        return -1;
    }

    for (int i = 0; i < 3; ++i) {
        write_all(fd, "\r");
        usleep(SENSOR_WAIT_MS * 1000);
    }
    if (drain_until_idle(fd, SENSOR_IDLE_MS) != 0) {
        return -1;
    }

    if (run_command_until_ok_capture(fd, "ipc_spi_rx_echo_auto", SPI_RX_TIMEOUT_MS,
                                     response, sizeof(response)) == 0) {
        spi_debug_dump("ipc_spi_rx_echo_auto response", response);
        result = 0;
    } else {
        spi_debug_dump("ipc_spi_rx_echo_auto failed response", response);
    }

    return result;
}

int uart_hvf_test_button(int fd, int wait_seconds) {
    char command[64];
    int timeout_ms;
    int result;

    if (wait_seconds <= 0) {
        return -1;
    }
    if (drain_until_idle(fd, SENSOR_IDLE_MS) != 0 || enter_passthrough(fd) != 0) {
        return -1;
    }

    snprintf(command, sizeof(command), "gpio_button %d", wait_seconds);
    timeout_ms = wait_seconds * 1000 + 800;
    result = run_command_until_ok(fd, command, timeout_ms);

    // 無論成功失敗，都要退出 passthrough，避免後續指令卡在同一模式。
    exit_passthrough(fd);
    return result;
}

int uart_hvf_test_led(int fd, int led_index) {
    return uart_hvf_set_led(fd, led_index, 1);
}

int uart_hvf_set_led(int fd, int led_index, int on) {
    char command[32];
    int result;

    if ((led_index != 1 && led_index != 2) ||
        drain_until_idle(fd, SENSOR_IDLE_MS) != 0 || enter_passthrough(fd) != 0) {
        return -1;
    }

    snprintf(command, sizeof(command), "%s %d", on ? "led_on" : "led_off", led_index);
    result = run_command_until_ok(fd, command, 1500);
    exit_passthrough(fd);
    return result;
}

int uart_hvf_probe_sensors(int fd, uart_hvf_sensor_result_t *result) {
    sensor_probe_context_t context = {.fd = fd};

    if (result == NULL) {
        return -1;
    }
    memset(result, 0, sizeof(*result));

    if (drain_until_idle(fd, SENSOR_IDLE_MS) != 0) {
        return -1;
    }

    write_all(fd, "\r");
    usleep(SENSOR_WAIT_MS * 1000);
    read_to_buffer(fd, context.response, sizeof(context.response), 300);

    result->sht41 = run_sensor_probe(&context, "sht41");
    result->ens210 = run_sensor_probe(&context, "ens210");
    result->lps22df = run_sensor_probe(&context, "lps22df");
    result->bme690 = run_sensor_probe(&context, "bme690");
    result->probe_completed = 1;

    return 0;
}
