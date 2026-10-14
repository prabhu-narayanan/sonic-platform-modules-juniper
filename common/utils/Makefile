CC = gcc
CFLAGS = -Wall

TARGET = pcimem

all: $(TARGET)

pcimem: pcimem.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f $(TARGET)
