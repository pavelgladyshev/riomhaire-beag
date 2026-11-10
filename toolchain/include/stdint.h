/* stdint.h - BEAG: only 16-bit integers exist */
#ifndef _STDINT_H
#define _STDINT_H
typedef int int16_t;
typedef unsigned uint16_t;
typedef int intptr_t;
typedef unsigned uintptr_t;
typedef int int_least16_t;
typedef unsigned uint_least16_t;
#define INT16_MIN  (-32767-1)
#define INT16_MAX  32767
#define UINT16_MAX 65535u
#endif
