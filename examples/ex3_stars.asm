; Example 3 (video 5.2-07): print five asterisks in a loop
    lli r1,0x00     ; r1 = 0x4000, the display
    lhi r1,0x40
    lli r2,5        ; r2 = counter
    lli r3,0x2A     ; r3 = '*'
    lli r4,1        ; r4 = 1
    sw  r3,(r1)     ; print '*'
    sub r2,r2,r4    ; counter - 1
    bnz r2,-2       ; back to the sw while the counter is not 0
    bz  r0,0        ; all done: loop forever
