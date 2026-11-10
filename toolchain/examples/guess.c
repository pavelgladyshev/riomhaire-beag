/* guess.c - guess the number. The time you take to press the first key seeds the random
   numbers, so every game is different. */
#include <stdio.h>
#include <stdlib.h>
#include <beag.h>

int main(void)
{
    unsigned seed = 0;
    int secret, guess, tries = 0;
    printf("I have a number from 1 to 100.\nPress a key to start.\n");
    while (!kbhit())
        seed++;
    getchar();
    srand(seed);
    secret = rand() % 100 + 1;
    do {
        printf("Your guess? ");
        guess = read_int();
        tries++;
        if (guess < secret)
            printf("Too small.\n");
        else if (guess > secret)
            printf("Too big.\n");
    } while (guess != secret);
    printf("Yes, %d! You needed %d tries.\n", secret, tries);
    return 0;
}
