/* Bitwise operators: with andn and xor, and (beagcc --no-andn-xor) with the runtime routines */
#include <stdio.h>

unsigned g = 0xA5C3;

unsigned mix(unsigned a, unsigned b, unsigned c) { return (a & b) | (~a & c); }

int main(void)
{
    unsigned x = 0x1234, y = 0x0FF0, z = 0xFFFF, w = 0;
    unsigned v[4] = {0x8001, 0x7FFE, 0x5555, 0xAAAA};
    int s = -21, t = 6, i;

    printf("%x %x %x %x\n", x & y, x | y, x ^ y, ~x);
    printf("%x %x %x %x\n", x & z, x | z, x ^ z, ~z);
    printf("%x %x %x %x\n", x & w, x | w, x ^ w, ~w);
    printf("%x %x %x\n", x & 0xFF, x | 0x8000, x ^ 0x00FF);
    printf("%x %x %x %x\n", x & 0xFF00, x & 0x7FFF, x & 1, x & 0);
    printf("%x %x %x\n", 0xF0F0 & x, 0x0101 | x, 0xFFFF ^ x);
    printf("%d %d %d %d\n", s & t, s | t, s ^ t, ~s);
    printf("%d %d %d\n", s & -1, s | 0, s ^ s);
    printf("%u %u %u\n", x % 16u, x % 256u, x % 2u);
    printf("%x\n", mix(x, y, g));
    x &= y; printf("%x ", x);
    x |= 0x8001; printf("%x ", x);
    x ^= g; printf("%x ", x);
    x = ~x; printf("%x\n", x);
    w = 0;
    for (i = 0; i < 4; i++)
        w = (w ^ v[i]) | (v[i] & ~w & 0x0F0F);
    printf("%x\n", w);
    /* many values live at once */
    printf("%x\n", ((v[0] & v[1]) | (v[2] ^ v[3])) ^ ((v[0] | v[2]) & ~(v[1] ^ g)) ^ (g & 0x3C3C));
    if (x & 0x0100) printf("bit 8 set\n"); else printf("bit 8 clear\n");
    if ((g ^ 0xA5C3) == 0) printf("equal\n");
    return 0;
}
