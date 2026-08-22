#ifndef PLATFORM_IO_H
#define PLATFORM_IO_H

#include <stddef.h>
#include <stdint.h>
#include <time.h>

/* intptr_t can hold either a POSIX file descriptor or a Windows HANDLE. */
typedef intptr_t platform_uart_t;
#define PLATFORM_UART_INVALID ((platform_uart_t)-1)

typedef struct {
    uint64_t value;
    int valid;
} platform_file_stamp_t;

typedef struct {
    intptr_t value;
} platform_lock_t;

const char *platform_default_uart_port(void);
int platform_list_uart_ports(char ports[][128], int max_ports);
platform_uart_t platform_uart_open(const char *port, int baud_rate);
void platform_uart_close(platform_uart_t uart);
int platform_uart_wait_readable(platform_uart_t uart, int timeout_ms);
int platform_uart_read(platform_uart_t uart, void *buffer, size_t size);
int platform_uart_write(platform_uart_t uart, const void *buffer, size_t size);
int platform_uart_flush_input(platform_uart_t uart);

void platform_sleep_ms(unsigned int milliseconds);
int platform_utc_time(time_t value, struct tm *result);

int platform_file_stamp(const char *path, platform_file_stamp_t *stamp);
int platform_file_stamp_equal(const platform_file_stamp_t *left,
                              const platform_file_stamp_t *right);

int platform_lock_acquire(platform_lock_t *lock, const char *name);
void platform_lock_release(platform_lock_t *lock);

#endif
