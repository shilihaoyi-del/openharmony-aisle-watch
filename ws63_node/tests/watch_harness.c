#include <stdio.h>
#include <stdlib.h>

#include "fusion.h"

static void Output(const uint8_t *data, size_t length)
{
    if (fwrite(data, 1, length, stdout) != length) exit(1);
}

int main(void)
{
    Fusion node;
    FusionInit(&node, Output);
    uint8_t header[6];
    size_t size;
    while ((size = fread(header, 1, sizeof(header), stdin)) == sizeof(header)) {
        uint32_t now = header[0] | ((uint32_t)header[1] << 8) |
            ((uint32_t)header[2] << 16) | ((uint32_t)header[3] << 24);
        size_t length = header[4] | ((size_t)header[5] << 8);
        FusionPoll(&node, now);
        for (size_t i = 0; i < length; ++i) {
            const int byte = getchar();
            if (byte == EOF) return 1;
            FusionReceive(&node, (uint8_t)byte, now);
        }
    }
    return size || ferror(stdin) || ferror(stdout);
}
