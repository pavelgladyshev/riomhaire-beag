/* Recursion, many arguments, function pointers, variadic functions, static locals */
#include <stdio.h>
#include <stdarg.h>

int fact(int n) { return n <= 1 ? 1 : n * fact(n - 1); }
int fib(int n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }
int ack(int m, int n)
{
    if (m == 0) return n + 1;
    if (n == 0) return ack(m - 1, 1);
    return ack(m - 1, ack(m, n - 1));
}
int many(int a, int b, int c, int d, int e, int f, int g)
{
    return a - b + c - d + e - f + g * 2;
}
int twice(int (*f)(int), int x) { return f(f(x)); }
int inc(int x) { return x + 1; }
int sq(int x) { return x * x; }
int counter(void)
{
    static int n = 10;
    return n++;
}
int sum(int count, ...)
{
    va_list ap;
    int s = 0;
    va_start(ap, count);
    while (count--)
        s += va_arg(ap, int);
    va_end(ap);
    return s;
}
void swap(int *a, int *b) { int t = *a; *a = *b; *b = t; }
int gcd(int a, int b) { while (b) { int t = a % b; a = b; b = t; } return a; }

int (*ops[3])(int) = { inc, sq, 0 };

int main(void)
{
    int i, x = 3, y = 4;
    int (*fp)(int);
    for (i = 0; i <= 7; i++)
        printf("%d ", fact(i));
    printf("\n");
    for (i = 0; i <= 15; i++)
        printf("%d ", fib(i));
    printf("\n");
    printf("ack %d %d\n", ack(2, 3), ack(1, 5));
    printf("many %d\n", many(1, 2, 3, 4, 5, 6, 7));
    printf("twice %d %d\n", twice(inc, 5), twice(sq, 3));
    fp = sq;
    printf("fp %d %d\n", fp(7), (*fp)(8));
    ops[2] = fp;
    for (i = 0; i < 3; i++)
        printf("%d ", ops[i](i + 2));
    printf("\n");
    x = counter();
    y = counter();
    printf("counter %d %d %d\n", x, y, counter());
    x = 3;
    y = 4;
    printf("sum %d %d %d\n", sum(0), sum(3, 1, 2, 3), sum(5, 10, 20, 30, 40, -100));
    swap(&x, &y);
    printf("swap %d %d\n", x, y);
    printf("gcd %d %d\n", gcd(1071, 462), gcd(17, 5));
    printf("nested %d\n", fact(fib(4)) + many(fact(3), fib(5), 1, 1, 1, 1, sq(inc(2))));
    return 0;
}
