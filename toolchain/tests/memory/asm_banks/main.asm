; copies the message in ROM bank table into RAM bank screen, then prints it from there
    li   r1,message        ; in the table ROM
    li   r2,buffer         ; in the screen RAM
    lli  r3,1
copy:
    lw   r4,(r1)
    sw   r4,(r2)
    add  r1,r1,r3
    add  r2,r2,r3
    bnz  r4,copy
    li   r1,0x4000
    li   r2,buffer
print:
    lw   r4,(r2)
    bz   r4,done
    sw   r4,(r1)
    add  r2,r2,r3
    b    print
done:
    b    done

#bank table
message: #d16 "from ROM via RAM", 10, 0

#bank screen
buffer: #res 32
