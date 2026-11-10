; Example 1 (video 5.2-03): add 3 and 6, result in r3
    lli r1,3
    lli r2,6
    add r3,r2,r1
    bz  r0,0        ; all done: loop forever (not on the slide; stops the program here)
