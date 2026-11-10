/* stdarg.h - BEAG: arguments are consecutive words on the stack */
#ifndef _STDARG_H
#define _STDARG_H

typedef int *va_list;
#define va_start(ap, last) ((ap) = (va_list)(&(last) + 1))
#define va_arg(ap, type)   (*(type *)((ap)++))
#define va_end(ap)         ((void)0)
#define va_copy(dst, src)  ((dst) = (src))

#endif
