#!/usr/bin/env python3
"""beagasm - assembler for the BEAG teaching computer (COMP20020, UCD).

Usage:
    python3 beagasm.py prog.asm                 # writes prog.mem (Logisim ROM image)
    python3 beagasm.py prog.asm -l prog.lst     # also writes a listing
    python3 beagasm.py prog.asm -o out.mem -f hex

The source syntax is that of the course's customasm files (beag.inc): the line
'#include "beag.inc"' is accepted and ignored, because the instruction set is built in.
A program that assembles with customasm gives the same .mem file here.

Instructions (16-bit words, registers r0..r7, r0 is always 0):
    add/sub/mul/div/rem/jalr  rd,rx,ry      lw rd,(rx)     sw ry,(rx)
    lli rd,imm8 (sign-extended)   lhi rd,imm8 (replaces bits 15..8)
    bz/bnz/bltz rx,target
Pseudo-instructions:
    li rd,imm16     = lli rd,low byte + lhi rd,high byte (always 2 words)
    b target        = bz r0,target
    nop             = add r0,r0,r0
    jmp target, jz/jnz/jltz rx,target
                    = b/bz/bnz/bltz when the target is in range, otherwise a longer sequence
                      that jumps with jalr through r7 (r7 is overwritten in that case)

Branch targets: a plain number is the offset itself, as in the lectures (bnz r2,-2 jumps two
instructions back); anything with a label or $ in it is an address (bnz r2,loop).

Directives: #include "file", #bank program|data, #addr expr, #res n, #d16 values or "strings",
NAME = expr (constant), label:, .local: (local to the last ordinary label).

The banks (and their addresses) come from the memory map: beag_memory.txt next to the first
source, or --memory FILE; by default program 0x0000-0x0FFF and data 0x2000-0x2FFF.

Several files are linked into one program (the first starts at address 0). A file's labels are
its own unless it exports them with '.globl name'; it uses another file's label after
'.extern name'. -m writes a memory map, -l a listing with the absolute address of every word.
"""

import argparse
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from beag_memory import MemoryMap, MemoryMapError  # noqa: E402

# ----------------------------------------------------------------------------------------------
# The machine

OPCODES = {'add': 0x0, 'sub': 0x1, 'mul': 0x2, 'div': 0x3, 'jalr': 0x4, 'sw': 0x5, 'lw': 0x6,
           'rem': 0x7, 'lhi': 0x8, 'lli': 0x9, 'bnz': 0xD, 'bz': 0xE, 'bltz': 0xF}
R_FORMAT = ('add', 'sub', 'mul', 'div', 'rem', 'jalr')
BRANCHES = ('bz', 'bnz', 'bltz')
LONG_JUMPS = {'jmp': None, 'jz': 'bz', 'jnz': 'bnz', 'jltz': 'bltz'}
PSEUDO = ('li', 'b', 'nop')
MNEMONICS = sorted(set(OPCODES) | set(LONG_JUMPS) | set(PSEUDO))

# The banks of the course's circuits (12-bit ROM and RAM); a memory map file can describe others
BANKS = MemoryMap.default().bank_ranges()
JUMP_REG = 7                         # register used by jmp/jz/jnz/jltz when they need the long form


class AsmError(Exception):
    def __init__(self, msg, where=None):
        super().__init__(msg)
        self.msg = msg
        self.where = where           # Line or None

    def __str__(self):
        if self.where is None:
            return f'error: {self.msg}'
        w = self.where
        return f'{w.file}:{w.lineno}: error: {self.msg}\n    {w.text.strip()}'


class Line:
    __slots__ = ('file', 'lineno', 'text')

    def __init__(self, file, lineno, text):
        self.file, self.lineno, self.text = file, lineno, text


# ----------------------------------------------------------------------------------------------
# Expressions

TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<num>0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|[0-9][0-9_]*)
  | (?P<chr>'(?:\\.|\\x[0-9a-fA-F]{2}|[^'\\])')
  | (?P<str>"(?:\\.|[^"\\])*")
  | (?P<id>\.?[A-Za-z_][A-Za-z0-9_.]*)
  | (?P<op><<|>>|[-+*/%&|^~()\[\]:,$!])
""", re.VERBOSE)

ESCAPES = {'n': 10, 't': 9, 'r': 13, '0': 0, '\\': 92, "'": 39, '"': 34, 'a': 7, 'b': 8, 'f': 12,
           'v': 11, 'e': 27}


def unescape(body, where):
    """Character codes of a string/char literal body (without quotes)."""
    out = []
    i = 0
    while i < len(body):
        c = body[i]
        if c == '\\':
            i += 1
            if i >= len(body):
                raise AsmError('unfinished escape sequence', where)
            e = body[i]
            if e == 'x':
                h = body[i + 1:i + 3]
                if len(h) != 2:
                    raise AsmError('\\x needs two hex digits', where)
                out.append(int(h, 16))
                i += 3
                continue
            if e not in ESCAPES:
                raise AsmError(f'unknown escape sequence \\{e}', where)
            out.append(ESCAPES[e])
        else:
            out.append(ord(c))
        i += 1
    return out


def tokenize(text, where):
    toks = []
    pos = 0
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise AsmError(f'unexpected character {text[pos]!r}', where)
        pos = m.end()
        kind = m.lastgroup
        if kind != 'ws':
            toks.append((kind, m.group()))
    return toks


class Expr:
    """Parsed expression. Nodes are tuples:
       ('num', value, is_bitpattern) ('sym', name) ('pc',) ('neg', e) ('not', e)
       ('bin', op, a, b) ('slice', e, hi, lo)"""

    def __init__(self, node, text):
        self.node, self.text = node, text

    def symbols(self):
        out = []

        def walk(n):
            if n[0] == 'sym':
                out.append(n[1])
            elif n[0] in ('neg', 'not'):
                walk(n[1])
            elif n[0] == 'bin':
                walk(n[2]); walk(n[3])
            elif n[0] == 'slice':
                walk(n[1])
        walk(self.node)
        return out

    def is_plain_number(self):
        """A literal number, possibly with a sign: used as a branch offset, as in the lectures."""
        n = self.node
        while n[0] == 'neg' or (n[0] == 'bin' and False):
            n = n[1]
        return n[0] == 'num'

    def is_bitpattern(self):
        """A hex/binary literal or a bit slice: 0x80..0xFF are then fine for lli."""
        n = self.node
        return (n[0] == 'num' and n[2]) or n[0] == 'slice'


BINARY_PRECEDENCE = [('|',), ('^',), ('&',), ('<<', '>>'), ('+', '-'), ('*', '/', '%')]


class ExprParser:
    def __init__(self, toks, where, text):
        self.toks, self.i, self.where, self.text = toks, 0, where, text

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self):
        t = self.peek()
        self.i += 1
        return t

    def expect(self, val):
        k, v = self.take()
        if v != val:
            raise AsmError(f'expected {val!r} in expression {self.text!r}', self.where)

    def parse(self, level=0):
        if level == len(BINARY_PRECEDENCE):
            return self.unary()
        left = self.parse(level + 1)
        while True:
            k, v = self.peek()
            if k == 'op' and v in BINARY_PRECEDENCE[level]:
                self.take()
                right = self.parse(level + 1)
                left = ('bin', v, left, right)
            else:
                return left

    def unary(self):
        k, v = self.peek()
        if k == 'op' and v == '-':
            self.take()
            return ('neg', self.unary())
        if k == 'op' and v == '+':
            self.take()
            return self.unary()
        if k == 'op' and v in '~!':
            self.take()
            return ('not', self.unary())
        return self.postfix()

    def postfix(self):
        e = self.primary()
        while self.peek() == ('op', '['):
            self.take()
            hi = self.const_int()
            self.expect(':')
            lo = self.const_int()
            self.expect(']')
            if hi < lo:
                raise AsmError(f'bit slice [{hi}:{lo}]: the first index must be the higher one', self.where)
            e = ('slice', e, hi, lo)
        return e

    def const_int(self):
        k, v = self.take()
        if k != 'num':
            raise AsmError('bit slice indices must be numbers', self.where)
        return parse_number(v)

    def primary(self):
        k, v = self.take()
        if k == 'num':
            return ('num', parse_number(v), v[:2].lower() in ('0x', '0b'))
        if k == 'chr':
            codes = unescape(v[1:-1], self.where)
            return ('num', codes[0], False)
        if k == 'id':
            return ('sym', v)
        if k == 'op' and v == '$':
            return ('pc',)
        if k == 'op' and v == '(':
            e = self.parse()
            self.expect(')')
            return e
        if k is None:
            raise AsmError(f'expression {self.text!r} is incomplete', self.where)
        raise AsmError(f'unexpected {v!r} in expression {self.text!r}', self.where)


def parse_number(s):
    s = s.replace('_', '').lower()
    if s.startswith('0x'):
        return int(s[2:], 16)
    if s.startswith('0b'):
        return int(s[2:], 2)
    if s.startswith('0o'):
        return int(s[2:], 8)
    return int(s, 10)


def parse_expr(text, where):
    text = text.strip()
    if not text:
        raise AsmError('missing operand', where)
    toks = tokenize(text, where)
    p = ExprParser(toks, where, text)
    node = p.parse()
    if p.i != len(toks):
        raise AsmError(f'unexpected {toks[p.i][1]!r} in expression {text!r}', where)
    return Expr(node, text)


# ----------------------------------------------------------------------------------------------
# Source statements

class Stmt:
    __slots__ = ('kind', 'args', 'line', 'scope', 'addr', 'bank', 'size', 'long', 'module')

    def __init__(self, kind, args, line, scope, module):
        self.kind, self.args, self.line, self.scope = kind, args, line, scope
        self.module = module
        self.addr = None
        self.bank = None
        self.size = 0
        self.long = False


class Module:
    """One source file of a program. Its labels are its own unless it exports them with .globl;
    it uses another file's label after declaring it with .extern."""

    def __init__(self, name):
        self.name = name
        self.exports = {}            # name -> Line of the .globl
        self.imports = {}            # name -> Line of the .extern


def strip_comment(text):
    """Remove a ; or // comment, ignoring those inside quotes."""
    q = None
    i = 0
    while i < len(text):
        c = text[i]
        if q:
            if c == '\\':
                i += 2
                continue
            if c == q:
                q = None
        elif c in '"\'':
            # a lone ' in a comment-free line would be odd, but only treat it as a quote if closed
            q = c
        elif c == ';' or text.startswith('//', i):
            return text[:i]
        i += 1
    return text


def split_operands(text):
    """Split at commas that are not inside quotes or brackets."""
    parts, depth, q, cur = [], 0, None, ''
    i = 0
    while i < len(text):
        c = text[i]
        if q:
            cur += c
            if c == '\\' and i + 1 < len(text):
                cur += text[i + 1]
                i += 2
                continue
            if c == q:
                q = None
        elif c in '"\'':
            q = c
            cur += c
        elif c in '([':
            depth += 1
            cur += c
        elif c in ')]':
            depth -= 1
            cur += c
        elif c == ',' and depth == 0:
            parts.append(cur.strip())
            cur = ''
        else:
            cur += c
        i += 1
    if cur.strip() or parts:
        parts.append(cur.strip())
    return parts


LABEL_RE = re.compile(r'^\s*(\.?[A-Za-z_][A-Za-z0-9_.]*)\s*:(?!=)')
CONST_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_.]*)\s*=(?!=)(.*)$')
BUILTIN_INCLUDES = ('beag.inc',)


LINK_RE = re.compile(r'^[.#](globl|global|extern)\b(.*)$', re.IGNORECASE)


class Program:
    def __init__(self, memory=None):
        self.memory = memory or MemoryMap.default()
        self.banks = self.memory.bank_ranges()     # name -> (first address, first address after)
        self.stmts = []
        self.global_scope = None
        self.included = set()
        self.modules = []
        self.module = None           # index of the module being read

    # -- reading ------------------------------------------------------------------------------

    def begin_module(self, name):
        self.modules.append(Module(name))
        self.module = len(self.modules) - 1
        self.global_scope = None

    def read_file(self, path, where=None):
        try:
            with open(path, encoding='utf-8') as f:
                text = f.read()
        except OSError as e:
            raise AsmError(f'cannot read {path}: {e.strerror}', where)
        if where is None:
            self.begin_module(path)
            self.included.add(os.path.abspath(path))
        self.read_text(text, path)

    def read_text(self, text, filename='<input>'):
        if self.module is None:
            self.begin_module(filename)
        for n, raw in enumerate(text.splitlines(), 1):
            self.read_line(Line(filename, n, raw))

    def add(self, kind, args, line):
        self.stmts.append(Stmt(kind, args, line, self.global_scope, self.module))

    def link_directive(self, kind, rest, line):
        names = [n for n in re.split(r'[\s,]+', rest.strip()) if n]
        if not names:
            raise AsmError(f'.{kind} needs one or more label names', line)
        self.add('link', (kind, names), line)
        mod = self.modules[self.module]
        for n in names:
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_.]*$', n):
                raise AsmError(f'{n!r} is not a label name', line)
            if kind == 'extern':
                mod.imports.setdefault(n, line)
            else:
                mod.exports.setdefault(n, line)
            if n in mod.imports and n in mod.exports:
                raise AsmError(f'{n!r} is declared both .globl and .extern in this file', line)

    def read_line(self, line):
        text = strip_comment(line.text).rstrip()
        if not text.strip():
            if line.text.strip():
                self.add('comment', (), line)    # kept for the listing
            return
        while True:
            m = LABEL_RE.match(text)
            if not m:
                break
            name = m.group(1)
            if name.lower() in MNEMONICS or is_register(name):
                break
            if not name.startswith('.'):
                self.global_scope = name
            self.add('label', (name,), line)
            text = text[m.end():]
        text = text.strip()
        if not text:
            return
        m = LINK_RE.match(text)
        if m:
            kind = m.group(1).lower()
            self.link_directive('extern' if kind == 'extern' else 'globl', m.group(2), line)
            return
        if text.startswith('#'):
            self.read_directive(text, line)
            return
        m = CONST_RE.match(text)
        if m:
            self.add('const', (m.group(1), parse_expr(m.group(2), line)), line)
            return
        parts = text.split(None, 1)
        mnem = parts[0].lower()
        ops = split_operands(parts[1]) if len(parts) > 1 else []
        if mnem not in MNEMONICS:
            hint = difflib.get_close_matches(mnem, MNEMONICS, 1)
            more = f' (did you mean {hint[0]}?)' if hint else ''
            if text.endswith(':') or ':' in parts[0]:
                more = ''
            raise AsmError(f'unknown instruction {parts[0]!r}{more}', line)
        self.add('insn', (mnem, ops), line)

    def read_directive(self, text, line):
        parts = text[1:].split(None, 1)
        d = parts[0].lower() if parts else ''
        rest = parts[1].strip() if len(parts) > 1 else ''
        if d == 'include':
            m = re.match(r'^"([^"]+)"$', rest)
            if not m:
                raise AsmError('#include needs a file name in double quotes', line)
            name = m.group(1)
            if os.path.basename(name) in BUILTIN_INCLUDES:
                return                       # the instruction set is built into this assembler
            path = os.path.join(os.path.dirname(line.file), name)
            key = os.path.abspath(path)
            if key in self.included:
                return
            self.included.add(key)
            self.read_file(path, line)
        elif d == 'bank':
            if rest not in self.banks:
                names = ', '.join(self.banks)
                where = self.memory.file or 'the memory map'
                raise AsmError(f'unknown bank {rest!r}: {where} has {names}', line)
            self.add('bank', (rest,), line)
        elif d == 'addr':
            self.add('addr', (parse_expr(rest, line),), line)
        elif d == 'res':
            self.add('res', (parse_expr(rest, line),), line)
        elif d in ('d16', 'd', 'dw', 'word'):
            items = []
            for op in split_operands(rest):
                if op.startswith('"'):
                    if len(op) < 2 or not op.endswith('"'):
                        raise AsmError('unterminated string', line)
                    items.append(unescape(op[1:-1], line))
                else:
                    items.append(parse_expr(op, line))
            if not items:
                raise AsmError(f'#{d} needs at least one value', line)
            self.add('data', (items,), line)
        elif d in ('once',):
            pass
        elif d in ('bankdef', 'ruledef', 'subruledef', 'bits', 'outp', 'fn'):
            raise AsmError(f'#{d} is not supported: the BEAG instruction set is built into beagasm', line)
        else:
            raise AsmError(f'unknown directive #{d}', line)


REG_RE = re.compile(r'^[rR]([0-7])$')


def is_register(s):
    return bool(REG_RE.match(s.strip()))


def reg(s, where):
    m = REG_RE.match(s.strip())
    if not m:
        raise AsmError(f'expected a register r0..r7, found {s!r}', where)
    return int(m.group(1))


def mem_reg(s, where):
    m = re.match(r'^\(\s*([rR][0-7])\s*\)$', s.strip())
    if not m:
        raise AsmError(f'expected an address register in brackets like (r2), found {s!r}', where)
    return int(m.group(1)[1])


# ----------------------------------------------------------------------------------------------
# Assembly

INSN_SIZE = {m: 1 for m in OPCODES}
INSN_SIZE.update({'li': 2, 'b': 1, 'nop': 1})
LONG_SIZE = {'jmp': 3, 'jz': 4, 'jnz': 4, 'jltz': 5}


class Assembler:
    def __init__(self, program):
        self.p = program
        self.symbols = {}        # name -> value of every label (all files: for the tools)
        self.banks = program.banks
        self.images = {b: {} for b in self.banks}     # bank -> {addr: word}
        self.listing = []        # (addr or None, [words], stmt)
        self.warnings = []
        self.reset_symbols()

    def reset_symbols(self):
        n = len(self.p.modules)
        self.locals = [{} for _ in range(n)]     # per file: name -> value
        self.mconsts = [{} for _ in range(n)]    # per file: name -> (Expr, Stmt)
        self.globals = {}                        # .globl labels: name -> value
        self.gconsts = {}                        # .globl constants: name -> (Expr, Stmt)
        self.global_mod = {}                     # .globl name -> index of the file defining it

    def lookup(self, name, stmt, partial, depth):
        m = stmt.module
        mod = self.p.modules[m]
        if name in self.locals[m]:
            return self.locals[m][name]
        if name in self.mconsts[m]:
            return self.const_value(self.mconsts[m][name], name, partial, depth)
        visible = name in mod.imports or name in mod.exports
        if visible and name in self.globals:
            return self.globals[name]
        if visible and name in self.gconsts:
            return self.const_value(self.gconsts[name], name, partial, depth)
        if partial:
            raise _Unknown()
        if name in self.global_mod:
            other = self.p.modules[self.global_mod[name]].name
            raise AsmError(f'{name!r} is defined in {other}; add ".extern {name}" to this file to use it',
                           stmt.line)
        if name in mod.imports:
            raise AsmError(f'{name!r} is declared .extern, but no file defines it with ".globl {name}"',
                           stmt.line)
        if name in mod.exports:
            raise AsmError(f'{name!r} is declared .globl, but it is not defined in this file', stmt.line)
        known = list(self.locals[m]) + list(self.mconsts[m]) + \
            [g for g in self.globals if g in mod.imports or g in mod.exports]
        hint = difflib.get_close_matches(name, known, 1)
        more = f' (did you mean {hint[0]}?)' if hint else ''
        raise AsmError(f'unknown label or constant {name!r}{more}', stmt.line)

    def const_value(self, entry, name, partial, depth):
        if depth > 50:
            raise AsmError(f'constant {name} is defined in terms of itself', entry[1].line)
        cexpr, cstmt = entry
        return self.eval(cexpr.node, cstmt, None, partial, depth + 1)

    def define(self, name, value, st, is_const=False):
        m = st.module
        mod = self.p.modules[m]
        if name in self.locals[m] or name in self.mconsts[m] or \
                (name in mod.exports and (name in self.globals or name in self.gconsts)
                 and self.global_mod.get(name) == m):
            raise AsmError(f'{name!r} is defined twice', st.line)
        if name in mod.imports:
            raise AsmError(f'{name!r} is declared .extern, but this file defines it too', st.line)
        if name in mod.exports:
            if name in self.global_mod:
                other = self.p.modules[self.global_mod[name]].name
                raise AsmError(f'{name!r} is defined (with .globl) both in {other} and here', st.line)
            self.global_mod[name] = m
            if is_const:
                self.gconsts[name] = value
            else:
                self.globals[name] = value
        elif is_const:
            self.mconsts[m][name] = value
        else:
            self.locals[m][name] = value

    # -- symbols ----------------------------------------------------------------------------

    def qualify(self, name, scope):
        if name.startswith('.'):
            if scope is None:
                return name
            return scope + name
        return name

    def value(self, expr, stmt, pc, partial=False):
        """Evaluate; with partial=True return None for unknown symbols."""
        try:
            return self.eval(expr.node, stmt, pc, partial)
        except _Unknown:
            return None

    def eval(self, n, stmt, pc, partial, depth=0):
        k = n[0]
        if k == 'num':
            return n[1]
        if k == 'pc':
            if pc is None:
                raise AsmError('$ (current address) cannot be used here', stmt.line)
            return pc
        if k == 'sym':
            if is_register(n[1]):
                raise AsmError(f'a register ({n[1]}) cannot be used here', stmt.line)
            return self.lookup(self.qualify(n[1], stmt.scope), stmt, partial, depth)
        if k == 'neg':
            return -self.eval(n[1], stmt, pc, partial, depth)
        if k == 'not':
            return ~self.eval(n[1], stmt, pc, partial, depth)
        if k == 'slice':
            v = self.eval(n[1], stmt, pc, partial, depth)
            return (v >> n[3]) & ((1 << (n[2] - n[3] + 1)) - 1)
        if k == 'bin':
            a = self.eval(n[2], stmt, pc, partial, depth)
            b = self.eval(n[3], stmt, pc, partial, depth)
            op = n[1]
            if op == '+': return a + b
            if op == '-': return a - b
            if op == '*': return a * b
            if op in '/%':
                if b == 0:
                    raise AsmError('division by zero in expression', stmt.line)
                q = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)
                return q if op == '/' else a - q * b
            if op == '&': return a & b
            if op == '|': return a | b
            if op == '^': return a ^ b
            if op == '<<': return a << b
            if op == '>>': return a >> b
        raise AsmError('bad expression', stmt.line)

    # -- layout -------------------------------------------------------------------------------

    def size_of(self, st):
        mnem, ops = st.args
        if mnem in LONG_JUMPS:
            return LONG_SIZE[mnem] if st.long else 1
        return INSN_SIZE[mnem]

    def layout(self):
        """Give every statement an address. Returns True if any long jump changed."""
        self.reset_symbols()
        pcs = {b: lo for b, (lo, hi) in self.banks.items()}
        bank = 'program'
        module = None
        self.extent = [{} for _ in self.p.modules]     # per file: bank -> [start, end)
        for st in self.p.stmts:
            if st.module != module:          # every file starts in the program bank
                module = st.module
                bank = 'program'
            st.bank = bank
            st.addr = pcs[bank]
            if st.kind == 'label':
                self.define(self.qualify(st.args[0], st.scope), pcs[bank], st)
            elif st.kind == 'const':
                name = st.args[0]
                if is_register(name) or name.lower() in MNEMONICS:
                    raise AsmError(f'{name!r} is a register or instruction name', st.line)
                self.define(name, (st.args[1], st), st, is_const=True)
            elif st.kind == 'bank':
                bank = st.args[0]
                st.bank = bank
                st.addr = pcs[bank]
            elif st.kind == 'addr':
                v = self.value(st.args[0], st, pcs[bank], partial=True)
                if v is None:
                    raise AsmError('#addr must not depend on labels defined further down', st.line)
                lo, hi = self.banks[bank]
                if not lo <= v <= hi:
                    raise AsmError(f'#addr 0x{v:04X} is outside the {bank} bank '
                                   f'(0x{lo:04X}-0x{hi - 1:04X})', st.line)
                pcs[bank] = v
                st.addr = v
            elif st.kind == 'res':
                v = self.value(st.args[0], st, pcs[bank], partial=True)
                if v is None:
                    raise AsmError('#res must not depend on labels defined further down', st.line)
                if v < 0:
                    raise AsmError('#res needs a size of 0 or more', st.line)
                st.size = v
                pcs[bank] += v
            elif st.kind == 'data':
                st.size = sum(len(it) if isinstance(it, list) else 1 for it in st.args[0])
                pcs[bank] += st.size
            elif st.kind == 'insn':
                if bank != 'program':
                    raise AsmError('instructions must be in the program bank '
                                   '(add #bank program before them)', st.line)
                st.size = self.size_of(st)
                pcs[bank] += st.size
            if st.size and st.kind != 'label':
                ext = self.extent[module].setdefault(st.bank, [st.addr, st.addr])
                ext[0] = min(ext[0], st.addr)
                ext[1] = max(ext[1], st.addr + st.size)
        self.end = pcs
        self.symbols = {}
        for m in reversed(range(len(self.p.modules))):
            self.symbols.update(self.locals[m])
        self.symbols.update(self.globals)
        # long jumps out of range?
        changed = False
        for st in self.p.stmts:
            if st.kind == 'insn' and st.args[0] in LONG_JUMPS and not st.long:
                ops = st.args[1]
                target = self.value(self.target_expr(st, ops), st, st.addr, partial=True)
                if target is None:
                    continue           # reported later
                if not -128 <= target - st.addr <= 127:
                    st.long = True
                    changed = True
        return changed

    def target_expr(self, st, ops):
        mnem = st.args[0]
        need = 1 if mnem == 'jmp' else 2
        if len(ops) != need:
            raise AsmError(f'{mnem} needs {need} operand{"s" if need > 1 else ""}', st.line)
        return parse_expr(ops[-1], st.line)

    # -- encoding -----------------------------------------------------------------------------

    def encode(self, st):
        mnem, ops = st.args
        line = st.line
        pc = st.addr

        def nops(n):
            if len(ops) != n:
                form = {3: 'rd,rx,ry', 2: 'two operands', 1: 'one operand', 0: 'no operands'}[n]
                raise AsmError(f'{mnem} takes {form}, found {len(ops)} operand(s)', line)

        def imm(e, lo, hi, what):
            v = self.value(e, st, pc)
            if not lo <= v <= hi:
                raise AsmError(f'{what} {v} is out of range ({lo}..{hi})', line)
            return v

        def lli_value(e):
            v = self.value(e, st, pc)
            if -128 <= v <= 127:
                return v & 0xFF
            if 128 <= v <= 255 and e.is_bitpattern():
                return v
            if 128 <= v <= 255:
                raise AsmError(f'lli sign-extends its 8-bit value, so {v} would load {v - 256}; '
                               f'use li for {v}, or write the bit pattern in hex (0x{v:02X})', line)
            raise AsmError(f'lli value {v} does not fit in 8 bits (-128..127); use li', line)

        def offset(e):
            if e.is_plain_number():
                off = self.value(e, st, pc)
            else:
                off = self.value(e, st, pc) - pc
            if not -128 <= off <= 127:
                raise AsmError(f'branch target is {off} words away; a branch reaches -128..127 '
                               f'(use jmp/jz/jnz/jltz for longer jumps)', line)
            return off & 0xFF

        if mnem in R_FORMAT:
            nops(3)
            d, x, y = (reg(o, line) for o in ops)
            return [OPCODES[mnem] << 12 | d << 8 | x << 4 | y]
        if mnem == 'lw':
            nops(2)
            return [0x6000 | reg(ops[0], line) << 8 | mem_reg(ops[1], line) << 4]
        if mnem == 'sw':
            nops(2)
            return [0x5000 | mem_reg(ops[1], line) << 4 | reg(ops[0], line)]
        if mnem == 'lli':
            nops(2)
            return [0x9000 | reg(ops[0], line) << 8 | lli_value(parse_expr(ops[1], line))]
        if mnem == 'lhi':
            nops(2)
            return [0x8000 | reg(ops[0], line) << 8 |
                    imm(parse_expr(ops[1], line), -128, 255, 'lhi value') & 0xFF]
        if mnem in BRANCHES:
            nops(2)
            return [OPCODES[mnem] << 12 | reg(ops[0], line) << 8 | offset(parse_expr(ops[1], line))]
        if mnem == 'li':
            nops(2)
            r = reg(ops[0], line)
            v = imm(parse_expr(ops[1], line), -32768, 65535, 'li value') & 0xFFFF
            return [0x9000 | r << 8 | (v & 0xFF), 0x8000 | r << 8 | (v >> 8)]
        if mnem == 'b':
            nops(1)
            return [0xE000 | offset(parse_expr(ops[0], line))]
        if mnem == 'nop':
            nops(0)
            return [0x0000]
        if mnem in LONG_JUMPS:
            e = self.target_expr(st, ops)
            if e.is_plain_number():
                raise AsmError(f'{mnem} needs a label as its target', line)
            target = self.value(e, st, pc) & 0xFFFF
            r = 0 if mnem == 'jmp' else reg(ops[0], line)
            if not st.long:
                op = 'bz' if mnem == 'jmp' else LONG_JUMPS[mnem]
                return [OPCODES[op] << 12 | r << 8 | ((target - pc) & 0xFF)]
            far = [0x9000 | JUMP_REG << 8 | (target & 0xFF),     # lli r7,target[7:0]
                   0x8000 | JUMP_REG << 8 | (target >> 8),       # lhi r7,target[15:8]
                   0x4000 | JUMP_REG << 4]                       # jalr r0,r7,r0
            if mnem == 'jmp':
                return far
            if mnem == 'jz':
                return [0xD000 | r << 8 | 4] + far               # bnz r,skip
            if mnem == 'jnz':
                return [0xE000 | r << 8 | 4] + far               # bz r,skip
            return [0xF000 | r << 8 | 2, 0xE004] + far           # bltz r,+2 ; b skip
        raise AsmError(f'unknown instruction {mnem!r}', line)

    def assemble(self):
        for _ in range(100):
            if not self.layout():
                break
        else:
            raise AsmError('jump lengths did not settle')
        for m, mod in enumerate(self.p.modules):
            for name, line in mod.exports.items():
                if self.global_mod.get(name) != m:
                    raise AsmError(f'{name!r} is declared .globl, but it is not defined in this file', line)
        for st in self.p.stmts:
            if st.kind == 'insn':
                words = self.encode(st)
                assert len(words) == st.size, (st.args, words, st.size)
                self.put(st, words)
            elif st.kind == 'data':
                words = []
                for it in st.args[0]:
                    if isinstance(it, list):
                        words.extend(c & 0xFFFF for c in it)
                    else:
                        v = self.value(it, st, st.addr + len(words))
                        if not -32768 <= v <= 65535:
                            raise AsmError(f'value {v} does not fit in 16 bits', st.line)
                        words.append(v & 0xFFFF)
                self.put(st, words)
            elif st.kind == 'const':
                self.value(st.args[1], st, None)        # report errors in unused constants too
                self.listing.append((None, [], st))
            else:
                self.listing.append((st.addr if st.kind in ('label', 'res', 'addr') else None, [], st))
        for b, (lo, hi) in self.banks.items():
            if self.end[b] > hi:
                what = {'program': 'the program', 'data': 'the data'}.get(b, f'the contents of bank {b}')
                raise AsmError(f'{what} is {self.end[b] - lo} words long, but the {b} bank holds '
                               f'{hi - lo} words (0x{lo:04X}-0x{hi - 1:04X})')

    def put(self, st, words):
        img = self.images[st.bank]
        for i, w in enumerate(words):
            a = st.addr + i
            if a in img:
                raise AsmError(f'address 0x{a:04X} is used twice (check #addr)', st.line)
            img[a] = w
        self.listing.append((st.addr, words, st))

    # -- output -------------------------------------------------------------------------------

    def image_words(self, bank):
        img = self.images[bank]
        if not img:
            return []
        lo = self.banks[bank][0]
        return [img.get(a, 0) for a in range(lo, max(img) + 1)]


def assemble_text(text, filename='<input>', memory=None):
    """Assemble source text; returns the Assembler (images, symbols, listing)."""
    return assemble_modules([(text, filename)], memory)


def assemble_file(path, memory=None):
    return assemble_files([path], memory)


def assemble_files(paths, memory=None):
    """Assemble and link several files: the first one starts at address 0."""
    p = Program(memory)
    for path in paths:
        p.read_file(path)
    a = Assembler(p)
    a.assemble()
    return a


def assemble_modules(modules, memory=None):
    """Assemble and link [(source text, file name), ...]."""
    p = Program(memory)
    for text, name in modules:
        p.begin_module(name)
        p.read_text(text, name)
    a = Assembler(p)
    a.assemble()
    return a


def link_names(paths, memory=None):
    """(exports, imports) of assembly files: the labels they declare .globl and .extern."""
    p = Program(memory)
    for path in paths:
        p.read_file(path)
    exports, imports = {}, set()
    for mod in p.modules:
        for n in mod.exports:
            exports[n] = mod.name
        imports.update(mod.imports)
    return exports, imports


# ----------------------------------------------------------------------------------------------
# Memory map

def map_symbols(a):
    """[(addr, bank, name, module, global)] of the labels worth showing in a map, in order."""
    out = []
    for st in a.p.stmts:
        if st.kind != 'label' or st.args[0].startswith('.'):
            continue
        name = st.args[0]
        m = st.module
        if re.match(r'^L\d+$', name):
            continue                     # the compiler's own labels
        parts = name.split('_')
        if name.startswith('rt_') and len(parts) > 2 and \
                ('_'.join(parts[:2]) in a.locals[m] or '_'.join(parts[:2]) in a.globals):
            continue                     # labels inside a runtime routine
        out.append((st.addr, st.bank, name, m, name in a.p.modules[m].exports))
    return out


def write_map(a, f, title, origins=None, describe=None):
    """A map of the program: where each file and each symbol is in the ROM and the RAM.
    origins: label -> where it comes from (default: its file); describe: file -> text."""
    origins = origins or {}
    describe = describe or {}
    mods = a.p.modules
    syms = map_symbols(a)
    name_w = max([len(s[2]) for s in syms] + [12]) + 2
    f.write(f'BEAG memory map of {title}\n\n')
    f.write('Files\n')
    for m, mod in enumerate(mods):
        text = describe.get(mod.name, os.path.basename(mod.name))
        f.write(f'  {text}\n')
        for b in a.banks:
            ext = a.extent[m].get(b)
            if ext:
                n = ext[1] - ext[0]
                f.write(f'      {b:8s} {ext[0]:04x}-{ext[1] - 1:04x}  {n:5d} word{"s" if n != 1 else ""}\n')
    mem = a.p.memory
    for b, (lo, hi) in a.banks.items():
        used = a.end[b] - lo
        if b not in ('program', 'data') and used == 0:
            continue
        f.write('\n')
        kind = mem.banks[b].kind.upper()
        if b == 'program':
            f.write(f'Program ROM 0x{lo:04X}-0x{hi - 1:04X}: {used} of {hi - lo} words used, '
                    f'{hi - lo - used} free\n')
        elif b == 'data':
            heap = a.symbols.get('___heap_start')
            f.write(f'Data RAM 0x{lo:04X}-0x{hi - 1:04X}: {used} words of variables')
            if heap is not None:
                top = mem.stack_top
                if mem.stack_in_data:
                    f.write(f'; the heap starts at 0x{heap:04x}, the stack at 0x{(top - 1) & 0xFFFF:04x} and grows '
                            f'down ({top - heap} words for both)')
                else:
                    f.write(f'; the heap is 0x{heap:04x}-0x{hi - 1:04x} ({hi - heap} words); the stack grows '
                            f'down from 0x{(top - 1) & 0xFFFF:04x}')
            f.write('\n')
        else:
            f.write(f'{kind} bank {b} 0x{lo:04X}-0x{hi - 1:04X}: {used} of {hi - lo} words used\n')
        f.write(f'  addr  words  {"symbol".ljust(name_w)}   from\n')
        here = [s for s in syms if s[1] == b]
        for i, (addr, bank, name, m, glob) in enumerate(here):
            end = a.extent[m].get(b, [addr, addr])[1]
            nxt = [s[0] for s in here[i + 1:] if s[0] > addr]
            size = min(nxt[0] if nxt else end, end) - addr
            if nxt and nxt[0] > addr and here[i + 1][0] == addr:
                size = 0
            origin = origins.get(name, os.path.basename(mods[m].name))
            f.write(f'  {addr:04x}  {size if size > 0 else "":>5}  {name.ljust(name_w)} '
                    f'{"G" if glob else " "} {origin}\n')
    globs = sorted((s for s in syms if s[4]), key=lambda s: s[2])
    if globs:
        f.write('\nGlobal symbols (.globl), by name\n')
        for addr, bank, name, m, glob in globs:
            f.write(f'  {name.ljust(name_w)} {addr:04x}  {origins.get(name, os.path.basename(mods[m].name))}\n')


def format_logisim(words):
    """Logisim 'v2.0 raw' image, laid out as customasm's logisim16 format."""
    out = ['v2.0 raw\n']
    for i, w in enumerate(words):
        out.append(f'{w:04x} ')
        if i % 8 == 7:
            out.append('\n')
    return ''.join(out)


def format_hex(words):
    return ''.join(f'{w:04x}\n' for w in words)


def disassemble(w, pc=None):
    """Text of one machine word (used by listings and the simulator's trace)."""
    op = w >> 12
    d, x, y, imm = (w >> 8) & 7, (w >> 4) & 7, w & 7, w & 0xFF
    simm = imm - 256 if imm & 0x80 else imm
    names = {v: k for k, v in OPCODES.items()}
    if op in (0xA, 0xB, 0xC):
        return f'.word 0x{w:04x}'
    m = names[op]
    if w == 0:
        return 'nop'
    if m in R_FORMAT:
        return f'{m} r{d},r{x},r{y}'
    if m == 'lw':
        return f'lw r{d},(r{x})'
    if m == 'sw':
        return f'sw r{y},(r{x})'
    if m == 'lli':
        return f'lli r{d},{simm}'
    if m == 'lhi':
        return f'lhi r{d},0x{imm:02x}'
    tgt = f' ; -> 0x{(pc + simm) & 0xFFFF:04x}' if pc is not None else ''
    return f'{m} r{d},{simm}{tgt}'


def write_listing(a, f, title=None):
    """Every line of every file with the absolute address and the machine code of each word:
    first the program ROM, then the data RAM."""
    if title:
        f.write(f'BEAG listing of {title}\n')
    # a label sharing its line with an instruction is shown on the instruction's row
    busy = {id(st.line) for _, _, st in a.listing if st.kind != 'label'}
    for bank, (lo, hi) in a.banks.items():
        rows = [(addr, k, words, st) for k, (addr, words, st) in enumerate(a.listing)
                if st.bank == bank and not (st.kind == 'label' and id(st.line) in busy)]
        if not any(words or st.kind in ('res', 'label') for _, _, words, st in rows):
            continue
        rows.sort(key=lambda r: (r[3].addr, r[1]))      # address order (#addr can jump about)
        name = {'program': 'Program ROM', 'data': 'Data RAM'}.get(
            bank, f'{a.p.memory.banks[bank].kind.upper()} bank {bank}')
        f.write(f'\n{name} 0x{lo:04X}-0x{hi - 1:04X}\n')
        f.write(' addr | code | source\n')
        f.write('------+------+---------------------------------------------------------\n')
        module = None
        for _, _, words, st in rows:
            addr = st.addr
            if st.module != module and len(a.p.modules) > 1:
                module = st.module
                f.write(f'      |      | ======== {a.p.modules[module].name} ========\n')
            module = st.module
            src = st.line.text.rstrip()
            if st.kind == 'insn':
                for i, w in enumerate(words):
                    text = src if i == 0 else f'{"":28}({disassemble(w, addr + i)})'
                    f.write(f' {addr + i:04x} | {w:04x} | {text}\n')
            elif st.kind == 'data':
                for i in range(0, len(words), 4):
                    chunk = ' '.join(f'{w:04x}' for w in words[i:i + 4])
                    f.write(f' {addr + i:04x} | {chunk} | {src if i == 0 else ""}\n')
            elif st.kind == 'res':
                end = f'-{addr + st.size - 1:04x}' if st.size > 1 else ''
                f.write(f' {addr:04x} |      | {src}' + (f'    ({addr:04x}{end})' if st.size else '') + '\n')
            elif st.kind in ('label', 'addr'):
                f.write(f' {addr:04x} |      | {src}\n')
            else:
                f.write(f'      |      | {src}\n')


def main(argv=None):
    ap = argparse.ArgumentParser(description='Assembler for the BEAG computer (COMP20020).')
    ap.add_argument('sources', nargs='+', help='assembly source files (.asm): several files are linked, '
                                               'the first one starting at address 0')
    ap.add_argument('-o', '--output', help='output file (default: first source name with .mem)')
    ap.add_argument('-f', '--format', choices=['logisim', 'hex'], default='logisim',
                    help='logisim: Logisim ROM image (default); hex: one word per line')
    ap.add_argument('-l', '--listing', help='also write a listing to this file ("-" for the screen)')
    ap.add_argument('-m', '--map', help='also write a memory map to this file ("-" for the screen)')
    ap.add_argument('--memory', help='the memory map of the computer (default: beag_memory.txt next to '
                                     'the first source, else the course\'s BEAG)')
    ap.add_argument('-s', '--symbols', action='store_true', help='print the label addresses')
    args = ap.parse_args(argv)
    try:
        memory = MemoryMap.find(args.memory, near=args.sources[0])
        a = assemble_files(args.sources, memory)
    except (AsmError, MemoryMapError) as e:
        print(e, file=sys.stderr)
        return 1
    if memory.file:
        print(f'beagasm: the memory map is {memory.file}', file=sys.stderr)
    out = args.output or os.path.splitext(args.sources[0])[0] + '.mem'
    if args.map:
        if args.map == '-':
            write_map(a, sys.stdout, out)
        else:
            with open(args.map, 'w') as f:
                write_map(a, f, out)
    fmt = format_logisim if args.format == 'logisim' else format_hex
    prog = a.image_words('program')
    with open(out, 'w') as f:
        f.write(fmt(prog))
    sizes = [f'{len(prog)} words of program']
    for bank in a.banks:
        if bank == 'program':
            continue
        words = a.image_words(bank)
        if words:
            bout = os.path.splitext(out)[0] + '.' + bank + os.path.splitext(out)[1]
            with open(bout, 'w') as f:
                f.write(fmt(words))
            sizes.append(f'{len(words)} words of initial data for bank {bank} in {bout}')
            if memory.banks[bank].kind == 'ram':
                print(f'note: {bout} holds initial values for RAM bank {bank}; load it into that RAM yourself, '
                      f'the program does not set it up', file=sys.stderr)
            else:
                print(f'note: {bout} is the image of ROM bank {bank}; load it into that ROM', file=sys.stderr)
    if args.listing:
        if args.listing == '-':
            write_listing(a, sys.stdout)
        else:
            with open(args.listing, 'w') as f:
                write_listing(a, f)
    if args.symbols:
        for name, v in sorted(a.symbols.items(), key=lambda kv: kv[1]):
            print(f'{v:04x} {name}')
    print(f'{out}: ' + ', '.join(sizes), file=sys.stderr)
    return 0


class _Unknown(Exception):
    pass


if __name__ == '__main__':
    sys.exit(main())
