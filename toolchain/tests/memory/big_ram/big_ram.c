/* More RAM than the course's BEAG has: a 9000-word array, deep recursion and a large heap */
#include <stdio.h>
#include <stdlib.h>
#include <beag.h>

#define LEDS (*(volatile int *)__BEAG_DEVICE_LEDS__)

int big[9000];

int depth(int n)
{
    int pad[20];                 /* 22 or so words of stack per call */
    pad[0] = n;
    return n == 0 ? 0 : 1 + depth(n - 1) + pad[0] - n;
}

int main(void)
{
    unsigned i, sum = 0;
    int blocks = 0, inside = 1;
    int *p;
    for (i = 0; i < 9000; i++)
        big[i] = i;
    for (i = 0; i < 9000; i++)
        sum += big[i];
    printf("sum %u\n", sum);                     /* 9000*8999/2 mod 65536 */
    printf("big at %x, in the RAM: %d\n", (unsigned)big, (unsigned)big >= 0x8000u && (unsigned)big < 0xC000u);
    printf("depth %d\n", depth(200));            /* about 4400 words of stack */
    while ((p = malloc(500)) != NULL) {
        blocks++;
        if ((unsigned)p < 0x8000u || (unsigned)p + 500 > 0xC000u)
            inside = 0;
        p[499] = 1;
    }
    printf("heap: %d blocks of 500, all in the RAM: %d\n", blocks, inside);
    LEDS = 0x55;
    printf("key %c\n", getchar());
    return 0;
}
