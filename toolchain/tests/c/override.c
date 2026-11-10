/* A program's own putchar replaces the library's (printf then uses it too), and asm() */
#include <stdio.h>
#include <beag.h>

int putchar(int c)
{
    if (c >= 'a' && c <= 'z')
        c = c - 'a' + 'A';
    BEAG_DISPLAY = c;
    return c;
}

int seven(void)
{
    int r;
    asm("lli r1,7");           /* the return value is in r1 */
    asm("lli r2,0\n    add r1,r1,r2");
    return;
}

int main(void)
{
    printf("shouting %d\n", 42);
    puts("quiet words");
    printf("%d\n", seven());
    return 0;
}
