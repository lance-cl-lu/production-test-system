# Makefile for PCBA test tools

# Detect Homebrew curl paths if available
CURL_PREFIX := $(shell brew --prefix curl 2>/dev/null)
CFLAGS := -O2 -Wall
LDFLAGS := -lcurl

# If Homebrew curl is present, add include/lib paths
ifeq ($(CURL_PREFIX),)
  # No brew curl detected; rely on system paths
else
  CFLAGS += -I"$(CURL_PREFIX)/include"
  LDFLAGS += -L"$(CURL_PREFIX)/lib"
endif

TARGET := pcba_watcher

.PHONY: all clean run

all: $(TARGET)

pcba_watcher: pcba_watcher.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

run: $(TARGET)
	./$(TARGET)

clean:
	rm -f $(TARGET)
