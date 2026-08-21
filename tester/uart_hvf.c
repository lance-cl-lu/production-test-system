/*
 * uart_hvf.c
 *
 * 內容取自 uart_hvf_probe.c，保持相同的交握時序與解析方式。
 * probe 維持獨立可執行，方便單項手動測試。
 */

#include "uart_hvf.h"

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

static int debug_enabled = 0;

void uart_hvf_set_debug(int enabled) {
    debug_enabled = enabled;
}

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

static void trim_ascii_whitespace(char *text) {
    size_t start = 0;
    size_t end;

    while (text[start] != '\0' &&
           (text[start] == '\r' || text[start] == '\n' || text[start] == ' ' || text[start] == '\t')) {
        start++;
    }
    if (start > 0) {
        memmove(text, text + start, strlen(text + start) + 1);
    }

    end = strlen(text);
    while (end > 0 &&
           (text[end - 1] == '\r' || text[end - 1] == '\n' || text[end - 1] == ' ' || text[end - 1] == '\t')) {
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

// 韌體以 {[payload]} 包裝回應內容
static int extract_hvf_payload(const char *response, char *out, size_t out_len) {
    const char *start = strstr(response, "{[");
    if (start == NULL) {
        return -1;
    }
    start += 2;

    const char *end = strstr(start, "]}");
    if (end == NULL) {
        return -1;
    }

    size_t len = (size_t)(end - start);
    if (len >= out_len) {
        len = out_len - 1;
    }
    memcpy(out, start, len);
    out[len] = '\0';

    trim_ascii_whitespace(out);
    strip_control_chars(out);
    return 0;
}

int uart_hvf_open(const char *port) {
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

    cfsetispeed(&tty, SERIAL_BAUD);
    cfsetospeed(&tty, SERIAL_BAUD);

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
    debug_print("[debug] opened %s\n", port);
    return fd;
}

void uart_hvf_close(int fd) {
    if (fd >= 0) {
        close(fd);
        debug_print("[debug] closed port\n");
    }
}

void uart_hvf_flush_input(int fd, int idle_ms) {
    tcflush(fd, TCIFLUSH);  // 先丟掉 kernel 已緩衝的位元組
    (void)drain_until_idle(fd, idle_ms);
    tcflush(fd, TCIFLUSH);
    debug_print("[debug] input flushed (idle %d ms)\n", idle_ms);
}

static int read_stm32_id_direct(int fd, char *out, size_t out_len) {
    char after_enter[256];
    char response[1024];

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return -1;
    }

    write_all(fd, "\r");
    usleep(WAIT_MS * 1000);

    memset(after_enter, 0, sizeof(after_enter));
    read_to_buffer(fd, after_enter, sizeof(after_enter), 200);
    debug_print("[debug] after Enter bytes: %s\n", after_enter);

    write_all(fd, "stm32_id_info\r\n");
    usleep(WAIT_MS * 1000);

    memset(response, 0, sizeof(response));
    read_to_buffer(fd, response, sizeof(response), 1500);
    debug_print("[debug] raw response: %s\n", response);

    if (extract_hvf_payload(response, out, out_len) != 0) {
        return -1;
    }

    return (strstr(response, "<[OK]>") != NULL) ? 0 : -1;
}

static int read_stm32_id_passthrough(int fd, char *out, size_t out_len) {
    char passthrough_banner[1024];
    char id_response[1024];
    char exit_response[1024];
    static const char *const passthrough_commands[] = {"ipc_passthrough", "passthrough"};
    static const char *const passthrough_exit_commands[] = {"ipc_passthrough_exit", "passthrough_exit"};

    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] initial drain failed\n");
        return -1;
    }

    if (send_first_command_with_success_hints(
            fd, passthrough_commands,
            sizeof(passthrough_commands) / sizeof(passthrough_commands[0]),
            passthrough_banner, sizeof(passthrough_banner), 1200,
            "passthrough", "Entering HVF passthrough", "Press Ctrl+C") != 0) {
        debug_print("[debug] passthrough failed\n");
        return -1;
    }

    usleep((WAIT_MS + 50) * 1000);

    // 進入 passthrough 後連按 Enter 並清空緩衝，避免 banner 殘留干擾後續回應
    for (int i = 0; i < 3; i++) {
        write_all(fd, "\r");
        usleep(WAIT_MS * 1000);
    }
    if (drain_until_idle(fd, IDLE_MS) != 0) {
        debug_print("[debug] drain after passthrough Enter keys failed\n");
    }

    if (send_command_collect(fd, "stm32_id_info", id_response, sizeof(id_response), 1500) != 0) {
        debug_print("[debug] stm32_id_info first try failed, retrying\n");
        usleep((WAIT_MS + 100) * 1000);
        (void)send_command_collect(fd, "stm32_id_info", id_response, sizeof(id_response), 1500);
    }

    int extracted = extract_hvf_payload(id_response, out, out_len);

    // 無論讀取成敗都要退出 passthrough，否則裝置會卡在該模式
    int exit_ok = send_first_command_with_success_hints(
        fd, passthrough_exit_commands,
        sizeof(passthrough_exit_commands) / sizeof(passthrough_exit_commands[0]),
        exit_response, sizeof(exit_response), 2500,
        "passthrough exit", "IPC_IRQ pulse sent", "Exited HVF passthrough");

    if (extracted != 0 || strlen(out) == 0U) {
        return -1;
    }

    // 某些韌體會在 ipc_passthrough 時直接退出，後續 exit 指令可能回 Unknown command。
    // 只要 UID 已成功抽出，就視為讀取成功，避免誤判 SEARCH 失敗。
    if (exit_ok != 0 && strstr(exit_response, "<[OK]>") == NULL) {
        debug_print("[debug] passthrough exit not acknowledged, but UID already read\n");
    }

    return 0;
}

int uart_hvf_read_stm32_id(int fd, int passthrough, char *out, size_t out_len) {
    if (out == NULL || out_len == 0U) {
        return -1;
    }
    out[0] = '\0';

    return passthrough ? read_stm32_id_passthrough(fd, out, out_len)
                       : read_stm32_id_direct(fd, out, out_len);
}
