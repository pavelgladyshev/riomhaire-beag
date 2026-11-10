/* primes.c - the prime numbers below 500, by trial division */
#include <stdio.h>

int is_prime(int n)
{
    int d;
    if (n < 2)
        return 0;
    for (d = 2; d * d <= n; d++)
        if (n % d == 0)
            return 0;
    return 1;
}

int main(void)
{
    int n, count = 0;
    for (n = 2; n < 500; n++) {
        if (is_prime(n)) {
            printf("%4d", n);
            count++;
            if (count % 8 == 0)
                printf("\n");
        }
    }
    printf("\n%d primes\n", count);
    return 0;
}
