/* Structs, unions, enums, typedefs, linked lists with malloc */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct point {
    int x, y;
} Point;

struct rect {
    Point a, b;
    char name[8];
};

union word {
    int i;
    unsigned u;
    char c;
};

enum colour { RED, GREEN = 5, BLUE, LAST = BLUE + 10 };

struct node {
    int value;
    struct node *next;
};

int area(const struct rect *r)
{
    return (r->b.x - r->a.x) * (r->b.y - r->a.y);
}

Point mid;

void midpoint(const struct rect *r, Point *m)
{
    m->x = (r->a.x + r->b.x) / 2;
    m->y = (r->a.y + r->b.y) / 2;
}

struct node *push(struct node *list, int v)
{
    struct node *n = malloc(sizeof(struct node));
    n->value = v;
    n->next = list;
    return n;
}

int main(void)
{
    struct rect r;
    struct rect copy;
    Point pts[3];
    union word w;
    struct node *list = NULL, *n;
    int i, total;
    r.a.x = 1; r.a.y = 2; r.b.x = 11; r.b.y = 7;
    strcpy(r.name, "box");
    printf("area %d %s\n", area(&r), r.name);
    midpoint(&r, &mid);
    printf("mid %d %d\n", mid.x, mid.y);
    copy = r;
    copy.b.x = 21;
    printf("%d %d %s\n", area(&r), area(&copy), copy.name);
    for (i = 0; i < 3; i++) {
        pts[i].x = i;
        pts[i].y = i * i;
    }
    printf("%d %d\n", pts[2].x + pts[1].y, (int)sizeof(pts));
    printf("%d %d\n", (int)sizeof(struct rect), (int)sizeof(union word));
    w.i = -1;
    printf("%u %d\n", w.u, w.c);
    printf("%d %d %d %d\n", RED, GREEN, BLUE, LAST);
    for (i = 1; i <= 5; i++)
        list = push(list, i * 10);
    total = 0;
    for (n = list; n; n = n->next) {
        printf("%d ", n->value);
        total += n->value;
    }
    printf("= %d\n", total);
    while (list) {
        n = list->next;
        free(list);
        list = n;
    }
    list = push(NULL, 99);
    printf("%d\n", list->value);
    {
        Point *pp = &pts[1];
        pp->x += 100;
        (*pp).y -= 1;
        printf("%d %d\n", pts[1].x, pts[1].y);
    }
    return 0;
}
