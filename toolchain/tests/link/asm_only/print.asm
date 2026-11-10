; print.asm: print_char prints the character in r1 (and counts the calls)
#globl print_char
.extern message
print_char:
    li   r2,0x4000
    sw   r1,(r2)
    lli  r1,0x21         ; '!'
    li   r2,message
    sw   r1,(r2)         ; main prints this at the end
loop:
    jalr r0,r7,r0
#bank data
count: #res 2
