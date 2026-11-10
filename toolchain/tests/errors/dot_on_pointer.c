// error: . needs a struct on its left
struct point { int x, y; };
int main(void)
{
    struct point p, *q = &p;
    q.x = 3;
    return 0;
}
