/* The preprocessor */
#include <stdio.h>
#include <limits.h>

#define SQUARE(x) ((x) * (x))
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define STR(x) #x
#define XSTR(x) STR(x)
#define CAT(a, b) a##b
#define N 10
#define DEBUG 1
#define LOG(...) printf(__VA_ARGS__)
#define EMPTY

#if DEBUG && N > 5
#define MODE "debug"
#elif N > 100
#define MODE "big"
#else
#define MODE "other"
#endif

#ifndef UNDEFINED_THING
#define FLAG 1
#endif

#ifdef FLAG
int flag = FLAG;
#else
int flag = -1;
#endif

int main(void)
{
    int CAT(var, 1) = 5;
    printf("%d %d %d\n", SQUARE(N), SQUARE(1 + 2), MAX(3, 7));
    printf("%s %s %s\n", STR(hello), XSTR(N), MODE);
    printf("%d %d\n", var1, flag);
    LOG("%d-%d\n", 1, 2);
    printf("%d %d %d\n", INT_MAX, INT_MIN, CHAR_BIT);
    printf("%u\n", UINT_MAX);
#if defined(N) && !defined(NOTHING)
    printf("defined ok\n");
#endif
#undef N
#ifdef N
    printf("still defined\n");
#endif
    EMPTY printf("line %d\n", __LINE__);
    return 0;
}
