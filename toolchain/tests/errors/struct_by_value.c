// error: passing a struct by value is not supported
struct point { int x, y; };
int len(struct point p) { return p.x; }
int main(void) { return 0; }
