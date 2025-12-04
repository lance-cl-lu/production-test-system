/*
 * uid_searcher.c
 * 
 * UID 搜尋工具：模擬從本機設備讀取 UID 並透過 HTTP POST 傳送至後端。
 * 
 * 編譯方式：
 *   gcc -o uid_searcher uid_searcher.c -lcurl
 * 或使用 Makefile:
 *   make uid_searcher
 * 
 * 使用方式：
 *   ./uid_searcher                    # 模擬搜尋並傳送隨機 UID
 *   ./uid_searcher <UID>              # 傳送指定的 UID
 * 
 * 功能：
 * 1. 模擬搜尋本機連接的設備（延遲 1-2 秒模擬搜尋過程）
 * 2. 產生或使用指定的 UID
 * 3. 透過 HTTP POST 傳送至 http://localhost:8000/api/pcba/uid-search
 * 4. 後端收到後會透過 WebSocket 廣播給前端
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <curl/curl.h>

#define API_URL "http://localhost:8000/api/pcba/uid-search"
#define MAX_UID_LENGTH 64

// 產生模擬的 UID（格式：NL-YYYYMMDD-XXXX）
void generate_uid(char* uid, size_t max_len) {
    time_t now = time(NULL);
    struct tm* t = localtime(&now);
    int random_suffix = rand() % 10000;
    
    snprintf(uid, max_len, "NL-%04d%02d%02d-%04d",
             t->tm_year + 1900,
             t->tm_mon + 1,
             t->tm_mday,
             random_suffix);
}

// libcurl 回調函數（用於接收回應）
size_t write_callback(void* contents, size_t size, size_t nmemb, void* userp) {
    size_t total_size = size * nmemb;
    printf("Response: %.*s\n", (int)total_size, (char*)contents);
    return total_size;
}

// 傳送 UID 到後端
int send_uid_to_backend(const char* uid) {
    CURL* curl;
    CURLcode res;
    int success = 0;

    curl = curl_easy_init();
    if (!curl) {
        fprintf(stderr, "Failed to initialize CURL\n");
        return 0;
    }

    // 構建 JSON payload
    char json_payload[256];
    snprintf(json_payload, sizeof(json_payload), "{\"uid\":\"%s\"}", uid);

    struct curl_slist* headers = NULL;
    headers = curl_slist_append(headers, "Content-Type: application/json");

    curl_easy_setopt(curl, CURLOPT_URL, API_URL);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_payload);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);

    printf("Sending UID to backend: %s\n", uid);
    printf("API URL: %s\n", API_URL);
    printf("Payload: %s\n", json_payload);

    res = curl_easy_perform(curl);

    if (res != CURLE_OK) {
        fprintf(stderr, "curl_easy_perform() failed: %s\n", curl_easy_strerror(res));
    } else {
        long http_code = 0;
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
        printf("HTTP Response Code: %ld\n", http_code);
        
        if (http_code >= 200 && http_code < 300) {
            success = 1;
            printf("✓ UID sent successfully\n");
        } else {
            fprintf(stderr, "✗ Server returned error code: %ld\n", http_code);
        }
    }

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    return success;
}

int main(int argc, char* argv[]) {
    srand(time(NULL));
    
    char uid[MAX_UID_LENGTH];
    
    // 如果有參數則使用指定的 UID，否則自動產生
    if (argc > 1) {
        strncpy(uid, argv[1], MAX_UID_LENGTH - 1);
        uid[MAX_UID_LENGTH - 1] = '\0';
        printf("Using specified UID: %s\n", uid);
    } else {
        printf("Searching for device...\n");
        // 模擬搜尋延遲
        sleep(1 + rand() % 2);
        
        generate_uid(uid, MAX_UID_LENGTH);
        printf("Device found! UID: %s\n", uid);
    }

    // 傳送 UID 到後端
    if (send_uid_to_backend(uid)) {
        printf("\n✓ UID search completed successfully\n");
        printf("  The UID should now appear in the frontend UI\n");
        return 0;
    } else {
        fprintf(stderr, "\n✗ Failed to send UID to backend\n");
        fprintf(stderr, "  Please check if backend is running at %s\n", API_URL);
        return 1;
    }
}
