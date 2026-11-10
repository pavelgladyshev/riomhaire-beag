; Example 2 (video 5.2-05): print "Hi" on the display at 0x4000
    lli r1,0x00     ; r1 = 0x4000, the display
    lhi r1,0x40
    lli r2,0x48     ; 'H'
    sw  r2,(r1)
    lli r2,0x69     ; 'i'
    sw  r2,(r1)
    bz  r0,0        ; all done: loop forever (not on the slide; stops the program here)
