/* Included first when a test is compiled natively (by run_tests.py --host) to produce its
   expected output: the system headers are read before unsigned is narrowed to 16 bits. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdarg.h>
#include <limits.h>
#define unsigned unsigned short
