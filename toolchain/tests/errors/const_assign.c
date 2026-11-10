// error: the object 'limit' is const and cannot be changed
const int limit = 10;
int main(void)
{
    limit = 20;
    return limit;
}
