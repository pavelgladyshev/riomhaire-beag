# BEAG toolchain: assembler, C compiler and simulator

Tools for the BEAG computer (`../circuits/beag_harvard.circ` and
`../circuits/beag_von_neumann.circ`). They need only Python 3 (3.9 or later, no extra packages).

| File | What it does |
|---|---|
| `beagasm.py` | assembler and linker: `.asm` files → Logisim ROM image (`.mem`), listing, memory map |
| `beagcc.py` | C compiler: `.c` (and `.asm`) files → `.mem`, with the assembly, listing and map; `--run` runs the result in the simulator |
| `beagsim.py` | instruction-level simulator of the two Week 10 circuits (fast, for testing) |
| `cc_lex.py`, `cc_parse.py`, `cc_gen.py` | the compiler's preprocessor, parser and code generator |
| `beag_memory.py` | reads the memory map file (`beag_memory.txt`): where the ROM, RAM and devices are |
| `include/`, `lib/` | the C library: headers and sources (compiled together with every program) |
| `examples/` | example programs |
| `tests/` | tests: `run_tests.py`, `fuzz.py` |

## Installing

There is nothing to build or install apart from Python:

1. Check that Python 3.9 or later is there: `python3 --version` (macOS and Linux) or `py --version` (Windows). If
   not, install it from [python.org](https://www.python.org/downloads/) (on Windows, tick *Add python.exe to PATH*).
2. Copy the whole `BEAG_toolchain` folder anywhere. Keep its files together: `beagcc.py` needs the `cc_*.py` files,
   `beagasm.py`, `beagsim.py`, `include/` and `lib/` next to it.
3. Run the tools with Python from that folder (on Windows write `py` instead of `python3`):

```bash
python3 beagcc.py examples/hello.c --run
```

   From another folder, give the path: `python3 ~/BEAG_toolchain/beagcc.py prog.c`. To check the installation,
   `python3 tests/run_tests.py` runs the tests (the expected outputs of some of them were made on macOS, but they
   are stored in the folder, so the tests need no C compiler).

## Quick start

```bash
python3 beagcc.py examples/hello.c              # writes examples/hello.asm and examples/hello.mem
python3 beagcc.py examples/hello.c --run        # ... and runs it in the simulator
python3 beagcc.py examples/calc.c --run -i '2*(3+4)\n\n'   # keyboard input for the program
```

Run it in Logisim: open `beag_harvard.circ`, right-click `Program_ROM` → *Load Image...* → choose
the `.mem` file, reset (Ctrl-R) and run the clock (Ctrl-K). Or from the command line:

```bash
java -jar logisim-evolution-5.0.0-all.jar -t tty --load examples/hello.mem Program_ROM -- ../circuits/beag_harvard.circ
```

(For `beag_von_neumann.circ` leave out `Program_ROM`: its ROM has no label.) A BEAG program never
ends by itself: at the end it loops on the spot (`b rt_halt`), so stop Logisim with Ctrl-C. In the
tty mode, Logisim's keyboard reads what is typed on the terminal (or piped into it).

## Your own computer: the memory map (`beag_memory.txt`)

The tools assume the memory of the course's BEAG (ROM 0x0000–0x0FFF, RAM 0x2000–0x2FFF, display
0x4000, keyboard 0x4001–0x4002). When you change the circuit – more ROM or RAM, devices of your own,
a different address for the display – describe it in a file `beag_memory.txt` next to your
program: beagasm, beagcc and beagsim find it there (or give it with `--memory FILE`) and say
that they use it. `examples/beag_memory.txt` is a commented copy of the default to start from.

```
rom  program  0x0000  8K       # the program's ROM; execution starts at 0 after Reset
ram  data     0x8000-0xBFFF    # variables, heap and (by default) the stack
ram  screen   0xC000  2K       # more RAM: '#bank screen' in assembly, a pointer in C
rom  table    0x1000  0x100    # more ROM: '#bank table'; its image is written to prog.table.mem
display   0xF000
keyboard  0xF001               # the key code is then at 0xF002
device    leds  0xF010         # your own I/O: in C, (*(volatile int *)__BEAG_DEVICE_LEDS__)
stack     0xC000               # the stack grows down from 0xBFFF (default: the end of data)
organisation  vonneumann       # or harvard
```

* A bank is `START SIZE` or `START-END`; numbers are decimal or 0x hexadecimal, and a size may end
  in K (1024 words). `program` (ROM) and `data` (RAM) must be there; other banks are optional.
* The assembler places `#bank` contents in the bank of that name and reports a bank that
  overflows; the listing and the memory map show every bank.
* The compiler puts the global variables in `data`, starts the stack at `stack` (or at the end of
  `data`) and lets `malloc` use the rest of `data`. When the map has a ROM that `lw` can read –
  the program ROM of a von Neumann BEAG, or another ROM bank – string literals, `const` data
  and the initial values of the variables go there (see *Memory and size*). `beag.h` takes the addresses
  of the display and the keyboard from the map; without a keyboard `getchar()` returns EOF
  (−1), without a display `putchar` prints nothing.
* The simulator follows the map: `lw` and `sw` reach the banks, the display and the keyboard;
  devices read 0, and `--io` shows what the program writes to them. With `organisation vonneumann`
  instructions are fetched through the same memory (`lw` can read the ROM, code can run in RAM).
* The map is checked: banks and devices must not overlap, a Harvard program ROM starts at 0, the
  stack must be in a RAM bank.

The map must match the circuit: the tools cannot see the circuit, so a wrong map gives a program
that works in beagsim and not in Logisim.

## The assembler: `beagasm.py`

```bash
python3 beagasm.py prog.asm                # writes prog.mem
python3 beagasm.py prog.asm -l prog.lst    # also a listing: address, machine code, source
python3 beagasm.py prog.asm -m prog.map    # also a memory map (- for the screen)
python3 beagasm.py prog.asm -f hex         # one hexadecimal word per line instead
python3 beagasm.py main.asm util.asm       # several files linked into one program
python3 beagasm.py prog.asm --memory my_beag.txt   # for a computer with its own memory map
```

The syntax is that of the course's customasm files: `#include "beag.inc"` is accepted and
ignored (the instruction set is built in), and the course's existing assembly programs assemble
to exactly the bytes customasm gives.

```
; comment                            label:       .local_label:     NAME = expression
add sub mul div rem jalr  rd,rx,ry   lw rd,(rx)   sw ry,(rx)
andn xor  rd,rx,ry  (opcodes A and B, not in the circuits shown in the videos)
lli rd,imm8   lhi rd,imm8            bz bnz bltz  rx,target
li rd,imm16   (= lli + lhi)          b target (= bz r0,target)        nop
jmp target    jz/jnz/jltz rx,target  (as b/bz/bnz/bltz, but jump anywhere: see below)
#bank program | data    #addr expr    #res n    #d16 values or "strings"
.globl name, ...       .extern name, ...       (also written #globl, #extern)
```

* **Branch targets.** A plain number is the offset itself, as in the lectures: `bnz r2,-2` jumps
  two instructions back. Anything with a label (or `$`, the current address) is an address:
  `bnz r2,loop`. A branch reaches −128…+127 words; the assembler says so when a target is too far.
* **Long jumps.** `jmp`, `jz`, `jnz`, `jltz` are a single `b`/`bz`/`bnz`/`bltz` when the target is
  near, and otherwise a longer sequence that jumps with `jalr r0,r7,r0` (so they may change r7).
  The C compiler uses them; in hand-written code, prefer the real instructions.
* **lli is sign-extended.** `lli r1,200` is an error (it would load −56); use `li r1,200`. A bit
  pattern written in hex is accepted (`lli r1,0xC8` loads −56 on purpose).
* Expressions: `+ - * / % & | ^ << >> ~`, parentheses, `'c'` characters, `x[15:8]` bit slices.
* **Several files.** Given several files, the assembler links them: the first file starts at
  address 0 and the others follow it, in the ROM and in the RAM. A file's labels are its own
  (two files may both have a `loop:`) unless the file exports them with `.globl name`; a file uses
  another file's label after `.extern name`. A missing `.extern`, a label exported by two files,
  or an `.extern` nobody exports is reported. A single file needs neither directive.
* The banks are those of the memory map: by default the program bank is 0x0000–0x0FFF and the
  data bank 0x2000–0x2FFF (the ROM and RAM of the circuits have 12 address bits, although the
  lecture's memory map shows 8K of each). `#res` reserves space; initialised data in a bank other
  than program is written to a separate image, `prog.BANK.mem` (nothing loads a RAM image into
  the RAM by itself).

## The C compiler: `beagcc.py`

```bash
python3 beagcc.py prog.c                   # prog.mem, prog.asm, prog.lst, prog.map
python3 beagcc.py prog.c -S                # only prog.asm
python3 beagcc.py main.c util.c -o prog.mem
python3 beagcc.py main.c fast.asm          # C and assembly files in one program
python3 beagcc.py prog.c --run -i 'input\n'
python3 beagcc.py --vn prog.c              # for a von Neumann BEAG (beag_von_neumann.circ, the A4 BEAG)
```

| File | Contents |
|---|---|
| `prog.mem` | the ROM image for Logisim |
| `prog.asm` | the compiled C: every C line appears as a comment above its code, and each function's register variables and stack frame are listed above it |
| `prog.lst` | the listing of the whole program as it is in the ROM: every file (the start-up code, the compiled C, the library and runtime routines, the `.asm` files), each word with its absolute address and machine code; the extra words of `li` and of long jumps are shown disassembled; then the variables in the RAM |
| `prog.map` | the memory map: the address range of each file, every function and variable with its address, size and the file it comes from, the free ROM, and the RAM left for the heap and the stack |

### The C language on BEAG

Most of C89/C99 works: `char`, `short`, `int` and their `unsigned` forms, pointers, arrays
(also 2-D), `struct`, `union`, `enum`, `typedef`, initialisers (also designated ones such as
`{ [3] = 1, .x = 2 }`), function pointers, recursion, variadic functions (`stdarg.h`), `switch`,
`goto`, `static` and global variables, the preprocessor (`#include`, `#define` with arguments,
`#`, `##`, `#if`/`#ifdef`). Things particular to BEAG:

* **Everything is 16 bits.** `int`, `char`, `short` and pointers are all one 16-bit word. Memory
  is addressed in words, so `sizeof(char) == sizeof(int) == 1`, `CHAR_BIT` is 16 and a string
  uses one word per character. `INT_MAX` is 32767: `200 * 200` overflows (to −25536), and so
  does `8!`.
* **Not supported:** `long`, `float`, `double`, bit-fields, compound literals, and passing or
  returning a `struct` by value (pass a pointer instead; assigning structs works).
* `&`, `|`, `^`, `<<` and `>>` by a variable amount, and unsigned `/` and `%`, are done by small
  routines (the circuits in the videos have no such instructions; the compiler does not use
  `andn` and `xor` yet), so they take tens to hundreds of instructions.
  Shifts by a constant, `x & 255` style masks and signed `/` and `%` use the instructions directly.
  Comparisons are exact for all values (`-30000 < 30000` is true even though
  `-30000 - 30000` overflows).
* `main()` takes no arguments. When it returns, the program stops (BEAG loops on the spot).
* `const` works as in C: a `const` object cannot be assigned to (the compiler says so), and
  global or `static` `const` data stays in ROM when the ROM can be read (see below).
* `volatile` works as in C: every read and write of a `volatile` object is made, in order, and
  a `volatile` variable is never kept in a register. Use it for memory-mapped I/O:
  `volatile int *p` is a pointer to volatile data (each `*p` reads the device), `int *volatile p`
  a pointer that is itself volatile. `beag.h` defines the I/O registers this way.
* `asm("...")` puts assembly into the program. It may use r1, r2 and r7; r3–r5 may hold variables.

### The library

| Header | Functions |
|---|---|
| `stdio.h` | `putchar`, `getchar` (waits for a key, does not show it), `puts`, `printf`, `sprintf` |
| `stdlib.h` | `abs`, `atoi`, `rand`, `srand`, `malloc`, `calloc`, `free`, `exit` |
| `string.h` | `strlen`, `strcpy`, `strncpy`, `strcat`, `strcmp`, `strncmp`, `strchr`, `strrchr`, `memset`, `memcpy`, `memmove`, `memcmp` |
| `ctype.h` | `isdigit`, `isalpha`, `isalnum`, `isupper`, `islower`, `isspace`, `isxdigit`, `isprint`, `ispunct`, `toupper`, `tolower` |
| `beag.h` | `BEAG_DISPLAY`, `BEAG_KBD_READY`, `BEAG_KBD_DATA` (the I/O registers), `kbhit()`, `read_line(buf, size)` (with echo and Backspace), `read_int()` |
| also | `stdarg.h`, `stddef.h`, `stdbool.h`, `stdint.h`, `limits.h`, `assert.h` |

`printf` knows `%d %i %u %x %X %o %b %c %s %p %%`, a width, and the flags `-` and `0`.

The library is compiled together with the program, and only the functions the program uses
(directly or indirectly) end up in the ROM: a program using `puts` is about 80 words, one using
`printf` about 680. A program may define its own version of a library function.

### C and assembly together

`beagcc` accepts `.asm` files next to the `.c` files and links them with the compiled C. A C
function or global variable `name` is the label `_name` in assembly; the compiled C exports its
non-`static` functions and variables with `.globl`. An assembly function that C calls:

```
.globl _times10            ; int times10(int x);   declared in the C file
_times10:                  ; x is in r1
    add  r2,r1,r1          ; 2x
    add  r1,r2,r2          ; 4x
    add  r1,r1,r1          ; 8x
    add  r1,r1,r2          ; 10x: the result goes back in r1
    jalr r0,r7,r0          ; return
```

The rules are those of the compiled code (see below): the first argument arrives in r1, the
others on the stack (`[sp]` is the second, `[sp+1]` the third, ...; for a function with `...`
every argument is on the stack); the result goes back in r1; the return address is in r7; the
function may change r1, r2 and r7 but must give back r3, r4, r5 and sp as it found them. To call a
C function from assembly (`.extern _putchar`): put the first argument in r1, push the others,
`li r7,_putchar` and `jalr r7,r7,r0`, then pop them; r3–r5 are kept by the call. A library
function the assembly uses is linked in, and an assembly file may replace one (`.globl _putchar`).
`tests/link/mixed` is a complete example.

### Memory and size

* The ROM holds 4096 words of program. The compiler reports the size; the assembler stops with
  an error when a program does not fit.
* Global variables start at 0x2000; the stack grows down from 0x2FFF. The start-up code sets the
  global variables to 0 and gives the initialised ones their values before `main()` runs.
* Where the constant data goes depends on whether `lw` can read the ROM:
  - **Von Neumann BEAG** (`beagcc --vn`, or `organisation vonneumann` in the memory map; also a
    Harvard BEAG with an extra ROM bank in its data memory): string literals and global or
    `static` `const` data are kept in the ROM, one word each, and never copied. The initial values
    of the other global variables are a table in ROM (`rt_idata`), which one loop copies into RAM
    at start-up. A local array or struct with five or more words of constant initial value is
    copied from a ROM image by a short loop. Writing to a string literal does nothing (it is in
    ROM; in C it is not allowed anyway).
  - **Harvard BEAG** (the default, `beag_harvard.circ`): `lw` cannot read the program ROM, so
    every word of initial data – each character of a string too – is put into RAM by start-up
    code, about three instructions per word. A program built this way also runs on the von
    Neumann BEAG; one built with `--vn` runs only where the ROM can be read.
* `malloc` takes memory between the global variables and the stack.

### How the generated code works

| Register | Use |
|---|---|
| r0 | always 0 |
| r1, r2 | values of expressions; r1 is the first argument and the return value; a call changes them |
| r3, r4, r5 | register variables (each function's most used local variables), or more values; a function that uses them saves and restores them |
| r6 | stack pointer: the last word pushed; the stack grows down from 0x2FFF |
| r7 | return address after `jalr r7,r7,r0`, and scratch for constants and addresses |

A function's frame, from sp upwards: local variables kept in memory, the saved r3–r5, the
return address, then the arguments from the 2nd one on (pushed by the caller; the 1st argument
arrives in r1, except for functions with `...`, which get all their arguments on the stack).
There is no frame pointer: the compiler knows how far sp has moved and addresses everything
from it. BEAG has no "address + offset" addressing, so a variable kept in memory costs three
instructions to reach (`lli r7,offset` / `add r7,r6,r7` / `lw`): that is why the most used ones
live in r3–r5.

## The simulator: `beagsim.py`

```bash
python3 beagsim.py prog.mem                # or prog.asm, or prog.c (compiled first)
python3 beagsim.py prog.mem -i '42\n'      # keyboard input
python3 beagsim.py prog.mem --stdin        # keyboard input typed on this terminal
python3 beagsim.py prog.asm --trace        # every instruction and the registers it changes
python3 beagsim.py prog.mem --regs --stats
python3 beagsim.py prog.mem --vonneumann   # beag_von_neumann.circ: lw can read the ROM, 2 cycles per instruction
python3 beagsim.py prog.c --io             # show what the program writes to the devices of the memory map
```

It does what the circuits do, including the Divider's results (division rounds towards zero,
`x / 0` gives `x` and `x % 0` gives 0, −32768 / −1 gives −32768) and the 12-bit ROM. It stops at
`bz r0,0` (a branch to itself, the usual end of a program), when the program waits for a key and
there is no more input, or after `--max-steps` instructions. An `lw` from an address where there
is nothing (for example the ROM, on the Harvard BEAG) stops it with an error: in Logisim the
register would get an undefined value.

## Tests

```bash
python3 tests/run_tests.py                 # C programs, error messages, assembler
python3 tests/run_tests.py --logisim logisim-evolution-5.0.0-all.jar    # also in Logisim
python3 tests/run_tests.py --logisim JAR --circuit ../circuits/beag_von_neumann.circ
python3 tests/run_tests.py --vn            # everything compiled for a von Neumann BEAG (data in ROM)
python3 tests/run_tests.py --vn --logisim JAR --circuit ../circuits/beag_von_neumann.circ
python3 tests/fuzz.py 200                  # random programs against the computer's C compiler
python3 tests/fuzz.py 200 --vn             # the same, compiled for a von Neumann BEAG
```

* `tests/c/*.c`: programs with the output they must print (`.expected`) and keyboard input
  (`.input`). Most expected outputs come from the computer's own C compiler (with `unsigned` made
  16-bit by `tests/host_prelude.h`, see `run_tests.py --host`); `wrap16.c` checks the 16-bit
  behaviour itself, with hand-written expectations.
* `tests/errors/*.c`: programs that must not compile, with the message expected.
* `tests/link/`: programs made of several files (C and assembly), linked by beagcc.
* `tests/memory/`: programs for computers with their own memory maps (more RAM and ROM, the stack
  in its own bank, no keyboard, extra banks in assembly); `tests/memory_errors/`: maps that must
  be refused.
* `tests/asm/isa_edge.asm`: the instruction set's edge cases (division signs, divide by zero,
  overflow, `lhi`, `jalr`), whose output was checked on both Logisim circuits.
* `tests/fuzz.py`: random programs full of signed and unsigned arithmetic, comparisons, shifts,
  bitwise operators, calls and arrays, compiled by beagcc and by the computer's C compiler with
  every result cut to 16 bits; the outputs must agree.

Checked on 26 October 2026: all 53 tests pass in beagsim, both as they are (Harvard) and with
`--vn` (data in ROM). The 16 C test programs give the same output in Logisim-evolution 5.0.0 on
`beag_harvard.circ` (Harvard build) and, built with `--vn`, on `beag_von_neumann.circ` and the
Assignment 4 BEAG. The random-program test agreed with the computer's C compiler on about 1000
programs, 150 of them built with `--vn` (except a few too big for the ROM). The memory-map tests run
in beagsim only: they describe computers that have no Logisim circuit in the course.

## Notes

* Programs compiled by beagcc run on the Week 10 circuits and on a von Neumann BEAG with `jalr`,
  such as the one built in Assignment 4. A computer built from gates (like your own) simulates
  much more slowly in Logisim than the Week 10 circuits: give it time, or set the clock frequency
  to the maximum.
* The compiler's output is a readable example of how C maps onto the instruction set (stack
  frames, calling convention, loops, `switch`): compare `examples/backwards.c` with the
  hand-written backwards printer of lecture 5.2.
