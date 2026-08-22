#ifndef _WIN32

#include "platform_http.h"
#include <curl/curl.h>
#include <stdio.h>

void platform_http_init(void) {
    curl_global_init(CURL_GLOBAL_ALL);
}

void platform_http_cleanup(void) {
    curl_global_cleanup();
}

int platform_http_post_json(const char *url, const char *json_payload, int timeout_seconds,
                            char *error, size_t error_size) {
    CURL *curl = curl_easy_init();
    struct curl_slist *headers = NULL;
    CURLcode result;
    long status = 0;
    if (curl == NULL) return -1;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_payload);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, (long)timeout_seconds);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    result = curl_easy_perform(curl);
    if (result == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
    if (result != CURLE_OK && error != NULL && error_size > 0) {
        snprintf(error, error_size, "%s", curl_easy_strerror(result));
    } else if ((status < 200 || status >= 300) && error != NULL && error_size > 0) {
        snprintf(error, error_size, "HTTP %ld", status);
    }
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    return result == CURLE_OK && status >= 200 && status < 300 ? 0 : -1;
}

#endif
