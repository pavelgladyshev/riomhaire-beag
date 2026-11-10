// error: duplicate case 1
int main(void)
{
    int x = 1;
    switch (x) {
    case 1: return 1;
    case 1: return 2;
    }
    return 0;
}
