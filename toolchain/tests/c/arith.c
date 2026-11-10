/* Arithmetic, precedence, division and remainder signs, bitwise operators and shifts */
#include <stdio.h>

int add(int a, int b) { return a + b; }

int main(void)
{
    int a = 17, b = 5, c = -17, d = -5;
    unsigned u = 40000, v = 7;
    int x;

    printf("%d %d %d %d %d\n", a + b, a - b, a * b, a / b, a % b);
    printf("%d %d %d %d\n", c / b, c % b, a / d, a % d);
    printf("%d %d\n", c / d, c % d);
    printf("%d %d %d\n", 2 + 3 * 4, (2 + 3) * 4, 100 / 10 / 5);
    printf("%d %d\n", -a, - -a);
    printf("%u %u %u %u\n", u / v, u % v, u / 3u, u % 1000u);
    printf("%u %u\n", 65535u / 2u, 65535u % 256u);
    printf("%d %d %d\n", a & b, a | b, a ^ b);
    printf("%d %d %d\n", c & 0xff, c | 3, c ^ -1);
    printf("%d %d\n", ~a, ~c);
    printf("%d %d %d %d\n", a << 3, a >> 2, c >> 2, c >> 1);
    printf("%d %d\n", c >> 4, -1 >> 5);
    printf("%u %u\n", u >> 3, u >> 15);
    printf("%d %d %d\n", a % 8, c % 8, c & 7);
    for (x = 0; x < 6; x++)
        printf("%d ", a >> x);
    printf("\n");
    for (x = 0; x < 6; x++)
        printf("%d ", c >> x);
    printf("\n");
    for (x = 0; x < 6; x++)
        printf("%d ", 3 << x);
    printf("\n");
    x = 10;
    x += 5; printf("%d ", x);
    x -= 3; printf("%d ", x);
    x *= 4; printf("%d ", x);
    x /= 5; printf("%d ", x);
    x %= 4; printf("%d ", x);
    x <<= 3; printf("%d ", x);
    x >>= 1; printf("%d ", x);
    x |= 1; printf("%d ", x);
    x &= 6; printf("%d ", x);
    x ^= 15; printf("%d\n", x);
    printf("%d %d\n", add(add(1, 2), add(3, add(4, 5))), add(a * b, c * d));
    printf("%d\n", (a + b) * (c + d) - (a - b) * (c - d) + (a * (b + (c * (d + 1)))));
    return 0;
}
