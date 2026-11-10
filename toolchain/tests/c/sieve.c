/* Primes and number theory */
#include <stdio.h>

char composite[1000];

int isqrt(int n)
{
    int r = 0;
    while ((r + 1) * (r + 1) <= n)
        r++;
    return r;
}

int main(void)
{
    int i, j, count = 0, last = 0;
    for (i = 2; i < 1000; i++) {
        if (composite[i])
            continue;
        count++;
        last = i;
        if (i < 32)                 /* i * i must not overflow: 182 * 182 > 32767 */
            for (j = i * i; j < 1000; j += i)
                composite[j] = 1;
    }
    printf("%d primes below 1000, the largest %d\n", count, last);
    for (i = 2; i < 60; i++)
        if (!composite[i])
            printf("%d ", i);
    printf("\n%d %d %d\n", isqrt(99), isqrt(100), isqrt(30000));
    {
        unsigned a = 1, b = 1, t;
        for (i = 0; i < 22; i++) {
            t = a + b;
            a = b;
            b = t;
        }
        printf("fib %u\n", b);
    }
    return 0;
}
