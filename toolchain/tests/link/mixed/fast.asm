; fast.asm: functions called from C. The first argument is in r1, the others on the
; stack ([r6] = the second); the result goes back in r1; r3-r5 and r6 must be kept.
.globl _times10, _sum3, _shout
.extern _putchar, _counter

_times10:                  ; x*10 = x*8 + x*2, with additions only
    add  r2,r1,r1          ; 2x
    add  r1,r2,r2          ; 4x
    add  r1,r1,r1          ; 8x
    add  r1,r1,r2          ; 10x
    jalr r0,r7,r0

_sum3:                     ; a + b + c: b is at [sp], c at [sp+1]
    lw   r2,(r6)
    add  r1,r1,r2
    lli  r2,1
    add  r2,r6,r2
    lw   r2,(r2)
    add  r1,r1,r2
    jalr r0,r7,r0

_shout:                    ; print the string at r1 in capitals, using C's putchar
    lli  r2,-3             ; a frame of 3 words: the return address, r3, the string pointer
    add  r6,r6,r2
    sw   r7,(r6)
    lli  r2,1
    add  r2,r6,r2
    sw   r3,(r2)           ; r3 must be kept: save it
    add  r3,r1,r0          ; r3 = the string pointer (putchar keeps r3)
loop:
    lw   r1,(r3)
    bz   r1,done
    lli  r2,0x61
    sub  r2,r1,r2
    bltz r2,print          ; below 'a'
    lli  r2,-32
    add  r1,r1,r2          ; to capitals
print:
    li   r7,_putchar
    jalr r7,r7,r0          ; putchar(r1)
    li   r2,_counter
    lw   r1,(r2)
    lli  r7,1
    add  r1,r1,r7
    sw   r1,(r2)           ; counter++
    lli  r7,1
    add  r3,r3,r7
    b    loop
done:
    lli  r1,10
    li   r7,_putchar
    jalr r7,r7,r0          ; putchar('\n')
    lli  r2,1
    add  r2,r6,r2
    lw   r3,(r2)
    lw   r7,(r6)
    lli  r2,3
    add  r6,r6,r2
    jalr r0,r7,r0
