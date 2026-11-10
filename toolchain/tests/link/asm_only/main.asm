; main.asm: prints "Hi" twice through a routine in print.asm
.extern print_char
.globl message
start:
    lli  r1,0x48         ; 'H'
    li   r7,print_char
    jalr r7,r7,r0
    lli  r1,0x69         ; 'i'
    li   r7,print_char
    jalr r7,r7,r0
loop:                     ; the same name as a label in print.asm: no clash
    li   r2,message
    lw   r1,(r2)
    li   r7,print_char
    jalr r7,r7,r0
finish:
    b    finish
#bank data
message: #res 1
