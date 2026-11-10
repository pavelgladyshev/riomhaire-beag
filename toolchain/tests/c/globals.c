/* Global and static initialisers */
#include <stdio.h>

int a = 5;
int b = -300;
unsigned big = 50000;
int arr[6] = { 1, 2, 3 };
int matrix[2][3] = { { 1, 2, 3 }, { 4, 5, 6 } };
int flat[2][2] = { 7, 8, 9 };
char msg[] = "global";
char sized[10] = "hi";
const char *names[] = { "ann", "bob", 0 };
int *pa = &a;
int *pm = &matrix[1][1];
struct item { const char *name; int qty; } items[] = { { "nut", 10 }, { "bolt", 20 } };
struct item designated = { .qty = 7, .name = "pin" };
int sparse[5] = { [3] = 33, [1] = 11 };
int zeros[100];
static int hidden = 42;

int next(void)
{
    static int n;
    return ++n;
}

int main(void)
{
    int i;
    printf("%d %d %u\n", a, b, big);
    for (i = 0; i < 6; i++)
        printf("%d ", arr[i]);
    printf("\n%d %d %d\n", matrix[0][2], matrix[1][0], (int)sizeof(matrix));
    printf("%d %d %d %d\n", flat[0][0], flat[0][1], flat[1][0], flat[1][1]);
    printf("%s %d %s %d %d\n", msg, (int)sizeof(msg), sized, (int)sizeof(sized), sized[5]);
    for (i = 0; names[i]; i++)
        printf("%s ", names[i]);
    printf("\n%d %d\n", *pa, *pm);
    printf("%s %d %s %d\n", items[1].name, items[0].qty, designated.name, designated.qty);
    for (i = 0; i < 5; i++)
        printf("%d ", sparse[i]);
    printf("\n%d %d %d\n", zeros[0], zeros[99], hidden);
    printf("%d %d %d\n", next(), next(), next() * 10);
    *pa = 77;
    printf("%d\n", a);
    return 0;
}
