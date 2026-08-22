#ifndef PLATFORM_HTTP_H
#define PLATFORM_HTTP_H

#include <stddef.h>

int platform_http_post_json(const char *url, const char *json_payload, int timeout_seconds,
                            char *error, size_t error_size);
void platform_http_init(void);
void platform_http_cleanup(void);

#endif
