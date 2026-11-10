/* fact.c - recursion: n! and the Fibonacci numbers. Note where 8! = 40320 no longer fits
   into a 16-bit int. */
#include <stdio.h>

int fact(int n)
{
    if (n <= 1)
        return 1;
    return n * fact(n - 1);
}

int fib(int n)
{
    if (n < 2)
        return n;
    return fib(n - 1) + fib(n - 2);
}

int main(void)
{
    int n;
    for (n = 0; n <= 9; n++)
        printf("%d! = %d\n", n, fact(n));
    for (n = 0; n <= 20; n++)
        printf("%d ", fib(n));
    printf("\n");
    return 0;
}
