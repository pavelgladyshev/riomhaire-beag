/* printf.c - printf and sprintf */
#include <stdio.h>
#include <stdarg.h>

static char *out_buf;      /* sprintf's buffer, or NULL for the display */

static void out(int c)
{
    if (out_buf)
        *out_buf++ = c;
    else
        putchar(c);
}

/* The conversions %d %i %u %x %X %o %b %c %s %p %%, with a width and the flags - and 0.
   Every conversion makes a string in buf (or points s at one), which one piece of code prints. */
static int format(const char *f, va_list ap)
{
    int count = 0, c;
    while ((c = *f++) != 0) {
        char buf[18];
        char *s, *p;
        int left = 0, zero = 0, width = 0, sign = 0, len;
        unsigned v, base = 0;
        if (c != '%') {
            out(c);
            count++;
            continue;
        }
        if (*f == '-') {
            left = 1;
            f++;
        }
        if (*f == '0') {
            zero = 1;
            f++;
        }
        while (*f >= '0' && *f <= '9')
            width = width * 10 + *f++ - '0';
        if (*f == 'l' || *f == 'h')
            f++;
        c = *f++;
        if (c == 0)
            break;
        s = buf + 17;
        *s = 0;
        v = *ap++;                   /* the argument (given back below if there is none) */
        switch (c) {
        case 'd':
        case 'i':
            if ((int)v < 0) {
                sign = 1;
                v = -v;
            }
            base = 10;
            break;
        case 'u':
            base = 10;
            break;
        case 'x':
        case 'X':
            base = 16;
            break;
        case 'p':
            base = 16;
            zero = 1;
            width = 4;
            break;
        case 'o':
            base = 8;
            break;
        case 'b':
            base = 2;
            break;
        case 'c':
            *--s = v;
            break;
        case 's':
            s = v ? (char *)v : "(null)";
            break;
        default:                     /* %% (or an unknown letter): print it, use no argument */
            *--s = c;
            ap--;
        }
        while (base) {
            int d = v % base;
            *--s = d + (d < 10 ? '0' : c == 'X' ? 'A' - 10 : 'a' - 10);
            v = v / base;
            if (!v)
                break;
        }
        for (p = s; *p; p++)
            ;
        len = p - s + sign;
        count += len > width ? len : width;
        if (sign && zero)
            out('-');
        if (!left)
            while (width-- > len)
                out(zero ? '0' : ' ');
        if (sign && !zero)
            out('-');
        while (*s)
            out(*s++);
        while (width-- > len)
            out(' ');
    }
    return count;
}

int printf(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    out_buf = NULL;
    return format(fmt, ap);
}

int sprintf(char *buf, const char *fmt, ...)
{
    va_list ap;
    int n;
    va_start(ap, fmt);
    out_buf = buf;
    n = format(fmt, ap);
    *out_buf = 0;
    out_buf = NULL;
    return n;
}
