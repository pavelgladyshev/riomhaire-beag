/* stdio.h - BEAG: output goes to the display, input comes from the keyboard */
#ifndef _STDIO_H
#define _STDIO_H
#include <stddef.h>

#define EOF (-1)

int putchar(int c);
int getchar(void);                    /* waits for a key; does not show it on the display     */
int puts(const char *s);
int printf(const char *format, ...);  /* %d %i %u %x %X %o %b %c %s %p %%, width, - and 0 flags */
int sprintf(char *buf, const char *format, ...);

#endif
