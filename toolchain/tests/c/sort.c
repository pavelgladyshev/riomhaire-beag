/* Sorting and searching */
#include <stdio.h>

void bubble(int *a, int n)
{
    int i, j;
    for (i = 0; i < n - 1; i++)
        for (j = 0; j < n - 1 - i; j++)
            if (a[j] > a[j + 1]) {
                int t = a[j];
                a[j] = a[j + 1];
                a[j + 1] = t;
            }
}

void quicksort(int *a, int lo, int hi)
{
    int i = lo, j = hi, pivot = a[(lo + hi) / 2];
    while (i <= j) {
        while (a[i] < pivot)
            i++;
        while (a[j] > pivot)
            j--;
        if (i <= j) {
            int t = a[i];
            a[i] = a[j];
            a[j] = t;
            i++;
            j--;
        }
    }
    if (lo < j)
        quicksort(a, lo, j);
    if (i < hi)
        quicksort(a, i, hi);
}

int bsearch_int(const int *a, int n, int key)
{
    int lo = 0, hi = n - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        if (a[mid] == key)
            return mid;
        if (a[mid] < key)
            lo = mid + 1;
        else
            hi = mid - 1;
    }
    return -1;
}

int data[50];

int main(void)
{
    int a[12] = { 5, -3, 99, 0, 12, -32768, 32767, 7, 7, -1, 1000, 3 };
    int i;
    unsigned seed = 12345;
    bubble(a, 12);
    for (i = 0; i < 12; i++)
        printf("%d ", a[i]);
    printf("\n");
    for (i = 0; i < 50; i++) {
        seed = seed * 25173 + 13849;
        data[i] = (int)(seed % 1000) - 500;
    }
    quicksort(data, 0, 49);
    for (i = 0; i < 50; i++)
        printf("%d ", data[i]);
    printf("\n");
    for (i = 1; i < 50; i++)
        if (data[i - 1] > data[i])
            printf("not sorted at %d\n", i);
    printf("%d %d %d\n", bsearch_int(a, 12, 99), bsearch_int(a, 12, -32768), bsearch_int(a, 12, 4));
    return 0;
}
