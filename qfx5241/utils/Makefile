CC = gcc
CFLAGS = -Wall

# pcimem source lives in the common utils/ directory
COMMON_UTILS = ../../common/utils

TARGET = pcimem

all: $(TARGET)

pcimem: $(COMMON_UTILS)/pcimem.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f $(TARGET)
