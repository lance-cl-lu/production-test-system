#ifndef _WIN32

#include "platform_io.h"

#include <errno.h>
#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <termios.h>
#include <unistd.h>

const char *platform_default_uart_port(void) {
#ifdef __APPLE__
    return "/dev/tty.usbserial-0001";
#else
    return "/dev/ttyUSB0";
#endif
}

static int collect_ports(const char *directory, const char *prefix, char ports[][128],
                         int count, int max_ports) {
    DIR *dir = opendir(directory);
    struct dirent *entry;
    if (dir == NULL) return count;
    while (count < max_ports && (entry = readdir(dir)) != NULL) {
        if (strncmp(entry->d_name, prefix, strlen(prefix)) != 0) continue;
        snprintf(ports[count], 128, "%s/%s", directory, entry->d_name);
        count++;
    }
    closedir(dir);
    return count;
}

int platform_list_uart_ports(char ports[][128], int max_ports) {
    int count = 0;
    if (ports == NULL || max_ports <= 0) return 0;
    count = collect_ports("/dev/serial/by-id", "", ports, count, max_ports);
    if (count > 0) return count; /* Prefer stable Linux device identities. */
#ifdef __APPLE__
    count = collect_ports("/dev", "cu.usbserial", ports, count, max_ports);
    count = collect_ports("/dev", "cu.usbmodem", ports, count, max_ports);
#else
    count = collect_ports("/dev", "ttyUSB", ports, count, max_ports);
    count = collect_ports("/dev", "ttyACM", ports, count, max_ports);
#endif
    return count;
}

static speed_t baud_constant(int baud_rate) {
    switch (baud_rate) {
        case 9600: return B9600;
        case 19200: return B19200;
        case 38400: return B38400;
        case 57600: return B57600;
        case 115200: return B115200;
        default: return (speed_t)0;
    }
}

platform_uart_t platform_uart_open(const char *port, int baud_rate) {
    speed_t baud = baud_constant(baud_rate);
    int fd;
    struct termios tty;

    if (port == NULL || baud == (speed_t)0) return PLATFORM_UART_INVALID;
    fd = open(port, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) return PLATFORM_UART_INVALID;

    memset(&tty, 0, sizeof(tty));
    if (tcgetattr(fd, &tty) != 0) {
        close(fd);
        return PLATFORM_UART_INVALID;
    }
    cfsetispeed(&tty, baud);
    cfsetospeed(&tty, baud);
    tty.c_cflag = (tty.c_cflag & ~CSIZE) | CS8;
    tty.c_cflag |= CLOCAL | CREAD;
    tty.c_cflag &= ~(PARENB | PARODD | CSTOPB);
#ifdef CRTSCTS
    tty.c_cflag &= ~CRTSCTS;
#endif
    tty.c_iflag = 0;
    tty.c_oflag = 0;
    tty.c_lflag = 0;
    tty.c_cc[VMIN] = 0;
    tty.c_cc[VTIME] = 0;
    if (tcsetattr(fd, TCSANOW, &tty) != 0) {
        close(fd);
        return PLATFORM_UART_INVALID;
    }
    tcflush(fd, TCIFLUSH);
    return (platform_uart_t)fd;
}

void platform_uart_close(platform_uart_t uart) {
    if (uart != PLATFORM_UART_INVALID) close((int)uart);
}

int platform_uart_wait_readable(platform_uart_t uart, int timeout_ms) {
    fd_set read_set;
    struct timeval timeout;
    int fd = (int)uart;
    FD_ZERO(&read_set);
    FD_SET(fd, &read_set);
    timeout.tv_sec = timeout_ms / 1000;
    timeout.tv_usec = (timeout_ms % 1000) * 1000;
    return select(fd + 1, &read_set, NULL, NULL, &timeout);
}

int platform_uart_read(platform_uart_t uart, void *buffer, size_t size) {
    ssize_t count = read((int)uart, buffer, size);
    if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return 0;
    return count < 0 ? -1 : (int)count;
}

int platform_uart_write(platform_uart_t uart, const void *buffer, size_t size) {
    ssize_t count = write((int)uart, buffer, size);
    if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return 0;
    return count < 0 ? -1 : (int)count;
}

int platform_uart_flush_input(platform_uart_t uart) {
    return tcflush((int)uart, TCIFLUSH);
}

void platform_sleep_ms(unsigned int milliseconds) {
    usleep((useconds_t)milliseconds * 1000U);
}

int platform_utc_time(time_t value, struct tm *result) {
    return gmtime_r(&value, result) == NULL ? -1 : 0;
}

int platform_file_stamp(const char *path, platform_file_stamp_t *stamp) {
    struct stat info;
    if (stamp == NULL || stat(path, &info) != 0) return -1;
#ifdef __APPLE__
    stamp->value = (uint64_t)info.st_mtimespec.tv_sec * 1000000000ULL +
                   (uint64_t)info.st_mtimespec.tv_nsec;
#else
    stamp->value = (uint64_t)info.st_mtim.tv_sec * 1000000000ULL +
                   (uint64_t)info.st_mtim.tv_nsec;
#endif
    stamp->valid = 1;
    return 0;
}

int platform_file_stamp_equal(const platform_file_stamp_t *left,
                              const platform_file_stamp_t *right) {
    return left != NULL && right != NULL && left->valid && right->valid &&
           left->value == right->value;
}

int platform_lock_acquire(platform_lock_t *lock, const char *name) {
    int fd;
    if (lock == NULL || name == NULL) return -1;
    fd = open(name, O_CREAT | O_RDWR, 0666);
    if (fd < 0 || flock(fd, LOCK_EX | LOCK_NB) != 0) {
        if (fd >= 0) close(fd);
        return -1;
    }
    lock->value = (intptr_t)fd;
    return 0;
}

void platform_lock_release(platform_lock_t *lock) {
    if (lock == NULL || lock->value < 0) return;
    flock((int)lock->value, LOCK_UN);
    close((int)lock->value);
    lock->value = -1;
}

#endif
