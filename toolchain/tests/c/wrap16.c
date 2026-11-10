/* What is special about 16 bits: overflow wraps around, char is 16 bits, sizeof counts words */
#include <stdio.h>
#include <limits.h>

int main(void)
{
    int big = 32767;
    unsigned u = 65535u;
    char c = 1000;               /* a char holds 16 bits on BEAG */
    int i;
    big++;
    printf("%d\n", big);                       /* -32768 */
    u++;
    printf("%u\n", u);                         /* 0 */
    printf("%d\n", 200 * 200);                 /* 40000 wraps to -25536 */
    printf("%d\n", 30000 + 30000);             /* -5536 */
    printf("%d %d\n", c, (int)sizeof(c));      /* 1000 1 */
    printf("%d %d %d\n", (int)sizeof(int), (int)sizeof(char *), CHAR_BIT);
    printf("%d %d\n", INT_MIN / -1, INT_MIN % -1);   /* -32768 0, as the div instruction gives */
    printf("%u %u\n", 40000u / 3u, 40000u % 3u);     /* 13333 1 */
    printf("%u\n", (unsigned)-1 >> 4);                /* 4095 */
    printf("%d\n", -1 >> 4);                          /* -1 */
    printf("%d\n", -17 >> 2);                         /* -5 (rounds down) */
    printf("%d %d\n", -17 / 4, -17 % 4);              /* -4 -1 (rounds towards 0) */
    printf("%d\n", 1 << 15);                          /* -32768 */
    printf("%u\n", 1u << 15);                         /* 32768 */
    printf("%x\n", 0x1234 ^ 0xffff);                  /* edcb */
    printf("%d\n", 12345 * 3);                        /* 37035 wraps to -28501 */
    for (i = 0, u = 1; i < 20; i++)
        u = u * 3;
    printf("%u\n", u);                                /* 3^20 mod 65536 = 7057 */
    printf("%d\n", -32768 < 32767);                   /* 1 */
    printf("%d\n", (unsigned)-32768 < 32767u);        /* 0: 32768 > 32767 */
    printf("%d %d\n", INT_MAX + 1 < 0, -INT_MAX - 1 == INT_MIN);  /* 1 1 */
    return 0;
}
