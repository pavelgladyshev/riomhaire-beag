/* assert.c */
#include <stdio.h>
#include <stdlib.h>

void __assert_fail(const char *expr, const char *file, int line)
{
    printf("Assertion failed: %s, %s line %d\n", expr, file, line);
    exit(1);
}
