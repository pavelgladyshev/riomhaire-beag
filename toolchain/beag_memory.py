"""The memory map of a BEAG computer: where its ROM, RAM and devices are.

beagasm, beagcc and beagsim read it from a memory map file, given with --memory FILE or found
as beag_memory.txt in the folder of the (first) source file; without one they use the map of the
course's circuits (DEFAULT_TEXT). One statement per line, # starts a comment:

    rom  program  0x0000  4K        the program; execution starts at address 0 after Reset
    ram  data     0x2000-0x2FFF     variables (also the heap and, by default, the stack)
    rom  NAME  START  SIZE          more ROM: '#bank NAME' in assembly puts things there
    ram  NAME  START  SIZE          more RAM (for example video memory)
    display   ADDRESS               a write prints a character
    keyboard  ADDRESS               reads 1 when a key is waiting; ADDRESS+1 reads the key code
    device    NAME  ADDRESS [SIZE]  your own input/output: the simulator reads 0, logs writes
    stack     ADDRESS               the stack grows down from ADDRESS-1 (default: end of data)
    organisation  harvard | vonneumann

A bank is START SIZE or START-END (END included). Numbers are decimal, 0x hexadecimal or 0b
binary; a size may end in K (1024 words). The banks 'program' (ROM) and 'data' (RAM) are needed.
"""

import os
import re

DEFAULT_FILE = 'beag_memory.txt'

DEFAULT_TEXT = """\
# The memory of the BEAG computers of the course: beag_harvard.circ, beag_von_neumann.circ and
# the Assignment 4 BEAG. Copy this file next to your program as beag_memory.txt and change it
# to describe your own circuit.
rom  program  0x0000  4K       # Program_ROM: 12 address bits
ram  data     0x2000  4K       # Data_RAM: addresses 0x2000-0x2FFF
display   0x4000
keyboard  0x4001               # ready flag; the key code is at 0x4002
organisation  harvard          # beag_von_neumann.circ and the A4 BEAG: vonneumann
"""


class MemoryMapError(Exception):
    def __init__(self, msg, file=None, line=None):
        super().__init__(msg)
        self.msg, self.file, self.line = msg, file, line

    def __str__(self):
        if self.file is None:
            return f'error: {self.msg}'
        return f'{self.file}:{self.line}: error: {self.msg}'


class Bank:
    def __init__(self, kind, name, start, size):
        self.kind, self.name, self.start, self.size = kind, name, start, size

    @property
    def end(self):
        """The first address after the bank."""
        return self.start + self.size

    def __contains__(self, addr):
        return self.start <= addr < self.end

    def __repr__(self):
        return f'{self.kind} {self.name} 0x{self.start:04x}-0x{self.end - 1:04x}'


class MemoryMap:
    def __init__(self):
        self.banks = {}                  # name -> Bank, in the order of the file
        self.display = None
        self.keyboard = None
        self.devices = {}                # name -> (start, size)
        self.stack = None
        self.organisation = 'harvard'
        self.file = None                 # where it came from (None: the built-in map)

    # -- reading ------------------------------------------------------------------------------

    @classmethod
    def parse(cls, text, filename=None):
        m = cls()
        m.file = filename
        where = filename or '(the built-in memory map)'
        for n, raw in enumerate(text.splitlines(), 1):
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            words = line.replace(',', ' ').split()
            key = words[0].lower()

            def fail(msg):
                raise MemoryMapError(msg, where, n)

            def num(s, what):
                return parse_number(s, what, fail)

            if key in ('rom', 'ram'):
                if len(words) not in (3, 4):
                    fail(f'write: {key} NAME START SIZE  or  {key} NAME START-END')
                name = words[1]
                if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
                    fail(f'{name!r} is not a bank name')
                if name in m.banks:
                    fail(f'the bank {name!r} is described twice')
                if len(words) == 3:
                    if '-' not in words[2]:
                        fail(f'write: {key} NAME START SIZE  or  {key} NAME START-END')
                    a, b = words[2].split('-', 1)
                    start, last = num(a, 'start'), num(b, 'end')
                    if last < start:
                        fail('the end of a bank must not come before its start')
                    size = last - start + 1
                else:
                    start, size = num(words[2], 'start'), num(words[3], 'size')
                if size <= 0:
                    fail('a bank needs at least one word')
                if start + size > 0x10000:
                    fail(f'the bank ends at 0x{start + size - 1:x}, beyond the last address 0xFFFF')
                m.banks[name] = Bank(key, name, start, size)
            elif key == 'display':
                if len(words) != 2:
                    fail('write: display ADDRESS')
                m.display = num(words[1], 'address')
            elif key == 'keyboard':
                if len(words) != 2:
                    fail('write: keyboard ADDRESS  (the ready flag; the key code is at ADDRESS+1)')
                m.keyboard = num(words[1], 'address')
            elif key == 'device':
                if len(words) not in (3, 4):
                    fail('write: device NAME ADDRESS [SIZE]')
                size = num(words[3], 'size') if len(words) == 4 else 1
                m.devices[words[1]] = (num(words[2], 'address'), size)
            elif key == 'stack':
                if len(words) != 2:
                    fail('write: stack ADDRESS  (the stack grows down from ADDRESS-1)')
                m.stack = num(words[1], 'address')
            elif key in ('organisation', 'organization'):
                if len(words) != 2:
                    fail('write: organisation harvard  or  organisation vonneumann')
                o = words[1].lower().replace('-', '').replace('_', '')
                if o not in ('harvard', 'vonneumann'):
                    fail('the organisation is harvard or vonneumann')
                m.organisation = o
            else:
                fail(f'unknown statement {words[0]!r} (rom, ram, display, keyboard, device, stack, organisation)')
        m.check(where)
        return m

    @classmethod
    def default(cls):
        return cls.parse(DEFAULT_TEXT)

    @classmethod
    def load(cls, path):
        try:
            with open(path, encoding='utf-8') as f:
                return cls.parse(f.read(), path)
        except OSError as e:
            raise MemoryMapError(f'cannot read the memory map {path}: {e.strerror}')

    @classmethod
    def find(cls, explicit=None, near=None):
        """The map given with --memory, else beag_memory.txt next to the file 'near', else the default."""
        if explicit:
            return cls.load(explicit)
        if near:
            p = os.path.join(os.path.dirname(os.path.abspath(near)), DEFAULT_FILE)
            if os.path.isfile(p):
                return cls.load(p)
        return cls.default()

    # -- checks -------------------------------------------------------------------------------

    def check(self, where):
        prog = self.banks.get('program')
        data = self.banks.get('data')
        if prog is None or prog.kind != 'rom':
            raise MemoryMapError(f"{where}: a 'rom program START SIZE' line is needed (the program's ROM)")
        if data is None or data.kind != 'ram':
            raise MemoryMapError(f"{where}: a 'ram data START SIZE' line is needed (the variables' RAM)")
        if self.organisation == 'harvard' and prog.start != 0:
            raise MemoryMapError(f'{where}: the program ROM of a Harvard BEAG starts at address 0 '
                                 f'(the PC addresses it directly)')
        if self.organisation == 'vonneumann' and 0 not in prog:
            raise MemoryMapError(f'{where}: execution starts at address 0 after Reset, so the program ROM '
                                 f'must include address 0')
        regions = [(b.start, b.end, f'{b.kind} {b.name}') for b in self.banks.values()]
        if self.display is not None:
            regions.append((self.display, self.display + 1, 'the display'))
        if self.keyboard is not None:
            regions.append((self.keyboard, self.keyboard + 2, 'the keyboard'))
        for name, (a, n) in self.devices.items():
            regions.append((a, a + n, f'device {name}'))
        for a, b, what in regions:
            if not (0 <= a and b <= 0x10000):
                raise MemoryMapError(f'{where}: {what} is outside the addresses 0x0000-0xFFFF')
        if self.organisation == 'harvard':
            # the program ROM is not in the data address space of a Harvard BEAG
            regions = [r for r in regions if r[2] != 'rom program']
        regions.sort()
        for (a1, b1, w1), (a2, b2, w2) in zip(regions, regions[1:]):
            if a2 < b1:
                raise MemoryMapError(f'{where}: {w1} and {w2} overlap (at 0x{a2:04x})')
        if self.stack is not None:
            ok = any(b.kind == 'ram' and b.start < self.stack <= b.end for b in self.banks.values())
            if not ok:
                raise MemoryMapError(f'{where}: the stack at 0x{self.stack:04x} is not in a RAM bank '
                                     f'(the first word pushed goes to 0x{(self.stack - 1) & 0xFFFF:04x})')

    # -- questions ----------------------------------------------------------------------------

    @property
    def program(self):
        return self.banks['program']

    @property
    def data(self):
        return self.banks['data']

    @property
    def stack_top(self):
        """The initial stack pointer (the first push writes stack_top - 1)."""
        return self.stack if self.stack is not None else self.data.end

    @property
    def stack_in_data(self):
        return self.data.start < self.stack_top <= self.data.end

    @property
    def vonneumann(self):
        return self.organisation == 'vonneumann'

    def rodata_bank(self):
        """The ROM bank that lw can read, for constant data: the program ROM of a von Neumann BEAG,
        or another ROM bank of a Harvard BEAG; None when there is none (the plain Harvard BEAG)."""
        if self.vonneumann:
            return 'program'
        for name, b in self.banks.items():
            if b.kind == 'rom' and name != 'program':
                return name
        return None

    def as_vonneumann(self):
        """This map with organisation vonneumann (beagcc --vn)."""
        import copy
        m = copy.copy(self)
        m.organisation = 'vonneumann'
        m.check(m.file or '(the memory map)')
        return m

    def bank_ranges(self):
        """name -> (first address, first address after) of every bank, for the assembler."""
        return {name: (b.start, b.end) for name, b in self.banks.items()}

    def defines(self):
        """Macros for the C preprocessor (beag.h uses them)."""
        d = [f'__BEAG_RAM_START__=0x{self.data.start:04x}', f'__BEAG_RAM_END__=0x{self.data.end:x}',
             f'__BEAG_ROM_SIZE__={self.program.size}']
        if self.display is not None:
            d.append(f'__BEAG_DISPLAY__=0x{self.display:04x}')
        if self.keyboard is not None:
            d.append(f'__BEAG_KEYBOARD__=0x{self.keyboard:04x}')
        if self.vonneumann:
            d.append('__BEAG_VON_NEUMANN__=1')
        for name, (a, n) in self.devices.items():
            d.append(f'__BEAG_DEVICE_{name.upper()}__=0x{a:04x}')
        return d

    def describe(self):
        """One line per item, for messages and maps."""
        out = [repr(b) for b in self.banks.values()]
        if self.display is not None:
            out.append(f'display 0x{self.display:04x}')
        if self.keyboard is not None:
            out.append(f'keyboard 0x{self.keyboard:04x} (key code 0x{self.keyboard + 1:04x})')
        for name, (a, n) in self.devices.items():
            out.append(f'device {name} 0x{a:04x}' + (f'-0x{a + n - 1:04x}' if n > 1 else ''))
        out.append(f'stack from 0x{(self.stack_top - 1) & 0xFFFF:04x} down; {self.organisation}')
        return out


def parse_number(s, what, fail):
    t = s.lower().replace('_', '')
    mult = 1
    if t.endswith('k'):
        mult, t = 1024, t[:-1]
    try:
        if t.startswith('0x'):
            v = int(t[2:], 16)
        elif t.startswith('0b'):
            v = int(t[2:], 2)
        else:
            v = int(t, 10)
    except ValueError:
        fail(f'{s!r} is not a number ({what})')
    return v * mult
