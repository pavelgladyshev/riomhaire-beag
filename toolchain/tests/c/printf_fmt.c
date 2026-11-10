/* printf formats and sprintf */
#include <stdio.h>

int main(void)
{
    char buf[40];
    int n;
    printf("[%d] [%5d] [%-5d] [%05d] [%-05d]\n", 42, 42, 42, 42, 42);
    printf("[%d] [%5d] [%05d] [%d]\n", -42, -42, -42, -32767 - 1);
    printf("[%u] [%x] [%X] [%04x] [%o]\n", 65535u, 48879u, 48879u, 255u, 8u);
    printf("[%c] [%3c] [%-3c] [%s] [%6s] [%-6s] [%%]\n", 'A', 'B', 'C', "str", "ab", "ab");
    printf("[%s]\n", "");
    n = sprintf(buf, "%d+%d=%d", 12, 30, 42);
    printf("%s %d\n", buf, n);
    n = printf("12345\n");
    printf("%d\n", n);
    printf("%d %i %d\n", 0, -1, 32767);
    printf("%ld %hd\n", 5, 6);
    return 0;
}
