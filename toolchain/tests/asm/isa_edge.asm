; Edge cases of the BEAG instruction set, printed as 4 hex digits per line.
; Used to check that beagsim agrees with the Logisim circuits: this output was checked on
; beag_harvard.circ and beag_von_neumann.circ with Logisim-evolution 5.0.0 (October 2026).

#bank program
start:
    lli r1,-7               ; -7 / 2 = -3 (fffd)
    lli r2,2
    div r1,r1,r2
    li  r7,printhex
    jalr r7,r7,r0
    lli r1,-7               ; -7 % 2 = -1 (ffff)
    lli r2,2
    rem r1,r1,r2
    li  r7,printhex
    jalr r7,r7,r0
    lli r1,7                ; 7 / -2 = -3 (fffd)
    lli r2,-2
    div r1,r1,r2
    li  r7,printhex
    jalr r7,r7,r0
    lli r1,7                ; 7 % -2 = 1
    lli r2,-2
    rem r1,r1,r2
    li  r7,printhex
    jalr r7,r7,r0
    lli r1,5                ; 5 / 0
    div r1,r1,r0
    li  r7,printhex
    jalr r7,r7,r0
    lli r1,5                ; 5 % 0
    rem r1,r1,r0
    li  r7,printhex
    jalr r7,r7,r0
    li  r1,0x8000           ; -32768 / -1
    lli r2,-1
    div r1,r1,r2
    li  r7,printhex
    jalr r7,r7,r0
    li  r1,0x8000           ; -32768 % -1
    lli r2,-1
    rem r1,r1,r2
    li  r7,printhex
    jalr r7,r7,r0
    li  r1,300              ; 300 * 300 = 90000 = 0x15f90
    mul r1,r1,r1
    li  r7,printhex
    jalr r7,r7,r0
    lli r1,-3               ; -3 * 5 = fff1
    lli r2,5
    mul r1,r1,r2
    li  r7,printhex
    jalr r7,r7,r0
    li  r1,0x8000           ; -32768 - 1 = 7fff
    lli r2,1
    sub r1,r1,r2
    li  r7,printhex
    jalr r7,r7,r0
    lli r1,-1               ; lhi keeps the low byte: 00ff
    lhi r1,0
    li  r7,printhex
    jalr r7,r7,r0
    li  r2,after            ; jalr r1,r2,r0 puts its own address + 1 in r1
    jalr r1,r2,r0
after:
    li  r7,printhex
    jalr r7,r7,r0
    li  r1,after            ; the address of after, for comparison
    li  r7,printhex
    jalr r7,r7,r0
    lli r2,3                ; jalr adds its two registers: jumps to after2 = (after2-3)+3
    li  r3,after2-3
    jalr r0,r3,r2
    lli r1,0x2d             ; skipped
    sw  r1,(r0)
after2:
    li  r1,0x8000           ; bltz on 0x8000 is taken
    bltz r1,neg
    lli r1,0
    b   pneg
neg:
    lli r1,1
pneg:
    li  r7,printhex
    jalr r7,r7,r0
    li  r2,0x2abc           ; RAM wraps? write 0x2abc and read it back
    li  r1,0x1234
    sw  r1,(r2)
    lw  r1,(r2)
    li  r7,printhex
    jalr r7,r7,r0
finish:
    b   finish

; print r1 as 4 hex digits and a newline; return address in r7; changes r1-r7
printhex:
    li  r2,save_r7
    sw  r7,(r2)
    li  r2,0x4000           ; display
    lli r3,16
    li  r4,buf+3            ; digits are produced from the last one
    lli r5,4
ph_loop:
    rem r6,r1,r3            ; -15..15
    bltz r6,ph_neg
    b   ph_ok
ph_neg:
    add r6,r6,r3            ; 0..15
ph_ok:
    sub r1,r1,r6            ; now an exact multiple of 16
    div r1,r1,r3
    lli r7,10
    sub r7,r6,r7
    bltz r7,ph_dec
    lli r6,0x61             ; 'a' + digit - 10
    add r6,r6,r7
    b   ph_store
ph_dec:
    lli r7,0x30             ; '0' + digit
    add r6,r6,r7
ph_store:
    sw  r6,(r4)
    lli r7,1
    sub r4,r4,r7
    sub r5,r5,r7
    bnz r5,ph_loop
    li  r4,buf
    lli r5,4
ph_print:
    lw  r6,(r4)
    sw  r6,(r2)
    lli r7,1
    add r4,r4,r7
    sub r5,r5,r7
    bnz r5,ph_print
    lli r6,10
    sw  r6,(r2)
    li  r7,save_r7
    lw  r7,(r7)
    jalr r0,r7,r0

#bank data
buf:     #res 4
save_r7: #res 1
