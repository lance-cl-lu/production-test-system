#ifndef UART_HVF_SENSORS_H
#define UART_HVF_SENSORS_H

#include <stddef.h>

typedef struct {
    int sht41;
    int ens210;
    int lps22df;
    int bme690;
    int probe_completed;
} uart_hvf_sensor_result_t;

typedef struct {
    int ok;
    int temperature_valid;
    int humidity_valid;
    int pressure_valid;
    int gas_resistance_valid;
    double temperature;
    double humidity;
    double pressure;
    double gas_resistance;
} uart_hvf_sensor_measurement_t;

// 執行 sensor_probe_all，成功回 0
int uart_hvf_probe_sensors(int fd, uart_hvf_sensor_result_t *result);

// 執行單顆 sensor probe，成功偵測回 1，未偵測到回 0，通訊錯誤回 -1
int uart_hvf_probe_sensor(int fd, const char *sensor_name);

// 讀取指定 IC 支援的量測值，成功回 0
int uart_hvf_measure_sensor(int fd, const char *sensor_name,
                            uart_hvf_sensor_measurement_t *result);

int uart_hvf_test_buzzer(int fd, int duration_ms);
int uart_hvf_test_spi(int fd);

#endif
