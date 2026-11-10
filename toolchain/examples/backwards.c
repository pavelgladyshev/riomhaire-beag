/* backwards.c - programming example 4 of lecture 5.2 (the backwards printer), in C.
   Type a line and press Enter: the program prints it backwards. Compare the assembly that
   beagcc makes (backwards.asm) with the one written by hand in the lecture. */
#include <beag.h>

int main(void)
{
    char *ram = (char *)0x2000;     /* the start of RAM, as in the lecture */
    int count = 0;                  /* characters typed so far */
    int c;

    for (;;) {
        while (!BEAG_KBD_READY)     /* wait for a key */
            ;
        c = BEAG_KBD_DATA;
        if (c == '\n')              /* Enter: stop reading */
            break;
        ram[count] = c;             /* keep the character in RAM */
        count++;
    }
    while (count > 0) {             /* print the characters in reverse order */
        count--;
        BEAG_DISPLAY = ram[count];
    }
    return 0;
}
