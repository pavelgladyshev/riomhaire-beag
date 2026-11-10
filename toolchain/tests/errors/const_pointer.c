// error: is const and cannot be changed
int main(void)
{
    const char *s = "abc";
    *s = 'x';
    return 0;
}
