#ifdef _WIN32

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winhttp.h>
#include "platform_http.h"

#include <stdio.h>
#include <string.h>

void platform_http_init(void) {}
void platform_http_cleanup(void) {}

static int utf8_to_wide(const char *input, wchar_t *output, int output_length) {
    return MultiByteToWideChar(CP_UTF8, 0, input, -1, output, output_length) > 0 ? 0 : -1;
}

int platform_http_post_json(const char *url, const char *json_payload, int timeout_seconds,
                            char *error, size_t error_size) {
    wchar_t wide_url[2048];
    URL_COMPONENTS parts;
    wchar_t host[256];
    wchar_t path[1536];
    HINTERNET session = NULL, connection = NULL, request = NULL;
    DWORD status = 0, status_size = sizeof(status);
    int ok = -1;

    if (utf8_to_wide(url, wide_url, (int)(sizeof(wide_url) / sizeof(wide_url[0]))) != 0)
        goto done;
    memset(&parts, 0, sizeof(parts));
    parts.dwStructSize = sizeof(parts);
    parts.lpszHostName = host;
    parts.dwHostNameLength = (DWORD)(sizeof(host) / sizeof(host[0]));
    parts.lpszUrlPath = path;
    parts.dwUrlPathLength = (DWORD)(sizeof(path) / sizeof(path[0]));
    if (!WinHttpCrackUrl(wide_url, 0, 0, &parts)) goto done;
    host[parts.dwHostNameLength] = L'\0';
    path[parts.dwUrlPathLength] = L'\0';

    session = WinHttpOpen(L"ProductionTestSensorWatcher/1.0",
                          WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                          WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (session == NULL) goto done;
    WinHttpSetTimeouts(session, timeout_seconds * 1000, timeout_seconds * 1000,
                       timeout_seconds * 1000, timeout_seconds * 1000);
    connection = WinHttpConnect(session, host, parts.nPort, 0);
    if (connection == NULL) goto done;
    request = WinHttpOpenRequest(connection, L"POST", path, NULL, WINHTTP_NO_REFERER,
                                 WINHTTP_DEFAULT_ACCEPT_TYPES,
                                 parts.nScheme == INTERNET_SCHEME_HTTPS ?
                                 WINHTTP_FLAG_SECURE : 0);
    if (request == NULL) goto done;
    if (!WinHttpSendRequest(request, L"Content-Type: application/json\r\n", (DWORD)-1L,
                            (LPVOID)json_payload, (DWORD)strlen(json_payload),
                            (DWORD)strlen(json_payload), 0) ||
        !WinHttpReceiveResponse(request, NULL)) goto done;
    if (!WinHttpQueryHeaders(request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                             WINHTTP_HEADER_NAME_BY_INDEX, &status, &status_size,
                             WINHTTP_NO_HEADER_INDEX)) goto done;
    if (status >= 200 && status < 300) ok = 0;

done:
    if (ok != 0 && error != NULL && error_size > 0) {
        snprintf(error, error_size, status ? "HTTP %lu" : "WinHTTP error %lu",
                 (unsigned long)(status ? status : GetLastError()));
    }
    if (request != NULL) WinHttpCloseHandle(request);
    if (connection != NULL) WinHttpCloseHandle(connection);
    if (session != NULL) WinHttpCloseHandle(session);
    return ok;
}

#endif
