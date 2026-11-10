/* The stack in its own RAM bank, the heap filling the bank data, and no keyboard */
#include <stdio.h>
#include <stdlib.h>

int fact(int n) { return n <= 1 ? 1 : n * fact(n - 1); }

int main(void)
{
    int local = 0;
    int blocks = 0, inside = 1;
    int *p;
    printf("fact %d\n", fact(7));
    printf("local in the stack bank: %d\n", (unsigned)&local >= 0x6000u && (unsigned)&local < 0x6400u);
    while ((p = malloc(100)) != NULL) {
        blocks++;
        if ((unsigned)p < 0x2000u || (unsigned)p + 100 > 0x2400u)
            inside = 0;
    }
    printf("heap: %d blocks, all in data: %d\n", blocks, inside);
    printf("getchar %d\n", getchar());
    return 0;
}
