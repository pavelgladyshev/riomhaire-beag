/* calc.c - a calculator for integer expressions such as 2*(3+4)-10/3.
   It shows how a recursive-descent parser works: each function reads one level of the
   grammar and calls the next one.
       expr   = term { ('+' | '-') term }
       term   = factor { ('*' | '/' | '%') factor }
       factor = number | '-' factor | '(' expr ')'
   An empty line ends the program. */
#include <stdio.h>
#include <ctype.h>
#include <beag.h>

char line[60];
char *p;          /* the next character to read */
int error;

int expr(void);

void skip_spaces(void)
{
    while (*p == ' ')
        p++;
}

int factor(void)
{
    int v = 0;
    skip_spaces();
    if (*p == '-') {
        p++;
        return -factor();
    }
    if (*p == '(') {
        p++;
        v = expr();
        skip_spaces();
        if (*p == ')')
            p++;
        else
            error = 1;
        return v;
    }
    if (!isdigit(*p)) {
        error = 1;
        return 0;
    }
    while (isdigit(*p))
        v = v * 10 + (*p++ - '0');
    return v;
}

int term(void)
{
    int v = factor();
    for (;;) {
        int op, w;
        skip_spaces();
        op = *p;
        if (op != '*' && op != '/' && op != '%')
            return v;
        p++;
        w = factor();
        if (op == '*')
            v = v * w;
        else if (w == 0)
            error = 2;
        else if (op == '/')
            v = v / w;
        else
            v = v % w;
    }
}

int expr(void)
{
    int v = term();
    for (;;) {
        skip_spaces();
        if (*p == '+') {
            p++;
            v = v + term();
        } else if (*p == '-') {
            p++;
            v = v - term();
        } else {
            return v;
        }
    }
}

int main(void)
{
    printf("BEAG calculator (16-bit integers)\n");
    for (;;) {
        int v;
        printf("> ");
        if (read_line(line, 60) == 0)
            break;
        p = line;
        error = 0;
        v = expr();
        skip_spaces();
        if (*p != 0 && !error)
            error = 1;
        if (error == 1)
            printf("syntax error at '%c'\n", *p ? *p : ' ');
        else if (error == 2)
            printf("division by zero\n");
        else
            printf("%d\n", v);
    }
    printf("bye\n");
    return 0;
}
