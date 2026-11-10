/* volatile: memory-mapped I/O through volatile pointers, and volatile variables */
#include <stdio.h>
#include <beag.h>

volatile int ticks;

int main(void)
{
    volatile int *display = (volatile int *)0x4000;
    volatile int *const ready = (volatile int *)0x4001;
    int *volatile p = (int *)&ticks;     /* a volatile pointer to a plain int */
    volatile int v = 5;
    int i, n = 0;
    for (i = 0; i < 3; i++) {
        v = v + i;                       /* v stays in memory: every access is made */
        ticks++;
    }
    *display = 'A' + v - 5;              /* 'A' + 3 = 'D' */
    *display = '\n';
    while (*ready) {                     /* read the waiting keys and count them */
        (void)BEAG_KBD_DATA;
        n++;
    }
    printf("%d %d %d %d\n", v, ticks, *p, n);
    printf("%d\n", (int)sizeof(volatile int));
    return 0;
}
