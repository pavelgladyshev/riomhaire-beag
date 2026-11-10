/* Arrays, pointers, pointer arithmetic, 2-D arrays, strings and string.h */
#include <stdio.h>
#include <string.h>

int grid[4][5];
char text[40];

int sum(const int *a, int n)
{
    int s = 0;
    while (n--)
        s += *a++;
    return s;
}

void reverse(char *s)
{
    char *e = s + strlen(s) - 1;
    while (s < e) {
        char t = *s;
        *s++ = *e;
        *e-- = t;
    }
}

int main(void)
{
    int a[10];
    int i, j, *p, *q;
    char local[20];
    for (i = 0; i < 10; i++)
        a[i] = i * i;
    printf("sum %d\n", sum(a, 10));
    printf("sum %d\n", sum(a + 3, 4));
    p = &a[2];
    q = a + 7;
    printf("%d %d %d %d\n", *p, p[1], *(q - 1), (int)(q - p));
    printf("%d %d %d\n", p < q, p == q - 5, q > p + 5);
    for (i = 0; i < 4; i++)
        for (j = 0; j < 5; j++)
            grid[i][j] = i * 10 + j;
    printf("%d %d %d\n", grid[2][3], grid[3][4], *(*(grid + 1) + 2));
    p = &grid[1][0];
    printf("%d %d\n", p[7], (int)sizeof(grid) / (int)sizeof(grid[0]));
    strcpy(text, "Hello");
    strcat(text, ", world");
    printf("%s %d\n", text, (int)strlen(text));
    strcpy(local, text + 7);
    reverse(local);
    printf("[%s]\n", local);
    printf("%d %d %d\n", strcmp("abc", "abd") < 0, strcmp("b", "a") > 0, strcmp("same", "same"));
    printf("%d\n", strncmp("abcdef", "abcxyz", 3));
    printf("%s|%s\n", strchr("hello", 'l'), strrchr("hello", 'l'));
    memset(a, 0, sizeof(a));
    printf("%d %d\n", a[0], a[9]);
    for (i = 0; i < 10; i++)
        a[i] = i;
    memmove(a + 2, a, 5 * sizeof(int));
    for (i = 0; i < 10; i++)
        printf("%d", a[i]);
    printf("\n");
    memcpy(a, a + 5, 3 * sizeof(int));
    printf("%d %d %d %d\n", a[0], a[1], a[2], memcmp(a, a + 5, 3 * sizeof(int)));
    {
        const char *words[] = { "zero", "one", "two", "three" };
        for (i = 3; i >= 0; i--)
            printf("%s ", words[i]);
        printf("\n");
        printf("%c%c\n", words[1][0], *words[2]);
    }
    {
        char *s = text;
        int vowels = 0;
        while (*s) {
            switch (*s++) {
            case 'a': case 'e': case 'i': case 'o': case 'u':
                vowels++;
            }
        }
        printf("vowels %d\n", vowels);
    }
    return 0;
}
