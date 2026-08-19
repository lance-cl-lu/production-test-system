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
    int remaining = timeout_ms;

    write_all(fd, command);
    write_all(fd, "\r\n");
    while (remaining > 0) {
        memset(response, 0, sizeof(response));
        read_to_buffer(fd, response, sizeof(response), remaining);
        if (strstr(response, "<[OK]>") != NULL) {
            return 0;
        }
        if (strstr(response, "<[ERROR]>") != NULL ||
            strstr(response, "Unknown command") != NULL) {
            return -1;
        }
        remaining -= 100;
    }
    return -1;
}

static int enter_passthrough(int fd) {
    char response[1024];

    write_all(fd, "ipc_passthrough\r\n");
    read_to_buffer(fd, response, sizeof(response), 2000);
    if (strstr(response, "Entering HVF passthrough") == NULL &&
        strstr(response, "Press Ctrl+C") == NULL) {
        return -1;
    }
    for (int i = 0; i < 3; i++) {
        write_all(fd, "\r");
        usleep(SENSOR_WAIT_MS * 1000);
    }
    return drain_until_idle(fd, SENSOR_IDLE_MS);
}

static void exit_passthrough(int fd) {
    (void)run_command_until_ok(fd, "ipc_passthrough_exit", 2500);
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
    int result = -1;

    if (drain_until_idle(fd, SENSOR_IDLE_MS) != 0 || enter_passthrough(fd) != 0) {
        return -1;
    }
    if (run_command_until_ok(fd, "ipc_spi_rx_echo_auto", 35000) == 0 &&
        run_command_until_ok(fd, "ipc_spi_tx_echo", 35000) == 0) {
        result = 0;
    }
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
