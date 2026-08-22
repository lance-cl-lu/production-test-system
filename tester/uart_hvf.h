/*
 * uart_hvf.h
 *
 * HVF 裝置的 UART 存取層，從 uart_hvf_probe.c 抽出供常駐程式使用。
 * 與 probe 不同之處：port 由呼叫端開啟並持有，不會每個指令重開一次。
 */

#ifndef UART_HVF_H
#define UART_HVF_H

#include <stddef.h>
#include "platform_io.h"

#define UART_HVF_DEFAULT_PORT (platform_default_uart_port())

void uart_hvf_set_debug(int enabled);

// 成功回傳跨平台 UART handle，失敗回 PLATFORM_UART_INVALID
platform_uart_t uart_hvf_open(const char *port);
void uart_hvf_close(platform_uart_t uart);

// 丟棄累積的輸入（例如換板子時的開機訊息），等到連續 idle_ms 無資料為止
void uart_hvf_flush_input(platform_uart_t uart, int idle_ms);

// 讀取 STM32 unique device ID
// passthrough = 0 讀 WLE；= 1 進 passthrough 讀 WBA
// 成功回 0，失敗回 -1
int uart_hvf_read_stm32_id(platform_uart_t uart, int passthrough, char *out, size_t out_len);

#endif  // UART_HVF_H
