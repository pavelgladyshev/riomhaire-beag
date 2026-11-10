#!/usr/bin/env python3
"""beagsim - instruction-level simulator of the BEAG computer (COMP20020, UCD).

Runs a program the way the Week 10 Logisim circuits do, but much faster, so that programs
(and the C compiler) can be tested from the command line.

Usage:
    python3 beagsim.py prog.mem                  # a Logisim ROM image
    python3 beagsim.py prog.asm                  # assembled first with beagasm
    python3 beagsim.py prog.c                    # compiled first with beagcc
    python3 beagsim.py prog.c -i '42\\n'          # text typed on the keyboard
    python3 beagsim.py prog.c --stdin            # keyboard reads this terminal
    python3 beagsim.py prog.asm --trace          # print every instruction

Machine: as described by the memory map (beag_memory.txt next to the program, or --memory FILE);
without one, as in beag_harvard.circ:
    ROM  0x0000-0x0FFF  program (12 address bits, the PC wraps at 0x1000)
    RAM  0x2000-0x2FFF  data
    0x4000 display (write a character code), 0x4001 keyboard ready (1/0), 0x4002 key code
On a von Neumann BEAG (organisation vonneumann in the map, or --vonneumann) the ROM can also be
read with lw, instructions are fetched through the data memory (so code can run from RAM) and
every instruction takes 2 cycles. The devices of the map read 0; --io shows what is written to them.

The run stops at 'bz r0,0' (b to itself, the usual end of a program), when the program waits
for a key and there is no more input, or after --max-steps instructions.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import beagasm  # noqa: E402
from beag_memory import MemoryMap, MemoryMapError  # noqa: E402

IDLE_POLLS = 2000            # empty keyboard polls (with no input left) before giving up


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def read_image(path):
    """Words of a Logisim image file (v2.0 raw or v3.0 hex) or a plain hex list."""
    with open(path) as f:
        lines = f.read().splitlines()
    words = []
    if lines and lines[0].startswith('v3.0'):
        for ln in lines[1:]:
            ln = ln.split('#')[0].strip()
            if not ln:
                continue
            addr, _, rest = ln.partition(':')
            a = int(addr, 16)
            for i, t in enumerate(rest.split()):
                while len(words) <= a + i:
                    words.append(0)
                words[a + i] = int(t, 16)
        return words
    if lines and lines[0].startswith('v2.0'):
        lines = lines[1:]
    for ln in lines:
        for t in ln.split('#')[0].split():
            if '*' in t:
                n, v = t.split('*')
                words.extend([int(v, 16)] * int(n))
            else:
                words.append(int(t, 16))
    return words


class Halt(Exception):
    pass


class Beag:
    def __init__(self, program, vonneumann=None, keyboard='', interactive=False, out=None,
                 warn=None, memory=None, images=None, io_log=False):
        self.mem = memory or MemoryMap.default()
        self.vn = self.mem.vonneumann if vonneumann is None else vonneumann
        prog = self.mem.program
        if len(program) > prog.size:
            raise ValueError(f'the program has {len(program)} words; the ROM holds {prog.size}')
        self.cells = {name: [0] * b.size for name, b in self.mem.banks.items()}
        self.cells['program'][:len(program)] = [w & 0xFFFF for w in program]
        for name, words in (images or {}).items():
            self.cells[name][:len(words)] = [w & 0xFFFF for w in words]
        self.rom = self.cells['program']
        # what lw and sw reach: every bank (the program ROM only in a von Neumann BEAG)
        self.regions = [(b.start, b.end, self.cells[name], b.kind == 'ram', name)
                        for name, b in self.mem.banks.items() if self.vn or name != 'program']
        self.display = self.mem.display
        self.kbd = self.mem.keyboard
        self.devices = [(a, a + n, name) for name, (a, n) in self.mem.devices.items()]
        self.io_log = io_log
        self.r = [0] * 8
        self.pc = 0
        self.keys = [ord(c) & 0x7F for c in keyboard]
        self.interactive = interactive
        self.out = out or sys.stdout
        self.warn_out = warn or sys.stderr
        self.steps = 0
        self.idle_polls = 0
        self.output = []
        self.warned = set()
        self.stop_reason = None
        self.error = False

    # -- memory system ------------------------------------------------------------------------

    def warn(self, key, msg):
        if key not in self.warned and len(self.warned) < 20:
            self.warned.add(key)
            self.warn_out.write(f'beagsim: warning at pc=0x{self.pc:04x}: {msg}\n')

    def device_at(self, addr):
        for a, b, name in self.devices:
            if a <= addr < b:
                return name
        return None

    def peek(self, addr):
        """The word at addr without side effects (for the trace), or None."""
        for start, end, cells, _, _ in self.regions:
            if start <= addr < end:
                return cells[addr - start]
        return None

    def load(self, addr):
        for start, end, cells, _, _ in self.regions:
            if start <= addr < end:
                return cells[addr - start]
        if addr == self.kbd:
            if not self.keys and self.interactive:
                self.read_terminal()
            if self.keys:
                return 1
            self.idle_polls += 1
            if self.idle_polls >= IDLE_POLLS and not self.interactive:
                self.stop_reason = 'waiting for a key, but there is no more input'
                raise Halt()
            return 0
        if self.kbd is not None and addr == self.kbd + 1:
            self.idle_polls = 0
            return self.keys.pop(0) if self.keys else 0
        if addr == self.display:
            return 0
        dev = self.device_at(addr)
        if dev is not None:
            if self.io_log:
                self.warn_out.write(f'beagsim: pc=0x{self.pc:04x}: lw from device {dev} (0x{addr:04x}) reads 0\n')
            return 0
        prog = self.mem.program
        what = ('the program ROM, which the Harvard BEAG cannot read with lw' if addr in prog and not self.vn
                else 'an address with nothing there in the memory map')
        self.stop_reason = (f'error at pc=0x{self.pc:04x}: lw from 0x{addr:04x}, {what} '
                            f'(Logisim would give the register an undefined value)')
        self.error = True
        raise Halt()

    def store(self, addr, value):
        for start, end, cells, writable, name in self.regions:
            if start <= addr < end:
                if writable:
                    cells[addr - start] = value
                else:
                    self.warn(('w', addr), f'sw to 0x{addr:04x}: ROM {name} cannot be written; ignored')
                return
        if addr == self.display:
            self.idle_polls = 0
            ch = chr(value & 0x7F)
            self.output.append(ch)
            self.out.write(ch)
            self.out.flush()
            return
        dev = self.device_at(addr)
        if dev is not None:
            if self.io_log:
                self.warn_out.write(f'beagsim: pc=0x{self.pc:04x}: device {dev} (0x{addr:04x}) <- '
                                    f'0x{value:04x} ({s16(value)})\n')
            return
        if not self.vn and addr in self.mem.program:
            self.warn(('w', addr), f'sw to 0x{addr:04x}: the program ROM cannot be written; ignored')
        else:
            self.warn(('w', addr), f'sw to 0x{addr:04x}: nothing there in the memory map; ignored')

    def read_terminal(self):
        try:
            line = sys.stdin.readline()
        except KeyboardInterrupt:
            line = ''
        if line == '':
            self.stop_reason = 'end of input'
            raise Halt()
        self.keys.extend(ord(c) & 0x7F for c in line)

    def fetch(self):
        if self.vn:
            return self.load(self.pc)
        prog = self.mem.program
        i = self.pc - prog.start
        if not 0 <= i < prog.size:
            i %= prog.size
            self.warn(('pc', 0), f'the PC (0x{self.pc:04x}) is past the end of the program ROM; '
                                 f'the ROM sees address 0x{prog.start + i:04x}')
        return self.rom[i]

    # -- one instruction ----------------------------------------------------------------------

    def step(self):
        w = self.fetch()
        op, d, x, y = w >> 12, (w >> 8) & 7, (w >> 4) & 7, w & 7
        imm = w & 0xFF
        r = self.r
        pc = self.pc
        nxt = (pc + 1) & 0xFFFF
        if op <= 7:
            a, b = r[x], r[y]
            sa, sb = s16(a), s16(b)
            if op == 0:
                v = a + b
            elif op == 1:
                v = a - b
            elif op == 2:
                v = sa * sb
            elif op == 3:                       # Logisim Divider, two's complement
                v = sa if sb == 0 else int(abs(sa) // abs(sb)) * (1 if (sa < 0) == (sb < 0) else -1)
            elif op == 7:
                if sb == 0:
                    v = 0
                else:
                    q = abs(sa) // abs(sb) * (1 if (sa < 0) == (sb < 0) else -1)
                    v = sa - q * sb
            elif op == 4:                       # jalr
                v = nxt
                nxt = (a + b) & 0xFFFF
            elif op == 5:                       # sw
                self.store(a, b)
                d = 0
                v = 0
            else:                               # lw
                v = self.load(a)
            if d:
                r[d] = v & 0xFFFF
        elif op == 8:
            if d:
                r[d] = (imm << 8) | (r[d] & 0xFF)
        elif op == 9:
            if d:
                r[d] = (imm | 0xFF00) if imm & 0x80 else imm
        elif op >= 0xD:
            v = r[d]
            taken = (v != 0) if op == 0xD else (v == 0) if op == 0xE else bool(v & 0x8000)
            if taken:
                if imm == 0:
                    self.stop_reason = 'halted (branch to itself)'
                    raise Halt()
                nxt = (pc + (imm - 256 if imm & 0x80 else imm)) & 0xFFFF
        else:
            self.warn(('op', op), f'opcode 0x{op:X} is unused; it does nothing')
        self.pc = nxt
        self.steps += 1

    def run(self, max_steps, trace=None):
        try:
            if trace:
                while self.steps < max_steps:
                    before = list(self.r)
                    pc = self.pc
                    w = self.peek(pc) if self.vn else self.rom[(pc - self.mem.program.start) % self.mem.program.size]
                    w = 0 if w is None else w
                    self.step()
                    ch = ' '.join(f'r{i}={self.r[i]:04x}' for i in range(8) if self.r[i] != before[i])
                    trace.write(f'{pc:04x}: {w:04x}  {beagasm.disassemble(w, pc):28s} {ch}\n')
            else:
                while self.steps < max_steps:
                    self.step()
            self.stop_reason = f'stopped after {max_steps} instructions (--max-steps)'
            return False
        except Halt:
            return True

    @property
    def cycles(self):
        return self.steps * (2 if self.vn else 1)


def bank_images(a):
    """The contents of the ROM banks other than program (they are part of the circuit)."""
    mem = a.p.memory
    return {name: a.image_words(name) for name, b in mem.banks.items()
            if name != 'program' and b.kind == 'rom' and a.image_words(name)}


def load_program(path, warn=None, memory=None):
    """(program words, Assembler or None) from a .mem/.hex image, an .asm source or a .c source."""
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.asm', '.s'):
        a = beagasm.assemble_file(path, memory)
        return a.image_words('program'), a
    if ext == '.c':
        import beagcc
        asm_text = beagcc.compile_files([path], memory=memory)
        a = beagasm.assemble_text(asm_text, os.path.splitext(path)[0] + '.asm', memory)
        return a.image_words('program'), a
    return read_image(path), None


def unescape_arg(s):
    return s.encode('latin-1', 'backslashreplace').decode('unicode_escape')


def main(argv=None):
    ap = argparse.ArgumentParser(description='Simulator of the BEAG computer (COMP20020).')
    ap.add_argument('program', help='.mem image, .asm source or .c source')
    ap.add_argument('-i', '--input', default='', help=r'keyboard input, e.g. "42\n"')
    ap.add_argument('--input-file', help='keyboard input from a file')
    ap.add_argument('--stdin', action='store_true', help='keyboard input from this terminal, line by line')
    ap.add_argument('--vonneumann', '--vn', action='store_true', help='simulate a von Neumann BEAG '
                                                                       '(beag_von_neumann.circ, the A4 BEAG)')
    ap.add_argument('--memory', help='the memory map of the computer (default: beag_memory.txt next to the '
                                     'program, else the course\'s BEAG)')
    ap.add_argument('--io', action='store_true', help='show what the program writes to (and reads from) '
                                                    'the devices of the memory map')
    ap.add_argument('--max-steps', type=int, default=20_000_000, help='instruction limit (default 20 million)')
    ap.add_argument('--trace', action='store_true', help='print every instruction executed')
    ap.add_argument('--regs', action='store_true', help='print the registers at the end')
    ap.add_argument('--stats', action='store_true', help='print the number of instructions and cycles')
    argv = list(sys.argv[1:] if argv is None else argv)
    for i in range(len(argv) - 1):              # allow -i -15 (argparse takes -15 for an option)
        if argv[i] in ('-i', '--input'):
            argv[i:i + 2] = ['--input=' + argv[i + 1], '']
    args = ap.parse_args([a for a in argv if a != ''])
    try:
        memory = MemoryMap.find(args.memory, near=args.program)
        if args.vonneumann:
            memory = memory.as_vonneumann()
        prog, a = load_program(args.program, memory=memory)
    except (beagasm.AsmError, MemoryMapError) as e:
        print(e, file=sys.stderr)
        return 1
    except Exception as e:                       # compiler errors are printed by beagcc
        if type(e).__name__ == 'CompileError':
            print(e, file=sys.stderr)
            return 1
        raise
    keys = unescape_arg(args.input)
    if args.input_file:
        with open(args.input_file) as f:
            keys += f.read()
    if memory.file:
        print(f'beagsim: the memory map is {memory.file}', file=sys.stderr)
    m = Beag(prog, vonneumann=True if args.vonneumann else None, keyboard=keys, interactive=args.stdin,
             memory=memory, images=bank_images(a) if a else None, io_log=args.io)
    finished = m.run(args.max_steps, trace=sys.stderr if args.trace else None)
    if m.output and m.output[-1] != '\n':
        sys.stdout.write('\n')
    if args.regs:
        print(' '.join(f'r{i}={m.r[i]:04x}({s16(m.r[i])})' for i in range(8)) + f' pc={m.pc:04x}',
              file=sys.stderr)
    if args.stats or not finished or not m.stop_reason.startswith('halted'):
        print(f'beagsim: {m.stop_reason}; {m.steps} instructions, {m.cycles} clock cycles', file=sys.stderr)
    if m.error:
        return 3
    return 0 if finished else 2


if __name__ == '__main__':
    sys.exit(main())
