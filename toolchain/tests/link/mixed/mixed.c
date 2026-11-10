/* C calling assembly and assembly calling C */
#include <stdio.h>

int times10(int x);               /* in fast.asm */
int sum3(int a, int b, int c);    /* in fast.asm */
void shout(const char *s);        /* in fast.asm: calls the C function putchar */
int counter;                      /* used by fast.asm */

int main(void)
{
    printf("%d %d\n", times10(42), sum3(1, 20, 300));
    shout("hello");
    printf("counter %d\n", counter);
    return 0;
}
