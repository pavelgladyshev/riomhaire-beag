; andn and xor (opcodes A and B), checked against add/sub/mul/div/rem on the same values.
; Prints '.' for every correct result, the first letter of the instruction for a wrong one,
; then 'Z' if andn/xor into r0 left r0 at 0 and lli+lhi still work. Runs on the circuits too.
    li r6,0x4000
    li r1,0x4d3c
    li r2,0x0001
    andn r3,r1,r2
    li r5,0x4d3c
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail0
    lli r5,'.'
    sw r5,(r6)
    b next0
fail0:
    lli r5,'A'
    sw r5,(r6)
next0:
    li r1,0xff00
    li r2,0x0001
    andn r1,r1,r2
    li r5,0xff00
    sub r5,r1,r5
    li r6,0x4000
    bnz r5,fail1
    lli r5,'.'
    sw r5,(r6)
    b next1
fail1:
    lli r5,'A'
    sw r5,(r6)
next1:
    li r1,0xffff
    li r2,0x18b8
    andn r2,r1,r2
    li r5,0xe747
    sub r5,r2,r5
    li r6,0x4000
    bnz r5,fail2
    lli r5,'.'
    sw r5,(r6)
    b next2
fail2:
    lli r5,'A'
    sw r5,(r6)
next2:
    li r5,0x18b8
    li r4,0xffff
    andn r4,r5,r4
    li r5,0x0000
    sub r5,r4,r5
    li r6,0x4000
    bnz r5,fail3
    lli r5,'.'
    sw r5,(r6)
    b next3
fail3:
    lli r5,'A'
    sw r5,(r6)
next3:
    li r1,0x1234
    li r2,0xffff
    andn r3,r1,r2
    li r5,0x0000
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail4
    lli r5,'.'
    sw r5,(r6)
    b next4
fail4:
    lli r5,'A'
    sw r5,(r6)
next4:
    li r1,0x18b8
    li r2,0x0001
    andn r3,r1,r2
    li r5,0x18b8
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail5
    lli r5,'.'
    sw r5,(r6)
    b next5
fail5:
    lli r5,'A'
    sw r5,(r6)
next5:
    li r1,0x8000
    li r2,0x1234
    andn r1,r1,r2
    li r5,0x8000
    sub r5,r1,r5
    li r6,0x4000
    bnz r5,fail6
    lli r5,'.'
    sw r5,(r6)
    b next6
fail6:
    lli r5,'A'
    sw r5,(r6)
next6:
    li r1,0x0001
    li r2,0xca26
    andn r2,r1,r2
    li r5,0x0001
    sub r5,r2,r5
    li r6,0x4000
    bnz r5,fail7
    lli r5,'.'
    sw r5,(r6)
    b next7
fail7:
    lli r5,'A'
    sw r5,(r6)
next7:
    li r5,0x0001
    li r4,0x1234
    andn r4,r5,r4
    li r5,0x0001
    sub r5,r4,r5
    li r6,0x4000
    bnz r5,fail8
    lli r5,'.'
    sw r5,(r6)
    b next8
fail8:
    lli r5,'A'
    sw r5,(r6)
next8:
    li r1,0x0001
    li r2,0x7fff
    andn r3,r1,r2
    li r5,0x0000
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail9
    lli r5,'.'
    sw r5,(r6)
    b next9
fail9:
    lli r5,'A'
    sw r5,(r6)
next9:
    li r1,0x5a5a
    li r2,0x18b8
    andn r3,r1,r2
    li r5,0x4242
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail10
    lli r5,'.'
    sw r5,(r6)
    b next10
fail10:
    lli r5,'A'
    sw r5,(r6)
next10:
    li r1,0x7fff
    li r2,0x8000
    andn r1,r1,r2
    li r5,0x7fff
    sub r5,r1,r5
    li r6,0x4000
    bnz r5,fail11
    lli r5,'.'
    sw r5,(r6)
    b next11
fail11:
    lli r5,'A'
    sw r5,(r6)
next11:
    li r1,0x5a5a
    li r2,0x00ff
    xor r3,r1,r2
    li r5,0x5aa5
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail12
    lli r5,'.'
    sw r5,(r6)
    b next12
fail12:
    lli r5,'X'
    sw r5,(r6)
next12:
    li r1,0x8000
    li r2,0xff00
    xor r1,r1,r2
    li r5,0x7f00
    sub r5,r1,r5
    li r6,0x4000
    bnz r5,fail13
    lli r5,'.'
    sw r5,(r6)
    b next13
fail13:
    lli r5,'X'
    sw r5,(r6)
next13:
    li r1,0x4d3c
    li r2,0x8000
    xor r2,r1,r2
    li r5,0xcd3c
    sub r5,r2,r5
    li r6,0x4000
    bnz r5,fail14
    lli r5,'.'
    sw r5,(r6)
    b next14
fail14:
    lli r5,'X'
    sw r5,(r6)
next14:
    li r5,0xffff
    li r4,0x0001
    xor r4,r5,r4
    li r5,0xfffe
    sub r5,r4,r5
    li r6,0x4000
    bnz r5,fail15
    lli r5,'.'
    sw r5,(r6)
    b next15
fail15:
    lli r5,'X'
    sw r5,(r6)
next15:
    li r1,0xff00
    li r2,0x3031
    xor r3,r1,r2
    li r5,0xcf31
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail16
    lli r5,'.'
    sw r5,(r6)
    b next16
fail16:
    lli r5,'X'
    sw r5,(r6)
next16:
    li r1,0x18b8
    li r2,0xa5cd
    xor r3,r1,r2
    li r5,0xbd75
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail17
    lli r5,'.'
    sw r5,(r6)
    b next17
fail17:
    lli r5,'X'
    sw r5,(r6)
next17:
    li r1,0x2516
    li r2,0x2516
    xor r1,r1,r2
    li r5,0x0000
    sub r5,r1,r5
    li r6,0x4000
    bnz r5,fail18
    lli r5,'.'
    sw r5,(r6)
    b next18
fail18:
    lli r5,'X'
    sw r5,(r6)
next18:
    li r1,0x4d3c
    li r2,0x5a5a
    xor r2,r1,r2
    li r5,0x1766
    sub r5,r2,r5
    li r6,0x4000
    bnz r5,fail19
    lli r5,'.'
    sw r5,(r6)
    b next19
fail19:
    lli r5,'X'
    sw r5,(r6)
next19:
    li r5,0x1234
    li r4,0x00ff
    xor r4,r5,r4
    li r5,0x12cb
    sub r5,r4,r5
    li r6,0x4000
    bnz r5,fail20
    lli r5,'.'
    sw r5,(r6)
    b next20
fail20:
    lli r5,'X'
    sw r5,(r6)
next20:
    li r1,0x1234
    li r2,0xffff
    xor r3,r1,r2
    li r5,0xedcb
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail21
    lli r5,'.'
    sw r5,(r6)
    b next21
fail21:
    lli r5,'X'
    sw r5,(r6)
next21:
    li r1,0x5a5a
    li r2,0x3031
    xor r3,r1,r2
    li r5,0x6a6b
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail22
    lli r5,'.'
    sw r5,(r6)
    b next22
fail22:
    lli r5,'X'
    sw r5,(r6)
next22:
    li r1,0xa5cd
    li r2,0x2516
    xor r1,r1,r2
    li r5,0x80db
    sub r5,r1,r5
    li r6,0x4000
    bnz r5,fail23
    lli r5,'.'
    sw r5,(r6)
    b next23
fail23:
    lli r5,'X'
    sw r5,(r6)
next23:
    li r1,0x5a5a
    li r2,0xffff
    add r3,r1,r2
    li r5,0x5a59
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail24
    lli r5,'.'
    sw r5,(r6)
    b next24
fail24:
    lli r5,'A'
    sw r5,(r6)
next24:
    li r1,0x8000
    li r2,0x18b8
    add r1,r1,r2
    li r5,0x98b8
    sub r5,r1,r5
    li r6,0x4000
    bnz r5,fail25
    lli r5,'.'
    sw r5,(r6)
    b next25
fail25:
    lli r5,'A'
    sw r5,(r6)
next25:
    li r1,0x00ff
    li r2,0xa5cd
    add r2,r1,r2
    li r5,0xa6cc
    sub r5,r2,r5
    li r6,0x4000
    bnz r5,fail26
    lli r5,'.'
    sw r5,(r6)
    b next26
fail26:
    lli r5,'A'
    sw r5,(r6)
next26:
    li r5,0x7fff
    li r4,0x3031
    add r4,r5,r4
    li r5,0xb030
    sub r5,r4,r5
    li r6,0x4000
    bnz r5,fail27
    lli r5,'.'
    sw r5,(r6)
    b next27
fail27:
    lli r5,'A'
    sw r5,(r6)
next27:
    li r1,0x18b8
    li r2,0x0001
    sub r3,r1,r2
    li r5,0x18b7
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail28
    lli r5,'.'
    sw r5,(r6)
    b next28
fail28:
    lli r5,'S'
    sw r5,(r6)
next28:
    li r1,0xffff
    li r2,0xa5cd
    sub r1,r1,r2
    li r5,0x5a32
    sub r5,r1,r5
    li r6,0x4000
    bnz r5,fail29
    lli r5,'.'
    sw r5,(r6)
    b next29
fail29:
    lli r5,'S'
    sw r5,(r6)
next29:
    li r1,0xa5cd
    li r2,0x4d3c
    sub r2,r1,r2
    li r5,0x5891
    sub r5,r2,r5
    li r6,0x4000
    bnz r5,fail30
    lli r5,'.'
    sw r5,(r6)
    b next30
fail30:
    lli r5,'S'
    sw r5,(r6)
next30:
    li r5,0x3031
    li r4,0x2516
    sub r4,r5,r4
    li r5,0x0b1b
    sub r5,r4,r5
    li r6,0x4000
    bnz r5,fail31
    lli r5,'.'
    sw r5,(r6)
    b next31
fail31:
    lli r5,'S'
    sw r5,(r6)
next31:
    li r1,0xffff
    li r2,0xffff
    mul r3,r1,r2
    li r5,0x0001
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail32
    lli r5,'.'
    sw r5,(r6)
    b next32
fail32:
    lli r5,'M'
    sw r5,(r6)
next32:
    li r1,0xa5a5
    li r2,0x3031
    mul r1,r1,r2
    li r5,0xa495
    sub r5,r1,r5
    li r6,0x4000
    bnz r5,fail33
    lli r5,'.'
    sw r5,(r6)
    b next33
fail33:
    lli r5,'M'
    sw r5,(r6)
next33:
    li r1,0xffff
    li r2,0x0001
    mul r2,r1,r2
    li r5,0xffff
    sub r5,r2,r5
    li r6,0x4000
    bnz r5,fail34
    lli r5,'.'
    sw r5,(r6)
    b next34
fail34:
    lli r5,'M'
    sw r5,(r6)
next34:
    li r5,0x5a5a
    li r4,0x2516
    mul r4,r5,r4
    li r5,0xc5bc
    sub r5,r4,r5
    li r6,0x4000
    bnz r5,fail35
    lli r5,'.'
    sw r5,(r6)
    b next35
fail35:
    lli r5,'M'
    sw r5,(r6)
next35:
    li r1,0x5a5a
    li r2,0xca26
    div r3,r1,r2
    li r5,0xffff
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail36
    lli r5,'.'
    sw r5,(r6)
    b next36
fail36:
    lli r5,'D'
    sw r5,(r6)
next36:
    li r1,0x4d3c
    li r2,0x0003
    div r1,r1,r2
    li r5,0x19be
    sub r5,r1,r5
    li r6,0x4000
    bnz r5,fail37
    lli r5,'.'
    sw r5,(r6)
    b next37
fail37:
    lli r5,'D'
    sw r5,(r6)
next37:
    li r1,0x2516
    li r2,0x4d3c
    div r2,r1,r2
    li r5,0x0000
    sub r5,r2,r5
    li r6,0x4000
    bnz r5,fail38
    lli r5,'.'
    sw r5,(r6)
    b next38
fail38:
    lli r5,'D'
    sw r5,(r6)
next38:
    li r5,0x00ff
    li r4,0x8000
    div r4,r5,r4
    li r5,0x0000
    sub r5,r4,r5
    li r6,0x4000
    bnz r5,fail39
    lli r5,'.'
    sw r5,(r6)
    b next39
fail39:
    lli r5,'D'
    sw r5,(r6)
next39:
    li r1,0x3031
    li r2,0x0001
    rem r3,r1,r2
    li r5,0x0000
    sub r5,r3,r5
    li r6,0x4000
    bnz r5,fail40
    lli r5,'.'
    sw r5,(r6)
    b next40
fail40:
    lli r5,'R'
    sw r5,(r6)
next40:
    li r1,0xff00
    li r2,0x5a5a
    rem r1,r1,r2
    li r5,0xff00
    sub r5,r1,r5
    li r6,0x4000
    bnz r5,fail41
    lli r5,'.'
    sw r5,(r6)
    b next41
fail41:
    lli r5,'R'
    sw r5,(r6)
next41:
    li r1,0x7fff
    li r2,0x1234
    rem r2,r1,r2
    li r5,0x0093
    sub r5,r2,r5
    li r6,0x4000
    bnz r5,fail42
    lli r5,'.'
    sw r5,(r6)
    b next42
fail42:
    lli r5,'R'
    sw r5,(r6)
next42:
    li r5,0xca26
    li r4,0xca26
    rem r4,r5,r4
    li r5,0x0000
    sub r5,r4,r5
    li r6,0x4000
    bnz r5,fail43
    lli r5,'.'
    sw r5,(r6)
    b next43
fail43:
    lli r5,'R'
    sw r5,(r6)
next43:
    li r1,0x1234
    li r2,0x00ff
    andn r0,r1,r2
    xor r0,r1,r2
    bnz r0,bad0
    lli r3,0x34
    lhi r3,0x12
    li r4,0x1234
    sub r4,r3,r4
    bnz r4,bad0
    lli r5,'Z'
    sw r5,(r6)
    b done
bad0:
    lli r5,'!'
    sw r5,(r6)
done:
    lli r5,10
    sw r5,(r6)
    b done2
done2:
    b done2
