/* Comparisons (also with large values, where a plain subtraction would overflow),
   logical operators and ?: */
#include <stdio.h>

int big = 30000, small = -30000;
unsigned ubig = 60000, usmall = 5;

void show(int v) { printf("%d", v); }

int main(void)
{
    int vals[] = { -32768, -30000, -1, 0, 1, 30000, 32767 };
    int i, j;
    for (i = 0; i < 7; i++) {
        for (j = 0; j < 7; j++) {
            int a = vals[i], b = vals[j];
            show(a < b); show(a <= b); show(a > b); show(a >= b); show(a == b); show(a != b);
            printf(" ");
        }
        printf("\n");
    }
    printf("%d %d %d %d\n", small < big, big < small, small > big, big > small);
    printf("%d %d %d %d\n", usmall < ubig, ubig < usmall, ubig > 32768u, usmall > 32768u);
    for (i = 0; i < 7; i++) {
        int a = vals[i];
        show(a < 0); show(a <= 0); show(a > 0); show(a >= 0); show(a < 5); show(a > -5); show(a < -5);
        show(a > 100); show(a >= -32768); show(a <= 32767);
        printf(" ");
    }
    printf("\n");
    for (i = 0; i < 7; i++) {
        unsigned a = vals[i];
        show(a < 5u); show(a > 5u); show(a < 40000u); show(a > 40000u); show(a == 0u);
        printf(" ");
    }
    printf("\n");
    i = 0;
    j = (i++ && i++);  printf("%d %d\n", i, j);
    j = (i++ || i++);  printf("%d %d\n", i, j);
    j = (0 || i++);    printf("%d %d\n", i, j);
    j = !i;            printf("%d %d %d\n", j, !j, !!i);
    printf("%d %d\n", i > 2 ? 10 : 20, i < 2 ? 10 : 20);
    printf("%d\n", big > 0 && small < 0 && !(big < small) ? 1 : 0);
    return 0;
}
