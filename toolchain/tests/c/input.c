/* Keyboard input: getchar, read_line, read_int */
#include <stdio.h>
#include <beag.h>
#include <ctype.h>

int main(void)
{
    char name[20];
    int a, b, c, n = 0;
    printf("Name? ");
    read_line(name, 20);
    printf("Hello, %s!\n", name);
    printf("Two numbers? ");
    a = read_int();
    b = read_int();
    printf("%d + %d = %d\n", a, b, a + b);
    while ((c = getchar()) != '.') {
        if (isalpha(c))
            n++;
    }
    printf("%d letters\n", n);
    printf("kbhit %d\n", kbhit());
    return 0;
}
