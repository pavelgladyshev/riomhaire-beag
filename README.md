# Ríomhaire Beag (BEAG): a simple 16-bit computer in Logisim

*Ríomhaire beag* is Irish for "small computer". BEAG is a complete 16-bit computer built from
gates, multiplexers, registers and memories in the free
[Logisim-evolution](https://github.com/logisim-evolution/logisim-evolution) circuit simulator,
small enough to fit on one screen. It was designed for teaching: you can write a program in its
13-instruction machine code, load it into the ROM and watch every register and wire change as the
clock ticks.

The computer is explained step by step in the video series
**[Ríomhaire Beag: Build and Program a Simple 16-bit Computer](https://www.youtube.com/playlist?list=PLTZUi9vkv3A8)**
(15 videos, from the COMP20020 Digital Systems module at University College Dublin).

## What is here

| Folder | Contents |
|---|---|
| `circuits/` | The current circuits: `beag_harvard.circ` (separate program ROM, one clock cycle per instruction) and `beag_von_neumann.circ` (one memory for program and data, a fetch cycle and an execute cycle per instruction). Open with Logisim-evolution 5.0.0 or later. |
| `circuits/as-in-videos/` | The versions shown in the videos (Logisim-evolution 3.9.0). Use these to follow the videos screen by screen. |
| `examples/` | The four programs written in the videos, as assembly (`.asm`) and as ROM images (`.mem`). |
| `isa/` | The instruction set with the control signals of every instruction (spreadsheet, as used in the videos on the instruction decoder). |
| `toolchain/` | An assembler, a C compiler and an instruction-level simulator for BEAG, in Python (see `toolchain/README.md`). |

## Getting started

1. Install Java and [Logisim-evolution 5.0.0](https://github.com/logisim-evolution/logisim-evolution/releases).
2. Open `circuits/beag_harvard.circ`.
3. Right-click the `Program_ROM` component, choose **Load Image...** and pick a file from `examples/`,
   for example `ex3_stars.mem`. (In `beag_von_neumann.circ` the program goes into the `ROM`.)
4. Reset the computer with **Ctrl-R** (Command-R on a Mac), then step through the program with
   **Ctrl-T**, which toggles the clock (two presses make one clock cycle), or let the clock run with
   **Ctrl-K**. Five asterisks appear on the display.

Programs can also be run from the command line, with the keyboard and display connected to the
terminal:

```bash
java -jar logisim-evolution-5.0.0-all.jar -t tty --load examples/ex3_stars.mem Program_ROM -- circuits/beag_harvard.circ
```

(For `beag_von_neumann.circ` leave out `Program_ROM`. The program never stops by itself, so end it with
Ctrl-C. In this mode the terminal sends each line to the keyboard when you press Enter. With
`-t tty,raw` every key goes to the computer at once, without echo; Enter then sends a carriage
return (0x0D), so end a line for `ex4_backwards` with Ctrl-J, which sends 0x0A.)

## The example programs

| File | Video | What it does |
|---|---|---|
| `ex1_add` | [First Machine-Code Program](https://www.youtube.com/watch?v=Tw9SecMni0Y&list=PLTZUi9vkv3A8) | loads 3 and 6 into registers and adds them (r3 = 9) |
| `ex2_hi` | [Printing 'Hi' on a Memory-Mapped Display](https://www.youtube.com/watch?v=JU-Z4u26v5A&list=PLTZUi9vkv3A8) | prints `Hi` |
| `ex3_stars` | [A Loop in Assembly](https://www.youtube.com/watch?v=-uGDVfDr5CY&list=PLTZUi9vkv3A8) | prints `*****` in a loop |
| `ex4_backwards` | [If-Then-Else, Comparisons and Arrays in RAM](https://www.youtube.com/watch?v=FKuRsnnltmI&list=PLTZUi9vkv3A8) | reads a line from the keyboard and prints it backwards |

The machine code is exactly the code worked out by hand in the videos; `ex1_add` and `ex2_hi` have
one extra instruction at the end (`bz r0,0`) that stops the program, so that it does not run on
through the empty ROM. To assemble your own program: `python3 toolchain/beagasm.py prog.asm`.

## The instruction set

Eight 16-bit registers, `r0` to `r7`; `r0` always reads 0. Every instruction is one 16-bit word of
four hexadecimal digits: the opcode, then three 4-bit fields.

| Instruction | Meaning | Encoding |
|---|---|---|
| `add rd,rx,ry` | rd ← rx + ry | `0 rd rx ry` |
| `sub rd,rx,ry` | rd ← rx − ry | `1 rd rx ry` |
| `mul rd,rx,ry` | rd ← rx × ry | `2 rd rx ry` |
| `div rd,rx,ry` | rd ← rx ÷ ry | `3 rd rx ry` |
| `rem rd,rx,ry` | rd ← remainder of rx ÷ ry | `7 rd rx ry` |
| `jalr rd,rx,ry` | rd ← PC + 1, PC ← rx + ry (subroutine call and return) | `4 rd rx ry` |
| `sw ry,(rx)` | memory[rx] ← ry | `5 0 rx ry` |
| `lw rd,(rx)` | rd ← memory[rx] | `6 rd rx 0` |
| `lhi rd,imm8` | top 8 bits of rd ← imm8 | `8 rd imm8` |
| `lli rd,imm8` | rd ← imm8, sign-extended | `9 rd imm8` |
| `bnz rx,offset` | if rx ≠ 0: PC ← PC + offset | `D rx offset` |
| `bz rx,offset` | if rx = 0: PC ← PC + offset | `E rx offset` |
| `bltz rx,offset` | if rx < 0: PC ← PC + offset | `F rx offset` |

Branch offsets are signed 8-bit numbers counted from the branch instruction itself, so
`bz r0,0` is an endless loop on the spot (used to end a program) and `bnz r2,-2` jumps two
instructions back. Opcodes A, B and C are unused, room for instructions of your own.

## The memory map

| Address | Device |
|---|---|
| `0x0000` – `0x1FFF` | ROM: the program (the circuits fit 4K words, `0x0000`–`0x0FFF`) |
| `0x2000` – `0x3FFF` | RAM (the circuits fit 4K words, `0x2000`–`0x2FFF`) |
| `0x4000` | display: storing an ASCII code here prints the character |
| `0x4001` | keyboard status: non-zero when a key is waiting |
| `0x4002` | keyboard data: the ASCII code of the key (reading it takes the key) |

The display and keyboard are *memory-mapped*: the program reaches them with the same `lw` and `sw`
instructions it uses for the RAM.

## Author

Pavel Gladyshev, School of Computer Science, University College Dublin.

## Licence

The circuits, example programs, instruction-set spreadsheet and documentation are licensed under
[Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/):
you may share and adapt them, including commercially, as long as you credit the author.
The toolchain in `toolchain/` is under the [MIT licence](toolchain/LICENSE). See `LICENSE` for details.
