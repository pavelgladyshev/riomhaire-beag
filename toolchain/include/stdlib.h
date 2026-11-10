/* stdlib.h - BEAG */
#ifndef _STDLIB_H
#define _STDLIB_H
#include <stddef.h>

#define RAND_MAX 32767
#define EXIT_SUCCESS 0
#define EXIT_FAILURE 1

int abs(int n);
int atoi(const char *s);
int rand(void);
void srand(unsigned seed);
void exit(int status);                /* stops the program (BEAG loops on the spot) */
void *malloc(size_t size);            /* size in words: malloc(10 * sizeof(int)) */
void *calloc(size_t n, size_t size);
void free(void *p);

#endif
