// error: struct point has no member 'z'
struct point { int x, y; };
int main(void)
{
    struct point p;
    p.z = 3;
    return 0;
}
