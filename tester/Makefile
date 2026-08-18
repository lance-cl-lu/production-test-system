# Makefile for PCBA test tools

# brew --prefix 即使套件未安裝也會回傳路徑，所以要實際檢查目錄存在
CURL_PREFIX := $(shell brew --prefix curl 2>/dev/null)
CURL_LIBDIR := $(wildcard $(CURL_PREFIX)/lib)

CFLAGS := -O2 -Wall
LDFLAGS :=

ifneq ($(CURL_LIBDIR),)
  CFLAGS += -I"$(CURL_PREFIX)/include"
  LDFLAGS += -L"$(CURL_LIBDIR)"
endif

LDFLAGS += -lcurl

TARGETS := pcba_watcher sensor_watcher uart_hvf_probe

.PHONY: all clean run run-sensor

all: $(TARGETS)

pcba_watcher: pcba_watcher.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

sensor_watcher: sensor_watcher.c uart_hvf.c
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

uart_hvf_probe: uart_hvf_probe.c
	$(CC) $(CFLAGS) -o $@ $<

run: pcba_watcher
	./pcba_watcher

run-sensor: sensor_watcher
	./sensor_watcher

clean:
	rm -f $(TARGETS)
