/* stddef.h - BEAG */
#ifndef _STDDEF_H
#define _STDDEF_H

#define NULL ((void *)0)
typedef unsigned size_t;
typedef int ptrdiff_t;
#define offsetof(type, member) ((size_t)&((type *)0)->member)

#endif
