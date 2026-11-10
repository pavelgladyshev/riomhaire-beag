/* Loops, break, continue, switch, goto */
#include <stdio.h>

int classify(int n)
{
    switch (n) {
    case 0:
        return 100;
    case 1:
    case 2:
        return 200;
    case -7:
        return 300;
    case 1000:
        return 400;
    default:
        return -1;
    }
}

int main(void)
{
    int i, j, sum = 0;
    for (i = 0; i < 10; i++) {
        if (i == 3)
            continue;
        if (i == 8)
            break;
        sum += i;
    }
    printf("sum %d\n", sum);
    i = 0;
    while (1) {
        i++;
        if (i > 100)
            break;
    }
    printf("i %d\n", i);
    i = 5;
    do {
        printf("%d ", i);
        i--;
    } while (i > 0);
    printf("\n");
    for (i = -8; i <= 1001; i++) {
        int c = classify(i);
        if (c != -1)
            printf("%d->%d ", i, c);
    }
    printf("\n");
    for (i = 0; i < 6; i++) {
        switch (i) {
        case 0: printf("zero "); 
        case 1: printf("one "); break;
        case 4: printf("four "); continue;
        default: printf("other ");
        }
        printf("| ");
    }
    printf("\n");
    for (i = 0; i < 3; i++)
        for (j = 0; j < 3; j++) {
            if (j == i)
                continue;
            printf("%d%d ", i, j);
        }
    printf("\n");
    i = 0;
again:
    i++;
    if (i < 5)
        goto again;
    printf("goto %d\n", i);
    for (;;) {
        if (++i > 20)
            break;
    }
    printf("for(;;) %d\n", i);
    {
        int k = 0, n = 0;
        while (k < 1000) {
            k += 7;
            if (k % 2)
                continue;
            n++;
        }
        printf("%d %d\n", k, n);
    }
    return 0;
}
