/* beag.c - keyboard helpers declared in beag.h */
#include <beag.h>
#include <stdio.h>
#include <stdlib.h>

int kbhit(void)
{
#ifdef BEAG_KBD_READY
    return BEAG_KBD_READY;
#else
    return 0;
#endif
}

int read_line(char *buf, int size)
{
    int n = 0;
    for (;;) {
        int c = getchar();
        if (c == '\n' || c == '\r' || c == EOF)
            break;
        if (c == 8 || c == 127) {          /* Backspace */
            if (n > 0) {
                n--;
                putchar(8);
            }
        } else if (n < size - 1) {
            buf[n++] = c;
            putchar(c);
        }
    }
    putchar('\n');
    buf[n] = 0;
    return n;
}

int read_int(void)
{
    char buf[8];
    read_line(buf, 8);
    return atoi(buf);
}
