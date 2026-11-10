/* limits.h - BEAG: every integer type is 16 bits, a char too */
#ifndef _LIMITS_H
#define _LIMITS_H
#define CHAR_BIT   16
#define SCHAR_MIN  (-32767-1)
#define SCHAR_MAX  32767
#define UCHAR_MAX  65535u
#define CHAR_MIN   (-32767-1)
#define CHAR_MAX   32767
#define SHRT_MIN   (-32767-1)
#define SHRT_MAX   32767
#define USHRT_MAX  65535u
#define INT_MIN    (-32767-1)
#define INT_MAX    32767
#define UINT_MAX   65535u
#endif
