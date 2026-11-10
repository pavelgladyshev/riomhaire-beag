/* const tables (kept in ROM on a von Neumann BEAG), initialised variables and local arrays */
#include <stdio.h>
#include <string.h>

const int squares[10] = { 0, 1, 4, 9, 16, 25, 36, 49, 64, 81 };
const char *const names[] = { "zero", "one", "two", "three" };
const char greeting[] = "constant greeting";
int counter = 7;                           /* initialised variable: copied to RAM at start-up */
int table[20] = { 1, 2, 3, [10] = 99, [19] = -1 };
char message[16] = "changeable";

int sum(const int *a, int n)
{
    int s = 0;
    while (n--)
        s += *a++;
    return s;
}

int lookup(int i)
{
    static const int primes[] = { 2, 3, 5, 7, 11, 13, 17, 19 };
    return primes[i];
}

int main(void)
{
    int local[8] = { 10, 20, 30, 40, 50, 60, 70, 80 };   /* copied from a ROM image */
    const char *s = names[3];
    int i;
    printf("%d %d %d\n", squares[3], sum(squares, 10), lookup(7));
    printf("%s %s %d\n", s, greeting, (int)strlen(greeting));
    counter += 1;
    message[0] = 'C';
    printf("%d %s %d %d %d\n", counter, message, table[2], table[10], table[19]);
    for (i = 0; i < 8; i++)
        local[i] += i;
    printf("%d %d %d\n", local[0], local[7], sum(local, 8));
    return 0;
}
