/* stdio.c - character input/output on the BEAG display and keyboard */
#include <stdio.h>
#include <beag.h>

int putchar(int c)
{
#ifdef BEAG_DISPLAY
    BEAG_DISPLAY = c;
#endif
    return c;
}

int getchar(void)
{
#ifdef BEAG_KBD_READY
    while (!BEAG_KBD_READY)
        ;
    return BEAG_KBD_DATA;
#else
    return EOF;                       /* this computer has no keyboard */
#endif
}

int puts(const char *s)
{
    while (*s)
        putchar(*s++);
    putchar('\n');
    return 0;
}
