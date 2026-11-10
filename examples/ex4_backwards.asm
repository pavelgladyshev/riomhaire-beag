; Example 4 (video 5.2-08): read a line from the keyboard, print it backwards
    lli r1,0x00     ; r1 = 0x4000, display
    lhi r1,0x40
    lli r2,0x01     ; r2 = 0x4001, keyboard status
    lhi r2,0x40
    lli r3,0x02     ; r3 = 0x4002, keyboard data
    lhi r3,0x40
    lli r4,0x00     ; r4 = 0x2000, start of RAM
    lhi r4,0x20
    lli r5,0        ; r5 = number of characters typed
    lw  r6,(r2)     ; reading loop: wait for a key
    bz  r6,-1
    lw  r6,(r3)     ; r6 = key code
    lli r7,0x0A     ; Enter?
    sub r7,r7,r6
    bz  r7,6        ; yes: go and print
    sw  r6,(r4)     ; no: store it in RAM
    lli r7,1
    add r5,r5,r7
    add r4,r4,r7
    bz  r0,-10      ; next key
    bz  r5,7        ; printing loop: nothing left? done
    lli r7,1
    sub r5,r5,r7
    sub r4,r4,r7
    lw  r6,(r4)
    sw  r6,(r1)     ; print the character
    bz  r0,-6
    bz  r0,0        ; all done: loop forever
