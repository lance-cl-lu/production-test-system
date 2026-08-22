#ifdef _WIN32

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "platform_io.h"

#include <stdio.h>
#include <string.h>

const char *platform_default_uart_port(void) {
    return "auto";
}

int platform_list_uart_ports(char ports[][128], int max_ports) {
    char target[1024];
    int count = 0;
    int number;
    if (ports == NULL || max_ports <= 0) return 0;
    for (number = 1; number <= 256 && count < max_ports; number++) {
        char name[16];
        snprintf(name, sizeof(name), "COM%d", number);
        if (QueryDosDeviceA(name, target, (DWORD)sizeof(target)) != 0) {
            snprintf(ports[count], 128, "%s", name);
            count++;
        }
    }
    return count;
}

static HANDLE uart_handle(platform_uart_t uart) {
    return (HANDLE)(intptr_t)uart;
}

platform_uart_t platform_uart_open(const char *port, int baud_rate) {
    char device_path[64];
    DCB state;
    COMMTIMEOUTS timeouts;
    HANDLE handle;

    if (port == NULL) return PLATFORM_UART_INVALID;
    if (strncmp(port, "\\\\.\\", 4) == 0) {
        snprintf(device_path, sizeof(device_path), "%s", port);
    } else {
        snprintf(device_path, sizeof(device_path), "\\\\.\\%s", port);
    }

    handle = CreateFileA(device_path, GENERIC_READ | GENERIC_WRITE, 0, NULL,
                         OPEN_EXISTING, 0, NULL);
    if (handle == INVALID_HANDLE_VALUE) return PLATFORM_UART_INVALID;

    memset(&state, 0, sizeof(state));
    state.DCBlength = sizeof(state);
    if (!GetCommState(handle, &state)) goto failed;
    state.BaudRate = (DWORD)baud_rate;
    state.ByteSize = 8;
    state.Parity = NOPARITY;
    state.StopBits = ONESTOPBIT;
    state.fBinary = TRUE;
    state.fParity = FALSE;
    state.fOutxCtsFlow = FALSE;
    state.fOutxDsrFlow = FALSE;
    /* Match a normal POSIX tty: no flow control, control lines asserted. */
    state.fDtrControl = DTR_CONTROL_ENABLE;
    state.fRtsControl = RTS_CONTROL_ENABLE;
    state.fOutX = FALSE;
    state.fInX = FALSE;
    if (!SetCommState(handle, &state)) goto failed;

    memset(&timeouts, 0, sizeof(timeouts));
    timeouts.ReadIntervalTimeout = MAXDWORD;
    timeouts.ReadTotalTimeoutConstant = 0;
    timeouts.ReadTotalTimeoutMultiplier = 0;
    timeouts.WriteTotalTimeoutConstant = 1000;
    if (!SetCommTimeouts(handle, &timeouts)) goto failed;
    SetupComm(handle, 4096, 4096);
    PurgeComm(handle, PURGE_RXABORT | PURGE_RXCLEAR | PURGE_TXABORT | PURGE_TXCLEAR);
    return (platform_uart_t)(intptr_t)handle;

failed:
    CloseHandle(handle);
    return PLATFORM_UART_INVALID;
}

void platform_uart_close(platform_uart_t uart) {
    if (uart != PLATFORM_UART_INVALID) CloseHandle(uart_handle(uart));
}

int platform_uart_wait_readable(platform_uart_t uart, int timeout_ms) {
    COMSTAT status;
    DWORD errors;
    int elapsed = 0;
    while (elapsed < timeout_ms) {
        if (!ClearCommError(uart_handle(uart), &errors, &status)) return -1;
        if (status.cbInQue > 0) return 1;
        Sleep(10);
        elapsed += 10;
    }
    return 0;
}

int platform_uart_read(platform_uart_t uart, void *buffer, size_t size) {
    DWORD count = 0;
    if (!ReadFile(uart_handle(uart), buffer, (DWORD)size, &count, NULL)) return -1;
    return (int)count;
}

int platform_uart_write(platform_uart_t uart, const void *buffer, size_t size) {
    DWORD count = 0;
    if (!WriteFile(uart_handle(uart), buffer, (DWORD)size, &count, NULL)) return -1;
    return (int)count;
}

int platform_uart_flush_input(platform_uart_t uart) {
    return PurgeComm(uart_handle(uart), PURGE_RXABORT | PURGE_RXCLEAR) ? 0 : -1;
}

void platform_sleep_ms(unsigned int milliseconds) {
    Sleep(milliseconds);
}

int platform_utc_time(time_t value, struct tm *result) {
    return gmtime_s(result, &value) == 0 ? 0 : -1;
}

int platform_file_stamp(const char *path, platform_file_stamp_t *stamp) {
    WIN32_FILE_ATTRIBUTE_DATA info;
    ULARGE_INTEGER ticks;
    if (stamp == NULL || !GetFileAttributesExA(path, GetFileExInfoStandard, &info)) return -1;
    ticks.LowPart = info.ftLastWriteTime.dwLowDateTime;
    ticks.HighPart = info.ftLastWriteTime.dwHighDateTime;
    stamp->value = ticks.QuadPart;
    stamp->valid = 1;
    return 0;
}

int platform_file_stamp_equal(const platform_file_stamp_t *left,
                              const platform_file_stamp_t *right) {
    return left != NULL && right != NULL && left->valid && right->valid &&
           left->value == right->value;
}

int platform_lock_acquire(platform_lock_t *lock, const char *name) {
    HANDLE mutex;
    (void)name;
    if (lock == NULL) return -1;
    mutex = CreateMutexA(NULL, FALSE, "Local\\ProductionTestSensorWatcher");
    if (mutex == NULL || GetLastError() == ERROR_ALREADY_EXISTS) {
        if (mutex != NULL) CloseHandle(mutex);
        return -1;
    }
    lock->value = (intptr_t)mutex;
    return 0;
}

void platform_lock_release(platform_lock_t *lock) {
    if (lock == NULL || lock->value == 0 || lock->value == -1) return;
    CloseHandle((HANDLE)(intptr_t)lock->value);
    lock->value = -1;
}

#endif
