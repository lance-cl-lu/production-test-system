#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

// 簡單隨機 PASS/FAIL 與模擬量測數據
static const char* pass_or_fail(double pass_ratio) {
    double r = (double)rand() / (double)RAND_MAX;
    return r < pass_ratio ? "pass" : "fail";
}

static void now_iso(char *buf, size_t len) {
    time_t t = time(NULL);
    struct tm tm;
    gmtime_r(&t, &tm);
    strftime(buf, len, "%Y-%m-%dT%H:%M:%SZ", &tm);
}

int main(int argc, char **argv) {
    // 用法：./pcba_demo <stage> <serial>
    // stage: wifi|firmware|touch|bluetooth|speaker
    // 範例：./pcba_demo wifi NL20231203001

    if (argc < 3) {
        fprintf(stderr, "Usage: %s <stage> <serial>\n", argv[0]);
        return 1;
    }

    const char *stage = argv[1];
    const char *serial = argv[2];

    // 初始化隨機種子
    srand((unsigned int)time(NULL));

    char timestamp[32];
    now_iso(timestamp, sizeof(timestamp));

    // 依不同測項輸出不同 detail 範例
    if (strcmp(stage, "wifi") == 0) {
        int rssi = -30 - (rand() % 40); // -30 ~ -70
        const char *status = pass_or_fail(0.85);
        printf("{\"serial\":\"%s\",\"stage\":\"wifi\",\"status\":\"%s\",\"detail\":{\"rssi\":%d},\"timestamp\":\"%s\"}\n",
               serial, status, rssi, timestamp);
    } else if (strcmp(stage, "firmware") == 0) {
        int major = 1 + (rand() % 3);
        int minor = rand() % 10;
        int patch = rand() % 20;
        char version[32];
        snprintf(version, sizeof(version), "%d.%d.%d", major, minor, patch);
        const char *status = pass_or_fail(0.95);
        printf("{\"serial\":\"%s\",\"stage\":\"firmware\",\"status\":\"%s\",\"detail\":{\"version\":\"%s\"},\"timestamp\":\"%s\"}\n",
               serial, status, version, timestamp);
    } else if (strcmp(stage, "touch") == 0) {
        int buttons = 3;
        int passed = 0;
        for (int i = 0; i < buttons; ++i) {
            // 每個按鍵 90% 通過
            if (strcmp(pass_or_fail(0.9), "pass") == 0) passed++;
        }
        const char *status = (passed == buttons) ? "pass" : "fail";
        printf("{\"serial\":\"%s\",\"stage\":\"touch\",\"status\":\"%s\",\"detail\":{\"passed\":%d,\"total\":%d},\"timestamp\":\"%s\"}\n",
               serial, status, passed, buttons, timestamp);
    } else if (strcmp(stage, "bluetooth") == 0) {
        int rssi = -40 - (rand() % 30);
        const char *status = pass_or_fail(0.9);
        printf("{\"serial\":\"%s\",\"stage\":\"bluetooth\",\"status\":\"%s\",\"detail\":{\"rssi\":%d},\"timestamp\":\"%s\"}\n",
               serial, status, rssi, timestamp);
    } else if (strcmp(stage, "speaker") == 0) {
        int spl = 70 + (rand() % 20); // 70~89 dB
        const char *status = pass_or_fail(0.8);
        printf("{\"serial\":\"%s\",\"stage\":\"speaker\",\"status\":\"%s\",\"detail\":{\"spl_db\":%d},\"timestamp\":\"%s\"}\n",
               serial, status, spl, timestamp);
    } else {
        fprintf(stderr, "Unknown stage: %s\n", stage);
        return 2;
    }

    return 0;
}
