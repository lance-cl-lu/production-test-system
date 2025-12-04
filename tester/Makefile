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

TARGETS := pcba_watcher uid_searcher

.PHONY: all clean run_watcher run_searcher

all: $(TARGETS)

pcba_watcher: pcba_watcher.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

uid_searcher: uid_searcher.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

run_watcher: pcba_watcher
	./pcba_watcher

run_searcher: uid_searcher
	./uid_searcher

clean:
	rm -f $(TARGETS)
