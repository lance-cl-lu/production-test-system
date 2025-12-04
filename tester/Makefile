# Simple Makefile for pcba_watcher

# Detect Homebrew curl paths if available
CURL_PREFIX := $(shell brew --prefix curl 2>/dev/null)
CFLAGS := -O2
LDFLAGS := -lcurl

# If Homebrew curl is present, add include/lib paths
ifeq ($(CURL_PREFIX),)
  # No brew curl detected; rely on system paths
else
  CFLAGS += -I"$(CURL_PREFIX)/include"
  LDFLAGS += -L"$(CURL_PREFIX)/lib"
endif

TARGET := pcba_watcher
SRC := pcba_watcher.c

.PHONY: all clean run

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

run: $(TARGET)
	./$(TARGET)

clean:
	rm -f $(TARGET)
