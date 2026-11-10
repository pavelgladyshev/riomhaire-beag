/* stdlib.c */
#include <stdlib.h>
#include <string.h>

int abs(int n)
{
    return n < 0 ? -n : n;
}

int atoi(const char *s)
{
    int n = 0, negative = 0;
    while (*s == ' ' || *s == '\t' || *s == '\n')
        s++;
    if (*s == '-') {
        negative = 1;
        s++;
    } else if (*s == '+') {
        s++;
    }
    while (*s >= '0' && *s <= '9')
        n = n * 10 + (*s++ - '0');
    return negative ? -n : n;
}

static unsigned next_random = 1;

int rand(void)
{
    next_random = next_random * 25173 + 13849;
    return next_random >> 1;
}

void srand(unsigned seed)
{
    next_random = seed;
}

void exit(int status)
{
    asm("jmp rt_halt");
}

/* A simple heap in the RAM bank data, from the end of the global variables up to the stack (or to
   the end of the bank when the stack is elsewhere). Every block has its size (in words, including
   this size word) in front of it; free blocks form a list. */
extern int __heap_start[];
extern int __heap_last[];
static int *heap_end;
static int *free_list;

void *malloc(size_t size)
{
    int *b;
    int **link;
    int n = size + 1;
    unsigned last, sp;
    if (n < 2)
        n = 2;
    for (link = &free_list; (b = *link) != NULL; link = (int **)&b[1]) {
        if (b[0] >= n) {
            *link = (int *)b[1];
            return b + 1;
        }
    }
    if (!heap_end)
        heap_end = __heap_start;
    b = heap_end;
    last = (unsigned)__heap_last;
    sp = (unsigned)&n;
    if (sp >= (unsigned)b && sp <= last)
        last = sp - 64;               /* the stack grows down towards the heap: keep away from it */
    if ((unsigned)n > last - (unsigned)b + 1 || (unsigned)b > last)
        return NULL;
    heap_end = b + n;
    b[0] = n;
    return b + 1;
}

void *calloc(size_t n, size_t size)
{
    void *p = malloc(n * size);
    if (p)
        memset(p, 0, n * size);
    return p;
}

void free(void *p)
{
    int *b;
    if (!p)
        return;
    b = (int *)p - 1;
    b[1] = (int)free_list;
    free_list = b;
}
