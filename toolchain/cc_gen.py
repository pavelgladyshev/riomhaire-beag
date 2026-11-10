"""Code generator of beagcc, the C compiler for the BEAG computer.

Register use in the generated code:
    r0      always 0
    r1, r2  values of expressions; a function returns its result in r1. A call may change them.
    r3..r5  register variables (the most used local variables of a function) or more expression
            values. A function that uses one of them saves it on entry and restores it on return.
    r6      stack pointer (sp): the last word pushed; the stack grows down from 0x2FFF
    r7      return address after jalr, and a scratch register for constants and addresses

Stack frame of a function, from sp upwards (there is no frame pointer: the compiler knows how far
sp has moved and addresses everything from sp):
    local variables kept in memory
    saved r3..r5 (those the function uses)
    return address
    argument 1, argument 2, ... (pushed by the caller)
A call: the caller makes room for the arguments and stores them, 'jalr r7,r7,r0' jumps to the
function with the return address in r7, and after the return the caller removes the arguments.
"""

from cc_lex import CompileError, SOURCES
from cc_parse import Node, promote, is_const_object
from beag_memory import MemoryMap

TEMP_ORDER = (1, 2, 3, 4, 5)
CALLER_SAVED = (1, 2)
CALLEE_SAVED = (3, 4, 5)
HELPER_CLOBBERS = (1, 2, 3)      # runtime routines also change r3 (and r7)
TMP = 7

HELPER_OPS = {'&': 'rt_and', '|': 'rt_or', '^': 'rt_xor', '<<': 'rt_shl'}
NEGATE = {'==': '!=', '!=': '==', '<': '>=', '>=': '<', '>': '<=', '<=': '>'}
WRITES = {'add', 'sub', 'mul', 'div', 'rem', 'lw', 'lhi', 'lli', 'li', 'jalr'}


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def addr_text(label, off):
    if label is None:
        return f'0x{off & 0xFFFF:04x}'
    if off == 0:
        return label
    return f'{label}+{off}' if off > 0 else f'{label}-{-off}'


def log2_exact(v):
    v &= 0xFFFF
    if v and v & (v - 1) == 0:
        return v.bit_length() - 1
    return None


def children(e):
    """The sub-expressions of an expression Node."""
    out = []
    for k, v in e.__dict__.items():
        if k in ('tok', 'type', 'sym', 'direct'):
            continue
        if isinstance(v, Node):
            out.append(v)
        elif isinstance(v, list):
            out.extend(x for x in v if isinstance(x, Node))
    return out


def dest_reg(op, args):
    if op in WRITES:
        return int(args.split(',')[0].strip()[1])
    return None


# ----------------------------------------------------------------------------------------------
# Choosing register variables

class Usage:
    """How often each local variable is used (loops count more), and which have their address taken."""

    def __init__(self, fd):
        self.weight = {}
        self.addressed = set()
        self.locals = []             # local Symbols in declaration order
        self.has_asm = False
        self.walk(fd.body, 0)

    def use(self, sym, depth):
        self.weight[sym] = self.weight.get(sym, 0) + 8 ** min(depth, 3)

    def walk(self, n, depth):
        if isinstance(n, list) or isinstance(n, tuple):
            for x in n:
                self.walk(x, depth)
            return
        if not isinstance(n, Node):
            return
        k = n.kind
        if k == 'var':
            if n.sym.storage in ('local', 'param'):
                self.use(n.sym, depth)
            return
        if k == 'addr' and n.a.kind == 'var':
            self.addressed.add(n.a.sym)
        if k == 'decl':
            for sym, init in n.items:
                self.locals.append(sym)
                if init:
                    self.use(sym, depth)
                    for off, e in init:
                        self.walk(e, depth)
            return
        if k == 'asm':
            self.has_asm = True
        if k in ('while', 'do'):
            self.walk(n.c, depth + 1)
            self.walk(n.body, depth + 1)
            return
        if k == 'for':
            self.walk(n.init, depth)
            self.walk(n.c, depth + 1)
            self.walk(n.step, depth + 1)
            self.walk(n.body, depth + 1)
            return
        for key, v in n.__dict__.items():
            if key in ('tok', 'type', 'sym', 'direct', 'label', 'cases', 'default'):
                continue
            if isinstance(v, (Node, list, tuple)):
                self.walk(v, depth)


# ----------------------------------------------------------------------------------------------
# One function

class FuncGen:
    def __init__(self, g, fd):
        self.g = g
        self.fd = fd
        self.lines = []
        self.refs = {}               # label -> token of its first use
        self.breaks = []
        self.conts = []
        self.ret_label = g.new_label()
        self.last_line = None
        self.tok = fd.tok
        self.sp_delta = 0            # words pushed since the end of the prologue
        self.touched = set()         # r3..r5 used, to be saved by the prologue
        usage = Usage(fd)
        self.has_asm = usage.has_asm
        # the first argument of a function without '...' arrives in r1, the others on the stack
        self.reg_arg = not fd.sym.type.varargs and len(fd.params) >= 1
        first = fd.params[0] if self.reg_arg else None
        # register variables: the most used scalar locals and parameters whose address is not taken
        cands = []
        for sym in usage.locals + fd.params:
            w = usage.weight.get(sym, 0)
            need = 2 if sym is first else 4 if sym.storage == 'param' else 3
            if sym.type.is_scalar and not sym.type.volatile and sym not in usage.addressed and \
                    not self.has_asm and w >= need:
                cands.append((-w, len(cands), sym))
        cands.sort(key=lambda c: (c[0], c[1]))
        self.regvar = {}
        for (w, _, sym), reg in zip(cands, (5, 4, 3)):
            self.regvar[sym] = reg
            self.touched.add(reg)
        if self.has_asm:
            self.touched.update(CALLEE_SAVED)
        self.temps = [r for r in TEMP_ORDER if r not in self.regvar.values()]
        self.free = list(self.temps)
        # memory locals: the most used first (offset 0 is the cheapest to reach); the first
        # argument, when it is not a register variable, is stored with them
        mem = [s for s in usage.locals if s not in self.regvar]
        if first is not None and first not in self.regvar:
            mem.append(first)
        mem.sort(key=lambda s: -usage.weight.get(s, 0) if s.type.is_scalar else 1)
        self.local_off = {}
        off = 0
        for s in mem:
            self.local_off[s] = off
            off += s.type.size()
        self.frame = off
        stack_params = fd.params[1:] if self.reg_arg else fd.params
        self.param_index = {s: k for k, s in enumerate(stack_params)}
        self.first = first

    # -- output -------------------------------------------------------------------------------

    def emit(self, op, args='', comment=None):
        self.lines.append(('ins', op, args, comment))

    def label(self, name):
        self.lines.append(('label', name))

    def comment(self, text):
        self.lines.append(('comment', text))

    def ref(self, label):
        if label not in self.refs:
            self.refs[label] = self.tok

    def new_label(self):
        return self.g.new_label()

    def mark_line(self, tok):
        self.tok = tok
        key = (tok.file, tok.line)
        if key == self.last_line or tok.file not in SOURCES:
            return
        self.last_line = key
        lines = SOURCES[tok.file]
        if 0 < tok.line <= len(lines):
            text = lines[tok.line - 1].strip()
            if text:
                self.comment(f'{tok.line}: {text}')

    # -- registers ----------------------------------------------------------------------------

    def alloc(self):
        if not self.free:
            raise CompileError('this expression is too complicated for the registers; '
                               'split it into simpler statements', self.tok)
        r = self.free.pop(0)
        if r in CALLEE_SAVED:
            self.touched.add(r)
        return r

    def release(self, r):
        if r in self.temps and r not in self.free:
            self.free.append(r)
            self.free.sort(key=TEMP_ORDER.index)

    def done(self, r, owned):
        if owned:
            self.release(r)

    def claim(self, r):
        self.free.remove(r)
        if r in CALLEE_SAVED:
            self.touched.add(r)

    def busy(self):
        return [r for r in self.temps if r not in self.free]

    def const(self, r, v, comment=None):
        v = s16(v)
        if -128 <= v <= 127:
            self.emit('lli', f'r{r},{v}', comment)
        else:
            self.emit('li', f'r{r},{v}', comment)

    def move(self, dst, src, comment=None):
        if dst != src:
            self.emit('add', f'r{dst},r{src},r0', comment)

    def own(self, r, owned):
        """A register the caller may change, holding the value of r."""
        if owned:
            return r
        t = self.alloc()
        self.move(t, r)
        return t

    def pmove(self, moves):
        """Parallel register moves [(dst, src), ...], using r7 to break cycles."""
        moves = [(d, s) for d, s in moves if d != s]
        while moves:
            for i, (d, s) in enumerate(moves):
                if all(d != s2 for j, (d2, s2) in enumerate(moves) if j != i):
                    self.move(d, s)
                    moves.pop(i)
                    break
            else:
                d0 = moves[0][0]
                self.move(TMP, d0)
                moves = [(d, TMP if s == d0 else s) for d, s in moves]

    def adjust_sp(self, k):
        if k:
            self.const(TMP, k)
            self.emit('add', 'r6,r6,r7')
            self.sp_delta -= k

    def push(self, r, comment='push'):
        self.adjust_sp(-1)
        self.emit('sw', f'r{r},(r6)', comment)

    def pop(self, r, comment='pop'):
        self.emit('lw', f'r{r},(r6)', comment)
        self.adjust_sp(1)

    # -- addresses ----------------------------------------------------------------------------
    # ('L', offset)          a local in the frame
    # ('P', index)           a parameter (index counts words of arguments)
    # ('sym', label, off)    a global, a static or a string (label None: absolute address)
    # ('reg', r, owned)      an address held in a register

    def static_addr(self, e):
        k = e.kind
        if k == 'var':
            s = e.sym
            if s.storage in ('local', 'param') and s in self.local_off:
                return ('L', self.local_off[s])
            if s.storage == 'param':
                return ('P', self.param_index[s])
            self.ref(s.label)
            return ('sym', s.label, 0)
        if k == 'str':
            self.ref(e.label)
            return ('sym', e.label, 0)
        if k == 'member':
            b = self.static_ptr(e.a)
            if b is not None:
                return self.shift(b, e.offset)
        if k == 'deref':
            return self.static_ptr(e.a)
        return None

    def static_ptr(self, p):
        k = p.kind
        if k == 'addr':
            return self.static_addr(p.a)
        if k == 'num':
            return ('sym', None, p.val & 0xFFFF)
        if k == 'cast' and p.a.type.is_ptr:
            return self.static_ptr(p.a)
        if k == 'binop' and p.op in ('+', '-') and p.type.is_ptr and p.b.kind == 'num':
            b = self.static_ptr(p.a)
            if b is not None:
                return self.shift(b, p.b.val if p.op == '+' else -p.b.val)
        return None

    def shift(self, a, off):
        if a[0] in ('L', 'P'):
            return (a[0], a[1] + off)
        return ('sym', a[1], a[2] + off)

    def is_regvar(self, e):
        return e.kind == 'var' and e.sym in self.regvar

    def frame_const(self, r, a):
        """Load the sp-offset of a frame address into r; returns False when the offset is 0."""
        if a[0] == 'L':
            v = a[1] + self.sp_delta
            if v == 0:
                return False
            self.const(r, v)
            return True
        self.emit('lli', f'r{r},@P{a[1]}+{self.sp_delta}@')
        return True

    def gen_addr(self, e):
        s = self.static_addr(e)
        if s is not None:
            return s
        if e.kind == 'deref':
            r, o = self.val(e.a)
            return ('reg', r, o)
        if e.kind == 'member':
            r, o = self.val(e.a)
            if e.offset:
                d = r if o else self.alloc()
                self.const(TMP, e.offset)
                self.emit('add', f'r{d},r{r},r7')
                return ('reg', d, True)
            return ('reg', r, o)
        raise CompileError('internal error: not an lvalue', e.tok)

    def addr_to_reg(self, a):
        """An owned register holding the address a."""
        if a[0] == 'reg':
            return self.own(a[1], a[2])
        r = self.alloc()
        if a[0] in ('L', 'P'):
            if self.frame_const(r, a):
                self.emit('add', f'r{r},r6,r{r}')
            else:
                self.move(r, 6)
        elif a[1] is None and -128 <= s16(a[2]) <= 127:
            self.const(r, a[2])
        else:
            self.emit('li', f'r{r},{addr_text(a[1], a[2])}')
        return r

    def addr_reg(self, a):
        """(register, owned) holding the address a: r6 or r7 for static addresses."""
        if a[0] == 'reg':
            return a[1], a[2]
        if a[0] in ('L', 'P'):
            if not self.frame_const(TMP, a):
                return 6, False
            self.emit('add', 'r7,r6,r7')
            return TMP, False
        if a[1] is None and -128 <= s16(a[2]) <= 127:
            self.const(TMP, a[2])
        else:
            self.emit('li', f'r7,{addr_text(a[1], a[2])}')
        return TMP, False

    def load(self, a, comment=None):
        r, o = self.addr_reg(a)
        d = r if o else self.alloc()
        self.emit('lw', f'r{d},(r{r})', comment)
        return d

    def store(self, a, v, comment=None):
        r, o = self.addr_reg(a)
        self.emit('sw', f'r{v},(r{r})', comment)
        self.done(r, o)

    # -- register needs (to decide when to spill) ---------------------------------------------

    def need(self, e):
        k = e.kind
        if k == 'regval' or self.is_regvar(e):
            return 0
        if k in ('num', 'str', 'var'):
            return 1
        if k == 'addr':
            return self.need_addr(e.a)
        if k in ('deref', 'member'):
            return self.need_addr(e)
        if k in ('cast', 'unary', 'not', 'bool'):
            return max(self.need(e.a), 1)
        if k == 'binop':
            if e.b.kind == 'num':
                return max(self.need(e.a), 2)
            n = max(self.need(e.a), self.need(e.b) + 1, 1)
            if self.is_helper(e):
                n = max(n, 2)
            return n
        if k == 'cmp':
            return max(self.need(e.a), self.need(e.b) + 1, 1)
        if k in ('logand', 'logor'):
            return 1 + max(self.need(e.a), self.need(e.b))
        if k == 'cond':
            return 1 + max(self.need(e.c), self.need(e.a), self.need(e.b))
        if k == 'assign':
            return 1 + max(self.need(e.b), self.need_addr(e.a))
        if k == 'incdec':
            return 1 if self.is_regvar(e.a) else self.need_addr(e.a) + 1
        if k == 'call':
            return 1
        if k == 'comma':
            return max(self.need(e.a), self.need(e.b))
        return 3

    def need_addr(self, e):
        if e.kind in ('var', 'str') or self.static_addr(e) is not None:
            return 1
        if e.kind in ('deref', 'member'):
            return max(self.need(e.a), 1)
        return 3

    def is_helper(self, e):
        op = e.op
        if op in HELPER_OPS:
            return True
        if op == '>>':
            return e.uns or e.b.kind != 'num'
        if op in ('/', '%'):
            return e.uns
        return False

    def has_call(self, e):
        """Does evaluating e call a function (which changes r1, r2)?"""
        if e.kind == 'call' or (e.kind == 'binop' and self.is_helper(e)):
            return True
        return any(self.has_call(c) for c in children(e))

    def pure(self, e):
        """No side effects: evaluating it later gives the same value."""
        if e.kind in ('call', 'assign', 'incdec'):
            return False
        return all(self.pure(c) for c in children(e))

    def gen_pair(self, a, b):
        if self.has_call(b) and not self.has_call(a) and self.pure(a):
            # the call first, so that a's value need not be kept across it
            y, yo = self.val(b)
            if yo and self.need(a) > len(self.free):
                self.push(y)
                self.release(y)
                x, xo = self.val(a)
                y = self.alloc()
                self.pop(y)
            else:
                x, xo = self.val(a)
            return x, xo, y, yo
        x, xo = self.val(a)
        if xo and self.need(b) > len(self.free):
            self.push(x)
            self.release(x)
            y, yo = self.val(b)
            x = self.alloc()
            self.pop(x)
        else:
            y, yo = self.val(b)
        return x, xo, y, yo

    def dest(self, x, xo, y=None, yo=False):
        if xo:
            return x
        if yo:
            return y
        return self.alloc()

    # -- expressions --------------------------------------------------------------------------

    def val(self, e):
        """(register, owned) holding the value of e. A register variable is not owned: read it only."""
        if self.is_regvar(e):
            return self.regvar[e.sym], False
        if e.kind == 'regval':
            return e.reg, e.owned
        if e.kind == 'cast' and not e.type.is_void:
            return self.val(e.a)
        if e.kind == 'comma':
            self.gen_void(e.a)
            return self.val(e.b)
        return self.gen(e), True

    def gen(self, e):
        """Code for the value of e; returns a register the caller owns."""
        k = e.kind
        if k == 'regval' or self.is_regvar(e) or (k == 'cast' and not e.type.is_void):
            r, o = self.val(e)
            return self.own(r, o)
        if k == 'num':
            r = self.alloc()
            if e.type.is_ptr and not -128 <= s16(e.val) <= 127:
                self.emit('li', f'r{r},0x{e.val & 0xFFFF:04x}')
            else:
                self.const(r, e.val)
            return r
        if e.type is not None and (e.type.is_array or e.type.is_func or e.type.is_struct) and \
                k in ('var', 'str', 'deref', 'member'):
            return self.addr_to_reg(self.gen_addr(e))
        if k == 'var':
            return self.load(self.static_addr(e), self.var_name(e))
        if k == 'addr':
            return self.addr_to_reg(self.gen_addr(e.a))
        if k in ('deref', 'member'):
            return self.load(self.gen_addr(e), 'volatile' if e.type.volatile else None)
        if k == 'cast':
            self.gen_void(e.a)
            return None
        if k == 'unary':
            x, xo = self.val(e.a)
            d = self.dest(x, xo)
            self.emit('sub', f'r{d},r0,r{x}')
            if e.op == '~':
                self.const(TMP, 1)
                self.emit('sub', f'r{d},r{d},r7', '~x = -x-1')
            return d
        if k in ('not', 'bool'):
            x, xo = self.val(e.a)
            d = self.dest(x, xo)
            skip, end = self.new_label(), self.new_label()
            self.emit('bz', f'r{x},{skip}')
            self.const(d, 0 if k == 'not' else 1)
            self.emit('b', end)
            self.label(skip)
            self.const(d, 1 if k == 'not' else 0)
            self.label(end)
            return d
        if k in ('cmp', 'logand', 'logor'):
            false, done = self.new_label(), self.new_label()
            self.gen_cond(e, false, False)
            r = self.alloc()                 # after the test, so that the test has every register
            self.const(r, 1)
            self.emit('b', done)
            self.label(false)
            self.const(r, 0)
            self.label(done)
            return r
        if k == 'binop':
            return self.gen_binop(e)
        if k == 'assign':
            return self.gen_assign(e, True)
        if k == 'incdec':
            return self.gen_incdec(e, True)
        if k == 'call':
            return self.gen_call(e, True)
        if k == 'cond':
            return self.gen_ternary(e)
        if k == 'comma':
            self.gen_void(e.a)
            return self.gen(e.b)
        raise CompileError(f'internal error: cannot generate {k}', e.tok)

    def gen_void(self, e):
        """Code for e when its value is not needed."""
        k = e.kind
        if k == 'assign':
            self.gen_assign(e, False)
        elif k == 'incdec':
            self.gen_incdec(e, False)
        elif k == 'call':
            self.gen_call(e, False)
        elif k == 'comma':
            self.gen_void(e.a)
            self.gen_void(e.b)
        elif k == 'cast':
            self.gen_void(e.a)
        elif k == 'var' and e.type.volatile:
            self.release(self.gen(e))        # a volatile variable is read even when unused
        elif k in ('num', 'str', 'var', 'addr', 'regval'):
            pass
        elif k == 'cond':
            other, end = self.new_label(), self.new_label()
            self.gen_cond(e.c, other, False)
            self.gen_void(e.a)
            self.emit('jmp', end)
            self.label(other)
            self.gen_void(e.b)
            self.label(end)
        elif k in ('logand', 'logor'):
            skip = self.new_label()
            self.gen_cond(e.a, skip, k == 'logor')
            self.gen_void(e.b)
            self.label(skip)
        else:
            r = self.gen(e)
            if r is not None:
                self.release(r)

    def into(self, e, target):
        """Evaluate e into the register target (a register variable)."""
        r, o = self.val(e)
        if r == target:
            return
        if o and self.lines and self.lines[-1][0] == 'ins':
            _, op, args, com = self.lines[-1]
            if op in WRITES and op != 'jalr' and dest_reg(op, args) == r:
                rest = args.split(',', 1)[1]
                self.lines[-1] = ('ins', op, f'r{target},{rest}', com)
                self.release(r)
                return
        self.move(target, r)
        self.done(r, o)

    def gen_binop(self, e):
        op, a, b = e.op, e.a, e.b
        if a.kind == 'num' and op in ('+', '*', '&', '|', '^') and b.kind != 'num':
            a, b = b, a
        if b.kind == 'num':
            r = self.gen_binop_const(e, op, a, b.val)
            if r is not None:
                return r
        x, xo, y, yo = self.gen_pair(a, b)
        if self.is_helper(e):
            if op in HELPER_OPS:
                return self.helper(HELPER_OPS[op], x, xo, y, yo)
            if op == '>>':
                return self.helper('rt_shr' if e.uns else 'rt_sar', x, xo, y, yo)
            return self.helper('rt_udiv', x, xo, y, yo, result=1 if op == '/' else 2)
        d = self.dest(x, xo, y, yo)
        mnem = {'+': 'add', '-': 'sub', '*': 'mul', '/': 'div', '%': 'rem'}[op]
        self.emit(mnem, f'r{d},r{x},r{y}')
        if d != x:
            self.done(x, xo)
        if d != y:
            self.done(y, yo)
        return d

    def gen_binop_const(self, e, op, a, c):
        """Binary operation with a constant right operand, or None to do it the general way."""
        c16 = c & 0xFFFF
        if op in ('+', '-'):
            x, xo = self.val(a)
            if c16 == 0:
                return self.own(x, xo)
            d = self.dest(x, xo)
            self.const(TMP, c)
            self.emit('add' if op == '+' else 'sub', f'r{d},r{x},r7')
            return d
        if op == '*':
            x, xo = self.val(a)
            if c16 == 1:
                return self.own(x, xo)
            d = self.dest(x, xo)
            if c16 == 0:
                self.const(d, 0)
            else:
                self.const(TMP, c)
                self.emit('mul', f'r{d},r{x},r7')
            return d
        if op in ('/', '%') and not e.uns and c16 != 0:
            x, xo = self.val(a)
            d = self.dest(x, xo)
            if c16 == 1:
                if op == '%':
                    self.const(d, 0)
                else:
                    self.move(d, x)
                return d
            self.const(TMP, c)
            self.emit('div' if op == '/' else 'rem', f'r{d},r{x},r7')
            return d
        if op == '%' and e.uns and log2_exact(c) is not None and 0 < log2_exact(c) <= 14:
            return self.mask(a, log2_exact(c))
        if op == '<<':
            x, xo = self.val(a)
            if c16 == 0:
                return self.own(x, xo)
            d = self.dest(x, xo)
            if c16 >= 16:
                self.const(d, 0)
            else:
                self.const(TMP, 1 << c16)
                self.emit('mul', f'r{d},r{x},r7', f'<< {c16}')
            return d
        if op == '>>' and not e.uns:
            x, xo = self.val(a)
            if c16 == 0:
                return self.own(x, xo)
            d = self.dest(x, xo)
            if c16 >= 15:
                neg, end = self.new_label(), self.new_label()
                self.emit('bltz', f'r{x},{neg}')
                self.const(d, 0)
                self.emit('b', end)
                self.label(neg)
                self.const(d, -1)
                self.label(end)
                return d
            t = self.alloc()
            fix, end = self.new_label(), self.new_label()
            self.const(TMP, 1 << c16, f'>> {c16}: divide, rounding down')
            self.emit('rem', f'r{t},r{x},r7')
            self.emit('div', f'r{d},r{x},r7')
            self.emit('bltz', f'r{t},{fix}')
            self.emit('b', end)
            self.label(fix)
            self.const(TMP, 1)
            self.emit('sub', f'r{d},r{d},r7')
            self.label(end)
            self.release(t)
            return d
        if op == '&':
            if c16 == 0xFFFF:
                x, xo = self.val(a)
                return self.own(x, xo)
            if c16 == 0:
                x, xo = self.val(a)
                d = self.dest(x, xo)
                self.const(d, 0)
                return d
            k = log2_exact(c16 + 1)
            if k is not None and 1 <= k <= 14:
                return self.mask(a, k)
        return None

    def mask(self, a, k):
        """a & (2**k - 1), using the remainder of a division."""
        x, xo = self.val(a)
        d = self.dest(x, xo)
        fix, end = self.new_label(), self.new_label()
        self.const(TMP, 1 << k, f'& 0x{(1 << k) - 1:x}')
        self.emit('rem', f'r{d},r{x},r7')
        self.emit('bltz', f'r{d},{fix}')
        self.emit('b', end)
        self.label(fix)
        self.emit('add', f'r{d},r{d},r7')
        self.label(end)
        return d

    def helper(self, name, x, xo, y, yo, result=1):
        """Call a runtime routine with x in r1 and y in r2; returns an owned result register."""
        self.g.helpers.add(name)
        self.ref(name)
        self.touched.add(3)                  # the routine changes r3: our caller expects it kept
        keep = [r for r in HELPER_CLOBBERS
                if (r in self.busy() or r in self.regvar.values())
                and not (xo and r == x) and not (yo and r == y)]
        for r in keep:
            self.push(r)
        self.pmove([(1, x), (2, y)])
        self.emit('li', f'r7,{name}')
        self.emit('jalr', 'r7,r7,r0')
        self.done(x, xo)
        self.done(y, yo)
        if result in self.free and result not in keep:
            res = result
            self.claim(res)
        else:
            res = self.alloc()
            self.move(res, result)
        for r in reversed(keep):
            self.pop(r)
        return res

    def gen_call(self, e, want):
        live = [r for r in self.busy() if r in CALLER_SAVED]
        for r in live:
            self.push(r)
        saved = list(self.free)
        self.free = sorted(self.free + live, key=TEMP_ORDER.index)
        ft = e.f.type.base
        reg_arg = not ft.varargs and len(e.args) >= 1
        stack_args = e.args[1:] if reg_arg else e.args
        first = 2 if reg_arg else 1
        n = len(stack_args)
        name = e.direct.name if e.direct else None
        if n:
            self.adjust_sp(-n)
        for i, a in enumerate(stack_args):
            r, o = self.val(a)
            if i == 0:
                self.emit('sw', f'r{r},(r6)', f'argument {first}')
            else:
                self.const(TMP, i)
                self.emit('add', 'r7,r6,r7')
                self.emit('sw', f'r{r},(r7)', f'argument {i + first}')
            self.done(r, o)
        f, fo = None, False
        if e.direct is None:
            f, fo = self.val(e.f)
            if reg_arg and f == 1:
                t = self.alloc()
                self.move(t, 1)
                self.release(1)
                f = t
        if reg_arg:
            r, o = self.val(e.args[0])
            if r == 1:
                self.done(r, o)
            else:
                self.move(1, r, 'argument 1')
                self.done(r, o)
        if e.direct is not None:
            self.ref(e.direct.label)
            self.emit('li', f'r7,{e.direct.label}')
            self.emit('jalr', 'r7,r7,r0', f'call {name}()')
        else:
            self.emit('jalr', f'r7,r{f},r0', 'call through a pointer')
            self.done(f, fo)
        if n:
            self.adjust_sp(n)
        self.free = saved
        res = None
        if want and not e.type.is_void:
            res = self.alloc()
            self.move(res, 1)
        for r in reversed(live):
            self.pop(r)
        return res

    def gen_ternary(self, e):
        other, end = self.new_label(), self.new_label()
        self.gen_cond(e.c, other, False)
        ra = self.gen(e.a)
        self.emit('jmp', end)
        self.label(other)
        self.release(ra)
        rb = self.gen(e.b)
        if rb != ra:
            self.move(ra, rb)
            self.release(rb)
            self.claim(ra)
        self.label(end)
        return ra

    def gen_assign(self, e, want):
        lhs, rhs = e.a, e.b
        if e.type.is_struct:
            if want:
                raise CompileError('the value of a struct assignment cannot be used', e.tok)
            return self.struct_copy(lhs, rhs)
        name = self.var_name(lhs)
        if self.is_regvar(lhs):
            reg = self.regvar[lhs.sym]
            if e.op == '=':
                self.into(rhs, reg)
            else:
                t = promote(lhs.type) if lhs.type.is_int else lhs.type
                op = Node('binop', e.tok, t, op=e.op, a=Node('regval', e.tok, lhs.type, reg=reg, owned=False),
                          b=rhs, uns=getattr(e, 'uns', False))
                self.into(op, reg)
            return self.own(reg, False) if want else None
        if e.op == '=':
            a = self.static_addr(lhs)
            if rhs.kind == 'num' and rhs.val == 0 and not want:
                if a is None:
                    a = self.gen_addr(lhs)
                self.store(a, 0, name)
                return None
            v, vo = self.val(rhs)
            if a is None:
                if vo and self.need_addr(lhs) > len(self.free):
                    self.push(v)
                    self.release(v)
                    a = self.gen_addr(lhs)
                    v = self.alloc()
                    self.pop(v)
                else:
                    a = self.gen_addr(lhs)
            self.store(a, v, name)
        else:
            a = self.static_addr(lhs)
            rhs_node = rhs
            if a is not None and self.has_call(rhs):
                y, yo = self.val(rhs)            # the call first: the variable is loaded after it
                rhs_node = Node('regval', e.tok, rhs.type, reg=y, owned=yo)
            if a is None:
                a = ('reg', self.addr_to_reg(self.gen_addr(lhs)), True)
                cur = self.alloc()
                self.emit('lw', f'r{cur},(r{a[1]})')
            else:
                cur = self.load(a, name)
            t = promote(lhs.type) if lhs.type.is_int else lhs.type
            op = Node('binop', e.tok, t, op=e.op, a=Node('regval', e.tok, lhs.type, reg=cur, owned=True),
                      b=rhs_node, uns=getattr(e, 'uns', False))
            v = self.gen_binop(op)
            vo = True
            self.store(a, v, name)
        if want:
            return self.own(v, vo)
        self.done(v, vo)
        return None

    def var_name(self, e):
        if e.kind != 'var':
            return 'volatile' if e.type.volatile else None
        return e.sym.name + (' (volatile)' if e.type.volatile else '')

    def gen_incdec(self, e, want):
        name = self.var_name(e.a)
        if self.is_regvar(e.a):
            reg = self.regvar[e.a.sym]
            old = None
            if e.post and want:
                old = self.alloc()
                self.move(old, reg)
            self.const(TMP, e.step)
            self.emit('add', f'r{reg},r{reg},r7', f'{name}{e.op}')
            if not want:
                return None
            return old if old is not None else self.own(reg, False)
        a = self.static_addr(e.a)
        if a is None:
            a = ('reg', self.addr_to_reg(self.gen_addr(e.a)), True)
            v = self.alloc()
            self.emit('lw', f'r{v},(r{a[1]})')
        else:
            v = self.load(a, name)
        if e.post and want:
            n = self.alloc()
            self.const(n, e.step)
            self.emit('add', f'r{n},r{v},r{n}')
            self.store(a, n, name)
            self.release(n)
            return v
        if self.free and a[0] != 'reg':
            k = self.alloc()                     # keep r7 for the address
            self.const(k, e.step)
            self.emit('add', f'r{v},r{v},r{k}')
            self.release(k)
        else:
            self.const(TMP, e.step)
            self.emit('add', f'r{v},r{v},r7')
        self.store(a, v, name)
        if want:
            return v
        self.release(v)
        return None

    def scratch(self, avoid):
        """A register for a short sequence: a free one, or one saved on the stack (borrowed)."""
        if self.free:
            return self.alloc(), False
        for r in (1, 2, 3, 4, 5):
            if r not in avoid:
                self.push(r, 'borrow')
                return r, True
        raise CompileError('internal error: no register to borrow', self.tok)

    def struct_copy(self, lhs, rhs):
        n = lhs.type.size()
        s, so = self.val(rhs)
        s = self.own(s, so)
        d = self.addr_to_reg(self.gen_addr(lhs))
        t, tb = self.scratch((s, d))
        self.comment(f'copy {n} words')
        if n <= 6:
            self.const(TMP, 1)
            for i in range(n):
                self.emit('lw', f'r{t},(r{s})')
                self.emit('sw', f'r{t},(r{d})')
                if i < n - 1:
                    self.emit('add', f'r{s},r{s},r7')
                    self.emit('add', f'r{d},r{d},r7')
            c, cb = None, False
        else:
            c, cb = self.scratch((s, d, t))
            loop = self.new_label()
            self.const(c, n)
            self.const(TMP, 1)
            self.label(loop)
            self.emit('lw', f'r{t},(r{s})')
            self.emit('sw', f'r{t},(r{d})')
            self.emit('add', f'r{s},r{s},r7')
            self.emit('add', f'r{d},r{d},r7')
            self.emit('sub', f'r{c},r{c},r7')
            self.emit('bnz', f'r{c},{loop}')
        for r, b in ((c, cb), (t, tb)):
            if r is None:
                continue
            if b:
                self.pop(r, 'borrowed')
            else:
                self.release(r)
        self.release(s)
        self.release(d)
        return None

    # -- conditions ---------------------------------------------------------------------------

    def gen_cond(self, e, label, jump_if):
        """Jump to label when the truth of e equals jump_if, otherwise fall through."""
        k = e.kind
        if k == 'num':
            if bool(e.val) == jump_if:
                self.emit('jmp', label)
            return
        if k == 'not':
            return self.gen_cond(e.a, label, not jump_if)
        if k == 'bool' or (k == 'cast' and e.type.is_scalar):
            return self.gen_cond(e.a, label, jump_if)
        if k == 'logand' or k == 'logor':
            if (k == 'logand') == jump_if:
                skip = self.new_label()
                self.gen_cond(e.a, skip, not jump_if)
                self.gen_cond(e.b, label, jump_if)
                self.label(skip)
            else:
                self.gen_cond(e.a, label, jump_if)
                self.gen_cond(e.b, label, jump_if)
            return
        if k == 'comma':
            self.gen_void(e.a)
            return self.gen_cond(e.b, label, jump_if)
        if k == 'cmp':
            return self.gen_cmp(e, label, jump_if)
        r, o = self.val(e)
        self.emit('jnz' if jump_if else 'jz', f'r{r},{label}')
        self.done(r, o)

    def gen_cmp(self, e, label, jump_if):
        op = e.op if jump_if else NEGATE[e.op]
        a, b = e.a, e.b
        if op in ('==', '!='):
            j = 'jz' if op == '==' else 'jnz'
            if b.kind == 'num' and b.val == 0:
                r, o = self.val(a)
            elif a.kind == 'num' and a.val == 0:
                r, o = self.val(b)
            elif b.kind == 'num':
                x, xo = self.val(a)
                r, o = self.dest(x, xo), True
                self.const(TMP, b.val)
                self.emit('sub', f'r{r},r{x},r7')
            else:
                x, xo, y, yo = self.gen_pair(a, b)
                r, o = self.dest(x, xo, y, yo), True
                self.emit('sub', f'r{r},r{x},r{y}')
                if r != x:
                    self.done(x, xo)
                if r != y:
                    self.done(y, yo)
            self.emit(j, f'r{r},{label}')
            self.done(r, o)
            return
        if op == '<':
            x, y, want = a, b, True
        elif op == '>=':
            x, y, want = a, b, False
        elif op == '>':
            x, y, want = b, a, True
        else:
            x, y, want = b, a, False
        self.gen_lt(x, y, e.uns, label, want)

    def gen_lt(self, x, y, uns, label, want):
        """Jump to label when (x < y) == want. Correct for all 16-bit values (no overflow)."""
        def zero(n):
            return n.kind == 'num' and n.val & 0xFFFF == 0

        if not uns and zero(y):                          # x < 0
            r, o = self.val(x)
            if want:
                self.emit('jltz', f'r{r},{label}')
            else:
                skip = self.new_label()
                self.emit('bltz', f'r{r},{skip}')
                self.emit('jmp', label)
                self.label(skip)
            self.done(r, o)
            return
        if not uns and zero(x):                          # 0 < y
            r, o = self.val(y)
            if want:
                skip = self.new_label()
                self.emit('bltz', f'r{r},{skip}')
                self.emit('jnz', f'r{r},{label}')
                self.label(skip)
            else:
                self.emit('jltz', f'r{r},{label}')
                self.emit('jz', f'r{r},{label}')
            self.done(r, o)
            return
        if uns and zero(y):                              # x < 0 is never true
            self.gen_void(x)
            if not want:
                self.emit('jmp', label)
            return
        if uns and zero(x):                              # 0 < y: y != 0
            r, o = self.val(y)
            self.emit('jnz' if want else 'jz', f'r{r},{label}')
            self.done(r, o)
            return
        if x.kind == 'num' and y.kind != 'num':          # c < y is !(y < c+1)
            c = x.val & 0xFFFF
            if c == (0xFFFF if uns else 0x7FFF):         # nothing is above the largest value
                self.gen_void(y)
                if not want:
                    self.emit('jmp', label)
                return
            c1 = Node('num', x.tok, x.type, val=(c + 1) & 0xFFFF)
            return self.gen_lt(y, c1, uns, label, not want)
        skip = self.new_label()
        t_lab, f_lab = (label, skip) if want else (skip, label)
        same = self.new_label()
        if y.kind == 'num':
            c = y.val & 0xFFFF
            rx, xo = self.val(x)
            # the sign (or top bit) of the constant is known: only one test is needed first
            top = c >= 0x8000
            if not uns and not top:                      # c > 0: x < 0 means x < c
                self.emit('jltz', f'r{rx},{t_lab}')
            elif not uns:                                # c < 0: x >= 0 means x > c
                self.emit('bltz', f'r{rx},{same}')
                self.emit('jmp', f_lab)
            elif not top:                                # x >= 0x8000 means x > c
                self.emit('jltz', f'r{rx},{f_lab}')
            else:                                        # x < 0x8000 means x < c
                self.emit('bltz', f'r{rx},{same}')
                self.emit('jmp', t_lab)
            self.label(same)
            d = self.dest(rx, xo)
            self.const(TMP, c)
            self.emit('sub', f'r{d},r{rx},r7')
            self.emit('jltz', f'r{d},{t_lab}')
            self.release(d)
        else:
            rx, xo, ry, yo = self.gen_pair(x, y)
            xneg = self.new_label()
            if not uns:
                self.emit('bltz', f'r{rx},{xneg}')       # x < 0 ?
                self.emit('jltz', f'r{ry},{f_lab}')      # x >= 0 > y
                self.emit('b', same)
                self.label(xneg)
                self.emit('bltz', f'r{ry},{same}')
                self.emit('jmp', t_lab)                  # x < 0 <= y
            else:
                self.emit('bltz', f'r{rx},{xneg}')       # x >= 0x8000 ?
                self.emit('jltz', f'r{ry},{t_lab}')      # x < 0x8000 <= y
                self.emit('b', same)
                self.label(xneg)
                self.emit('bltz', f'r{ry},{same}')
                self.emit('jmp', f_lab)                  # x >= 0x8000 > y
            self.label(same)                             # same sign: x - y cannot overflow
            d = self.dest(rx, xo, ry, yo)
            self.emit('sub', f'r{d},r{rx},r{ry}')
            self.emit('jltz', f'r{d},{t_lab}')
            for r, o in ((rx, xo), (ry, yo)):
                if r != d:
                    self.done(r, o)
            self.release(d)
        if f_lab == label:
            self.emit('jmp', label)
        self.label(skip)

    # -- statements ---------------------------------------------------------------------------

    def gen_stmt(self, s):
        k = s.kind
        if k not in ('block', 'case', 'default', 'label', 'empty', 'decl'):
            self.mark_line(s.tok)
        if k == 'block':
            for it in s.items:
                self.gen_stmt(it)
        elif k == 'decl':
            for sym, init in s.items:
                if init is not None:
                    self.mark_line(sym.tok)
                    self.local_init(sym, init)
        elif k == 'expr':
            self.gen_void(s.e)
        elif k == 'if':
            other = self.new_label()
            self.gen_cond(s.c, other, False)
            self.gen_stmt(s.then)
            if s.other is not None:
                end = self.new_label()
                self.emit('jmp', end)
                self.label(other)
                self.gen_stmt(s.other)
                self.label(end)
            else:
                self.label(other)
        elif k == 'while':
            top, test, end = self.new_label(), self.new_label(), self.new_label()
            self.emit('jmp', test)
            self.label(top)
            self.loop_body(s.body, end, test)
            self.label(test)
            self.mark_line(s.tok)
            self.gen_cond(s.c, top, True)
            self.label(end)
        elif k == 'do':
            top, test, end = self.new_label(), self.new_label(), self.new_label()
            self.label(top)
            self.loop_body(s.body, end, test)
            self.label(test)
            self.gen_cond(s.c, top, True)
            self.label(end)
        elif k == 'for':
            if s.init is not None:
                self.gen_stmt(s.init)
            top, cont, test, end = (self.new_label() for _ in range(4))
            if s.c is not None:
                self.emit('jmp', test)
            self.label(top)
            self.loop_body(s.body, end, cont)
            self.label(cont)
            if s.step is not None:
                self.mark_line(s.tok)
                self.gen_void(s.step)
            self.label(test)
            if s.c is not None:
                self.gen_cond(s.c, top, True)
            else:
                self.emit('jmp', top)
            self.label(end)
        elif k == 'switch':
            r, o = self.val(s.e)
            end = self.new_label()
            for c in s.cases:
                c.asm = self.new_label()
                if c.val & 0xFFFF == 0:
                    self.emit('jz', f'r{r},{c.asm}', 'case 0')
                else:
                    self.const(TMP, c.val)
                    self.emit('sub', f'r7,r{r},r7')
                    self.emit('jz', f'r7,{c.asm}', f'case {c.val}')
            self.done(r, o)
            if s.default is not None:
                s.default.asm = self.new_label()
                self.emit('jmp', s.default.asm, 'default')
            else:
                self.emit('jmp', end)
            self.breaks.append(end)
            self.gen_stmt(s.body)
            self.breaks.pop()
            self.label(end)
        elif k in ('case', 'default'):
            self.label(s.asm)
            self.gen_stmt(s.stmt)
        elif k == 'break':
            self.emit('jmp', self.breaks[-1], 'break')
        elif k == 'continue':
            self.emit('jmp', self.conts[-1], 'continue')
        elif k == 'return':
            if s.e is not None:
                self.into(s.e, 1)
                if 1 in self.temps and 1 not in self.free:
                    self.release(1)
            self.emit('jmp', self.ret_label, 'return')
        elif k == 'goto':
            if s.label.asm is None:
                s.label.asm = self.new_label()
            self.emit('jmp', s.label.asm, f'goto {s.label.name}')
        elif k == 'label':
            if s.label.asm is None:
                s.label.asm = self.new_label()
            self.label(s.label.asm)
            self.comment(f'{s.label.name}:')
            self.gen_stmt(s.stmt)
        elif k == 'asm':
            self.lines.append(('asm', s.text))
        elif k == 'empty':
            pass
        else:
            raise CompileError(f'internal error: statement {k}', s.tok)
        if self.busy() or self.sp_delta:
            raise CompileError('internal error: registers or stack left in use', s.tok)

    def loop_body(self, body, brk, cont):
        self.breaks.append(brk)
        self.conts.append(cont)
        self.gen_stmt(body)
        self.breaks.pop()
        self.conts.pop()

    def local_init(self, sym, init):
        t = sym.type
        if sym in self.regvar:
            for off, e in init:
                self.into(e, self.regvar[sym])
            return
        base = self.local_off[sym]
        if not (t.is_array or t.is_struct):
            for off, e in init:
                if e.kind == 'num' and e.val == 0:
                    self.store(('L', base + off), 0, sym.name)
                    continue
                r, o = self.val(e)
                self.store(('L', base + off), r, sym.name)
                self.done(r, o)
            return
        size = t.size()
        if self.g.memory.rodata_bank() and size >= 5:
            image = self.rom_image(init, size)
            if image is not None and sum(1 for v in image if v != 0) >= 4:
                self.copy_from_rom(sym, base, size, image)
                return
        given = {off for off, e in init}
        zeros = [o for o in range(size) if o not in given]
        cleared = False
        if len(zeros) > 6:
            p, c = self.alloc(), self.alloc()
            loop = self.new_label()
            self.comment(f'{sym.name}: set {size} words to 0')
            if self.frame_const(p, ('L', base)):
                self.emit('add', f'r{p},r6,r{p}')
            else:
                self.move(p, 6)
            self.const(c, size)
            self.const(TMP, 1)
            self.label(loop)
            self.emit('sw', f'r0,(r{p})')
            self.emit('add', f'r{p},r{p},r7')
            self.emit('sub', f'r{c},r{c},r7')
            self.emit('bnz', f'r{c},{loop}')
            self.release(p)
            self.release(c)
            cleared = True
        else:
            for o in zeros:
                self.store(('L', base + o), 0)
        for off, e in init:
            if e.kind == 'num' and e.val == 0:
                if not cleared:
                    self.store(('L', base + off), 0)
                continue
            r, o = self.val(e)
            self.store(('L', base + off), r, f'{sym.name}[{off}]')
            self.done(r, o)

    def rom_image(self, init, size):
        """The words of a local initialiser when they are all constants (for a table in ROM), else None."""
        words = [0] * size
        for off, e in init:
            v = rom_value(e)
            if v is None:
                return None
            if isinstance(v, tuple):
                self.ref(v[0])
            words[off] = v
        return words

    def copy_from_rom(self, sym, base, size, image):
        """Copy the initial value of a local array or struct from a table in ROM."""
        label = 'T' + self.g.new_label()[1:]
        self.g.func_tables.setdefault(self.fd.sym.label, []).append((label, image, f'initial value of {sym.name}'))
        regs = []
        for _ in range(4):
            regs.append(self.scratch(tuple(r for r, _ in regs)))
        (p, _), (q, _), (c, _), (t, _) = regs
        self.comment(f'{sym.name}: copy its {size} words of initial value from ROM')
        self.emit('li', f'r{q},{label}')
        if self.frame_const(p, ('L', self.local_off[sym])):
            self.emit('add', f'r{p},r6,r{p}')
        else:
            self.move(p, 6)
        self.const(c, size)
        self.const(TMP, 1)
        loop = self.new_label()
        self.label(loop)
        self.emit('lw', f'r{t},(r{q})')
        self.emit('sw', f'r{t},(r{p})')
        self.emit('add', f'r{p},r{p},r7')
        self.emit('add', f'r{q},r{q},r7')
        self.emit('sub', f'r{c},r{c},r7')
        self.emit('bnz', f'r{c},{loop}')
        for r, borrowed in reversed(regs):
            if borrowed:
                self.pop(r, 'borrowed')
            else:
                self.release(r)

    # -- the function -------------------------------------------------------------------------

    def generate(self):
        fd = self.fd
        sym = fd.sym
        self.tok = fd.tok
        self.last_line = (fd.tok.file, fd.tok.line)      # the header comment names the function
        self.gen_stmt(fd.body)
        body = self.lines
        saved = [r for r in (5, 4, 3) if r in self.touched]
        L, S = self.frame, len(saved)
        N = L + S + 1
        self.lines = []
        src = SOURCES.get(fd.tok.file)
        if src and 0 < fd.tok.line <= len(src):
            self.comment(f'{fd.tok.line}: {src[fd.tok.line - 1].strip()}')
        else:
            self.comment(f'function {sym.type.str_with(sym.name)}')
        if self.regvar:
            names = ', '.join(f'{s.name} in r{r}' for s, r in sorted(self.regvar.items(), key=lambda x: -x[1]))
            self.comment(f'register variables: {names}')
        if L:
            names = ', '.join(f'{s.name} at sp+{o}' for s, o in self.local_off.items())
            self.comment(f'local variables: {names}')
        self.label(sym.label)
        self.const(2, -N, f'prologue: {N} word{"s" if N > 1 else ""} of stack frame')
        self.emit('add', 'r6,r6,r2')
        if L + S == 0:
            self.emit('sw', 'r7,(r6)', 'return address')
        else:
            self.const(2, L + S)
            self.emit('add', 'r2,r6,r2')
            self.emit('sw', 'r7,(r2)', 'return address')
            if S:
                self.const(TMP, -1)
                for r in saved:
                    self.emit('add', 'r2,r2,r7')
                    self.emit('sw', f'r{r},(r2)', f'save r{r}')
        if self.first is not None:
            if self.first in self.regvar:
                self.move(self.regvar[self.first], 1, f'{self.first.name} (argument 1)')
            else:
                self.store(('L', self.local_off[self.first]), 1, f'{self.first.name} (argument 1)')
        for s, reg in self.regvar.items():
            if s.storage == 'param' and s is not self.first:
                self.emit('lli', f'r7,@P{self.param_index[s]}+0@')
                self.emit('add', 'r7,r6,r7')
                self.emit('lw', f'r{reg},(r7)', s.name)
        prologue = self.lines
        self.lines = []
        self.label(self.ret_label)
        if L + S == 0:
            self.emit('lw', 'r7,(r6)', 'epilogue: return address')
            self.const(2, 1)
            self.emit('add', 'r6,r6,r2')
        else:
            if L:
                self.const(2, L, 'epilogue')
                self.emit('add', 'r2,r6,r2')
            else:
                self.emit('add', 'r2,r6,r0', 'epilogue')
            self.const(TMP, 1)
            for r in reversed(saved):
                self.emit('lw', f'r{r},(r2)', f'restore r{r}')
                self.emit('add', 'r2,r2,r7')
            self.emit('add', 'r6,r2,r7')
            self.emit('lw', 'r7,(r2)', 'return address')
        self.emit('jalr', 'r0,r7,r0', 'return')
        lines = prologue + body + self.lines
        lines = resolve_params(lines, N)
        return peephole(lines)


def resolve_params(lines, n):
    """Replace @Pk+d@ (parameter k with sp moved by d) by its offset from sp."""
    out = []
    for ln in lines:
        if ln[0] == 'ins' and '@P' in ln[2]:
            op, args = ln[1], ln[2]
            reg, ph = args.split(',', 1)
            k, d = ph.strip('@')[1:].split('+')
            v = n + int(k) + int(d)
            op = 'lli' if -128 <= v <= 127 else 'li'
            ln = ('ins', op, f'{reg},{v}', ln[3])
        out.append(ln)
    return out


# ----------------------------------------------------------------------------------------------
# Peephole optimisation

INVERSE = {'jz': 'jnz', 'jnz': 'jz', 'bz': 'bnz', 'bnz': 'bz'}


def peephole(lines):
    changed = True
    while changed:
        changed = False
        # labels nothing jumps to
        used = set()
        for ln in lines:
            if ln[0] == 'ins' and ln[1] in ('jmp', 'jz', 'jnz', 'jltz', 'b', 'bz', 'bnz', 'bltz', 'li'):
                used.add(ln[2].split(',')[-1])
            elif ln[0] == 'asm':
                used.update(ln[1].replace(',', ' ').split())
        lines = [ln for ln in lines if not (ln[0] == 'label' and ln[1].startswith('L') and ln[1] not in used)]
        out = []
        r7 = None                       # what r7 holds: ('c', text) or ('sp', text)
        last_store = None               # (register, sp-offset) of 'sw rX,(r7)' with r7 = sp+offset
        i = 0
        n = len(lines)
        while i < n:
            ln = lines[i]
            kind = ln[0]
            if kind == 'ins':
                op, args = ln[1], ln[2]
                nxt = lines[i + 1] if i + 1 < n else None
                if op in ('jmp', 'b') and _next_label_is(lines, i + 1, args):
                    changed = True
                    i += 1
                    continue
                # 'jz r,A / jmp B / A:' is 'jnz r,B / A:'
                j = i + 1
                while j < n and lines[j][0] == 'comment':
                    j += 1
                jn = lines[j] if j < n else None
                if op in INVERSE and jn and jn[0] == 'ins' and jn[1] in ('jmp', 'b') and \
                        _next_label_is(lines, j + 1, args.split(',')[1]):
                    reg = args.split(',')[0]
                    inv = INVERSE[op]
                    if jn[1] == 'jmp':
                        inv = 'j' + inv[1:]
                    out.extend(lines[i + 1:j])
                    out.append(('ins', inv, f'{reg},{jn[2]}', jn[3] or ln[3]))
                    changed = True
                    i = j + 1
                    r7 = None
                    last_store = None
                    continue
                if op == 'add':
                    p = args.split(',')
                    if p[2] == 'r0' and p[0] == p[1]:
                        changed = True
                        i += 1
                        continue
                if op in ('lli', 'li') and args.startswith('r7,'):
                    val = ('c', args[3:])
                    if nxt and nxt[0] == 'ins' and nxt[1] == 'add' and nxt[2] == 'r7,r6,r7':
                        if r7 == ('sp', args[3:]):
                            changed = True
                            i += 2
                            continue
                    elif r7 == val:
                        changed = True
                        i += 1
                        continue
                if op == 'lw' and args.endswith(',(r7)') and r7 and r7[0] == 'sp' and \
                        last_store == (args.split(',')[0], r7[1]) and 'volatile' not in (ln[3] or ''):
                    changed = True
                    i += 1
                    continue
                out.append(ln)
                d = dest_reg(op, args)
                if op in ('lli', 'li') and args.startswith('r7,'):
                    r7 = ('c', args[3:])
                elif op == 'add' and args == 'r7,r6,r7' and r7 and r7[0] == 'c':
                    r7 = ('sp', r7[1])
                elif d == 7 or op in ('jmp', 'jz', 'jnz', 'jltz'):
                    r7 = None
                elif d == 6 and r7 and r7[0] == 'sp':
                    r7 = None
                if op == 'sw' and args.endswith(',(r7)') and r7 and r7[0] == 'sp':
                    last_store = (args.split(',')[0], r7[1])
                elif op == 'sw':
                    last_store = None
                elif last_store and (d is not None and (f'r{d}' == last_store[0] or d in (6, 7))):
                    last_store = None
                if op in ('jalr', 'jmp', 'jz', 'jnz', 'jltz'):
                    last_store = None
            elif kind in ('label', 'asm'):
                out.append(ln)
                r7 = None
                last_store = None
            else:
                out.append(ln)
            i += 1
        lines = out
    return lines


def _next_label_is(lines, j, name):
    while j < len(lines) and lines[j][0] == 'comment':
        j += 1
    while j < len(lines) and lines[j][0] == 'label':
        if lines[j][1] == name:
            return True
        j += 1
    return False


# ----------------------------------------------------------------------------------------------
# Runtime routines (only those used are included). They take r1 and r2, return the result in r1
# (rt_udiv: the remainder in r2), and may change r1, r2, r3 and r7.

RUNTIME = {
    'rt_and': """\
; r1 = r1 & r2, one bit at a time from the top (BEAG has no AND instruction)
rt_and:
    li   r3,rt_save
    sw   r7,(r3)            ; keep the return address
    lli  r3,1               ; the result; its first bit marks how many bits are done
rt_and_loop:
    bltz r3,rt_and_last     ; the mark has reached bit 15: one more bit to do
    add  r3,r3,r3
    bltz r1,rt_and_a
    b    rt_and_next
rt_and_a:
    bltz r2,rt_and_set      ; both top bits 1
    b    rt_and_next
rt_and_set:
    lli  r7,1
    add  r3,r3,r7
rt_and_next:
    add  r1,r1,r1
    add  r2,r2,r2
    b    rt_and_loop
rt_and_last:
    add  r3,r3,r3           ; the mark leaves the 16 bits
    bltz r1,rt_and_la
    b    rt_and_done
rt_and_la:
    bltz r2,rt_and_lset
    b    rt_and_done
rt_and_lset:
    lli  r7,1
    add  r3,r3,r7
rt_and_done:
    add  r1,r3,r0
    li   r7,rt_save
    lw   r7,(r7)
    jalr r0,r7,r0
""",
    'rt_or': """\
; r1 = r1 | r2, one bit at a time from the top
rt_or:
    li   r3,rt_save
    sw   r7,(r3)
    lli  r3,1               ; the result, with a mark bit as in rt_and
rt_or_loop:
    bltz r3,rt_or_last
    add  r3,r3,r3
    bltz r1,rt_or_set
    bltz r2,rt_or_set
    b    rt_or_next
rt_or_set:
    lli  r7,1
    add  r3,r3,r7
rt_or_next:
    add  r1,r1,r1
    add  r2,r2,r2
    b    rt_or_loop
rt_or_last:
    add  r3,r3,r3
    bltz r1,rt_or_lset
    bltz r2,rt_or_lset
    b    rt_or_done
rt_or_lset:
    lli  r7,1
    add  r3,r3,r7
rt_or_done:
    add  r1,r3,r0
    li   r7,rt_save
    lw   r7,(r7)
    jalr r0,r7,r0
""",
    'rt_xor': """\
; r1 = r1 ^ r2, one bit at a time from the top
rt_xor:
    li   r3,rt_save
    sw   r7,(r3)
    lli  r3,1               ; the result, with a mark bit as in rt_and
rt_xor_loop:
    bltz r3,rt_xor_last
    add  r3,r3,r3
    bltz r1,rt_xor_a
    bltz r2,rt_xor_set      ; 0 ^ 1
    b    rt_xor_next
rt_xor_a:
    bltz r2,rt_xor_next     ; 1 ^ 1
rt_xor_set:
    lli  r7,1
    add  r3,r3,r7
rt_xor_next:
    add  r1,r1,r1
    add  r2,r2,r2
    b    rt_xor_loop
rt_xor_last:
    add  r3,r3,r3
    bltz r1,rt_xor_la
    bltz r2,rt_xor_lset
    b    rt_xor_done
rt_xor_la:
    bltz r2,rt_xor_done
rt_xor_lset:
    lli  r7,1
    add  r3,r3,r7
rt_xor_done:
    add  r1,r3,r0
    li   r7,rt_save
    lw   r7,(r7)
    jalr r0,r7,r0
""",
    'rt_shl': """\
; r1 = r1 << r2 (doubling r2 times)
rt_shl:
    lli  r3,1
rt_shl_loop:
    bltz r2,rt_shl_done
    bz   r2,rt_shl_done
    add  r1,r1,r1
    sub  r2,r2,r3
    b    rt_shl_loop
rt_shl_done:
    jalr r0,r7,r0
""",
    'rt_sar': """\
; r1 = r1 >> r2 for a signed r1: halving r2 times, rounding down
rt_sar:
    li   r3,rt_save
    sw   r7,(r3)
rt_sar_loop:
    bltz r2,rt_sar_done
    bz   r2,rt_sar_done
    lli  r7,2
    rem  r3,r1,r7           ; -1, 0 or 1
    bltz r3,rt_sar_odd
    b    rt_sar_even
rt_sar_odd:
    add  r3,r3,r7           ; -1 -> 1
rt_sar_even:
    sub  r1,r1,r3           ; now even: the division is exact
    div  r1,r1,r7
    lli  r7,1
    sub  r2,r2,r7
    b    rt_sar_loop
rt_sar_done:
    li   r7,rt_save
    lw   r7,(r7)
    jalr r0,r7,r0
""",
    'rt_shr': """\
; r1 = r1 >> r2 for an unsigned r1
rt_shr:
    bltz r2,rt_shr_ret
    bz   r2,rt_shr_ret
    li   r3,rt_save
    sw   r7,(r3)
    lli  r3,2
    bltz r1,rt_shr_big
    div  r1,r1,r3
    b    rt_shr_next
rt_shr_big:                 ; top bit set: remove it, halve, put it back one place lower
    li   r7,0x8000
    add  r1,r1,r7
    div  r1,r1,r3
    li   r7,0x4000
    add  r1,r1,r7
rt_shr_next:
    lli  r7,1
    sub  r2,r2,r7
rt_shr_loop:                ; r1 is now below 0x8000: div halves it
    bz   r2,rt_shr_done
    div  r1,r1,r3
    sub  r2,r2,r7
    b    rt_shr_loop
rt_shr_done:
    li   r7,rt_save
    lw   r7,(r7)
rt_shr_ret:
    jalr r0,r7,r0
""",
    'rt_udiv': """\
; unsigned division: r1 = r1 / r2, r2 = r1 % r2 (the div and rem instructions are signed)
rt_udiv:
    bz   r2,rt_udiv_ret     ; x / 0: x, as the div instruction gives (remainder 0)
    bltz r2,rt_udiv_bigd    ; divisor >= 0x8000
    bltz r1,rt_udiv_bign    ; dividend >= 0x8000
    rem  r3,r1,r2           ; both below 0x8000: div and rem work
    div  r1,r1,r2
    add  r2,r3,r0
rt_udiv_ret:
    jalr r0,r7,r0
rt_udiv_bigd:               ; the quotient is 1 if x >= d, else 0
    bltz r1,rt_udiv_bigd2
    add  r2,r1,r0
    lli  r1,0
    jalr r0,r7,r0
rt_udiv_bigd2:
    sub  r3,r1,r2
    bltz r3,rt_udiv_q0
    add  r2,r3,r0
    lli  r1,1
    jalr r0,r7,r0
rt_udiv_q0:
    add  r2,r1,r0
    lli  r1,0
    jalr r0,r7,r0
rt_udiv_bign:               ; x >= 0x8000, d < 0x8000: divide x/2, then correct
    li   r3,rt_save
    sw   r7,(r3)
    li   r7,0x8000
    add  r3,r1,r7
    lli  r7,2
    div  r3,r3,r7
    li   r7,0x4000
    add  r3,r3,r7           ; r3 = x >> 1
    div  r3,r3,r2
    add  r3,r3,r3           ; q = ((x >> 1) / d) * 2
    mul  r7,r3,r2
    sub  r7,r1,r7           ; r = x - q*d, 0 <= r < 2d
    bltz r7,rt_udiv_fix     ; r >= 0x8000 > d
    sub  r1,r7,r2
    bltz r1,rt_udiv_done    ; r < d
rt_udiv_fix:
    sub  r7,r7,r2
    lli  r1,1
    add  r3,r3,r1
rt_udiv_done:
    add  r1,r3,r0
    add  r2,r7,r0
    li   r7,rt_save
    lw   r7,(r7)
    jalr r0,r7,r0
""",
}
RUNTIME_DATA = {'rt_and': ['rt_save'], 'rt_or': ['rt_save'], 'rt_xor': ['rt_save'],
                'rt_sar': ['rt_save'], 'rt_shr': ['rt_save'], 'rt_udiv': ['rt_save']}


# ----------------------------------------------------------------------------------------------
# The whole program

class Generator:
    def __init__(self, prog, memory=None):
        self.prog = prog
        self.memory = memory or MemoryMap.default()
        self.func_tables = {}        # function label -> [(label, words, comment)] tables in ROM
        self.nlabel = 0
        self.helpers = set()

    def new_label(self):
        self.nlabel += 1
        return f'L{self.nlabel}'

    def generate(self, header='', external=None, imports=(), separate_tail=False):
        """The program as assembly text.
        external: labels that other (assembly) files define, -> their file name;
        imports: labels those files use (.extern), which must be kept;
        separate_tail: the labels marking the end of the global variables (rt_data_end,
        ___heap_start) are left to tail_text(), to be placed after the other files' data."""
        prog = self.prog
        external = dict(external or {})
        main = prog.globals.get('main')
        if main is None or main.kind != 'func' or not main.defined:
            raise CompileError('the program has no main() function')
        if main.type.params:
            raise CompileError('main() cannot have parameters on BEAG (there is no command line)', main.tok)
        bodies = {}
        refs = {}
        funcs = []
        for fd in prog.funcs:
            lab = fd.sym.label
            if lab in external:
                if fd.weak:
                    continue                 # an assembly file replaces this library function
                raise CompileError(f'{fd.sym.name}() is defined here and also in {external[lab]} '
                                   f'(.globl {lab})', fd.tok)
            fg = FuncGen(self, fd)
            bodies[lab] = fg.generate()
            refs[lab] = fg.refs
            funcs.append(fd)
        objects = {s.label: s for s in prog.objects}
        for lab, s in objects.items():
            if lab in external:
                raise CompileError(f'{s.name} is defined here and also in {external[lab]} (.globl {lab})', s.tok)
        strings = {label: codes for codes, label in prog.strings.items()}
        init_refs = {}
        for s in prog.objects:
            r = {}
            for off, e in (s.init or []):
                v = self.const_value(e)
                if isinstance(v, tuple) and v[0] is not None:
                    r.setdefault(v[0], e.tok)
            init_refs[s.label] = r
        # keep only what main() (and the assembly files) can reach
        seen = set()
        todo = [main.label] + [lab for lab in imports if lab in bodies or lab in objects]
        first_use = {}
        while todo:
            lab = todo.pop()
            if lab in seen:
                continue
            seen.add(lab)
            for r, tok in list(refs.get(lab, {}).items()) + list(init_refs.get(lab, {}).items()):
                first_use.setdefault(r, tok)
                todo.append(r)
        defined = set(bodies) | set(objects) | set(strings) | set(RUNTIME) | set(external) | \
            {'___heap_start', '___heap_last'}
        for lab in sorted(seen):
            if lab not in defined:
                name = lab[1:] if lab.startswith('_') else lab
                raise CompileError(f'undefined reference to {name!r}: it is declared but never defined',
                                   first_use.get(lab))
        used_funcs = [fd for fd in funcs if fd.sym.label in seen]
        used_objs = [s for s in prog.objects if s.label in seen]
        used_strs = [lab for lab in strings if lab in seen]
        used_helpers = sorted(h for h in self.helpers if h in seen)
        helper_data = sorted({d for h in used_helpers for d in RUNTIME_DATA.get(h, [])})
        used_external = sorted(lab for lab in seen if lab in external)
        # where constant data goes: a ROM that lw can read (von Neumann program ROM, or a ROM bank)
        mem = self.memory
        ro = mem.rodata_bank()
        rom_objs = [s for s in used_objs if ro and is_const_object(s.type)]
        ram_objs = [s for s in used_objs if s not in rom_objs]
        rom_strs = used_strs if ro else []
        ram_strs = [] if ro else used_strs
        exported = [fd.sym.label for fd in used_funcs if fd.sym.storage == 'global'] + \
                   [s.label for s in used_objs if s.storage == 'global']
        # where each symbol comes from, for the memory map
        self.origins = {'rt_start': 'start-up code', 'rt_halt': 'start-up code', 'rt_clear': 'start-up code',
                        'rt_cleared': 'start-up code', 'rt_data_end': 'end of the global variables',
                        '___heap_start': 'the heap starts here', '___heap_last': 'the last word of the heap'}
        for fd in used_funcs:
            self.origins[fd.sym.label] = source_name(fd.tok.file)
        for s in used_objs:
            self.origins[s.label] = source_name(s.tok.file)
        for lab in used_strs:
            self.origins[lab] = 'string literal' + (' (ROM)' if ro else '')
        for s in rom_objs:
            self.origins[s.label] += ' (const, ROM)'
        self.origins.update({'rt_init': 'start-up code', 'rt_inited': 'start-up code',
                             'rt_idata': 'initial values of the variables'})
        for h in used_helpers:
            self.origins[h] = 'runtime routine'
        for d in helper_data:
            self.origins[d] = 'runtime routine (data)'
        self.separate_tail = separate_tail

        out = []
        w = out.append
        w(header)
        w('; registers: r0 = 0, r1-r2 = values (r1 also the return value), r3-r5 = register')
        w(';            variables or values, r6 = stack pointer, r7 = return address and scratch')
        w('; jmp/jz/jnz/jltz are the assembler\'s long-range forms of b/bz/bnz/bltz (they may use r7)')
        w('')
        for k in range(0, len(exported), 6):
            w('.globl ' + ', '.join(exported[k:k + 6]))
        ext = used_external + (['rt_data_end', '___heap_start', '___heap_last'] if separate_tail else [])
        for k in range(0, len(ext), 6):
            w('.extern ' + ', '.join(ext[k:k + 6]))
        w('')
        w('#bank program')
        w('rt_start:')
        top = mem.stack_top
        w(f'    li   r6,0x{top & 0xFFFF:04x}         ; stack pointer: the stack grows down from 0x{(top - 1) & 0xFFFF:04x}')
        data_words = sum(s.type.size() for s in ram_objs) + sum(len(strings[l]) for l in ram_strs)
        if ram_objs or ram_strs or helper_data or separate_tail:
            w(f'    li   r1,0x{mem.data.start:04x}          ; set all global variables to 0')
            w('    li   r2,rt_data_end')
            w('    lli  r3,1')
            w('rt_clear:')
            w('    sub  r4,r1,r2')
            w('    bz   r4,rt_cleared')
            w('    sw   r0,(r1)')
            w('    add  r1,r1,r3')
            w('    b    rt_clear')
            w('rt_cleared:')
        records = self.init_records(ram_objs) if ro else []
        if records:
            w('    li   r2,rt_idata        ; the initial values of the variables, from the ROM table rt_idata')
            w('    lli  r5,1')
            w('rt_init:')
            w('    lw   r3,(r2)            ; number of words (0: the end of the table)')
            w('    bz   r3,rt_inited')
            w('    add  r2,r2,r5')
            w('    lw   r1,(r2)            ; where they go')
            w('    add  r2,r2,r5')
            w('rt_init_word:')
            w('    lw   r4,(r2)')
            w('    sw   r4,(r1)')
            w('    add  r1,r1,r5')
            w('    add  r2,r2,r5')
            w('    sub  r3,r3,r5')
            w('    bnz  r3,rt_init_word')
            w('    b    rt_init')
            w('rt_inited:')
        init_lines = []
        if not ro:
            for s in ram_objs:
                if s.init:
                    vals = [(off, self.const_value(e)) for off, e in s.init]
                    init_lines.extend(self.init_code(s.label, vals, s.name))
            for lab in ram_strs:
                codes = strings[lab]
                text = ''.join(chr(c) if 32 <= c < 127 else '.' for c in codes[:-1])
                init_lines.extend(self.init_code(lab, list(enumerate(codes)), f'"{text}"'))
        if init_lines:
            w('    lli  r3,1               ; initialised variables and strings')
            out.extend(init_lines)
        w('    li   r7,_main')
        w('    jalr r7,r7,r0           ; call main()')
        w('rt_halt:')
        w('    b    rt_halt            ; main() has returned: stop here')
        for fd in used_funcs:
            w('')
            out.extend(format_lines(bodies[fd.sym.label]))
        for h in used_helpers:
            w('')
            out.append(RUNTIME[h].rstrip('\n'))
        rom = []
        for s in rom_objs:
            image = [0] * s.type.size()
            for off, e in (s.init or []):
                image[off] = self.const_value(e)
            rom.extend(d16_lines(s.label, image, f'{s.type} {s.name}'))
        for lab in rom_strs:
            codes = strings[lab]
            text = ''.join(chr(c) if 32 <= c < 127 else '\\n' if c == 10 else '.' for c in codes[:-1])
            rom.extend(d16_lines(lab, codes, f'"{text}"'))
        for fd in used_funcs:
            for lab, image, what in self.func_tables.get(fd.sym.label, []):
                rom.extend(d16_lines(lab, image, f'{fd.sym.name}(): {what}'))
                self.origins[lab] = f'{source_name(fd.tok.file)}: {what} in {fd.sym.name}()'
        if records:
            rom.append('rt_idata:                 ; initial values of the variables: number of words, address, values')
            for addr, words, what in records:
                rom.append(f'    #d16 {len(words)}, {addr}'.ljust(32) + f'; {what}')
                rom.extend(d16_lines(None, words))
            rom.append('    #d16 0                      ; the end of the table')
        if rom:
            w('')
            if ro != 'program':
                w(f'#bank {ro}')
            w(f'; constant data in ROM (lw can read the {"program ROM of a von Neumann BEAG" if ro == "program" else "ROM bank " + ro})')
            out.extend(rom)
        w('')
        w('#bank data')
        for s in ram_objs:
            w(f'{s.label}:'.ljust(20) + f' #res {s.type.size():<4}; {s.type} {s.name}')
        for lab in ram_strs:
            codes = strings[lab]
            text = ''.join(chr(c) if 32 <= c < 127 else '\\n' if c == 10 else '.' for c in codes[:-1])
            w(f'{lab}:'.ljust(20) + f' #res {len(codes):<4}; "{text}"')
        for d in helper_data:
            w(f'{d}:'.ljust(20) + ' #res 1')
        if not separate_tail:
            out.extend(self.tail_lines())
        room = mem.data.size - (128 if mem.stack_in_data else 0)
        if data_words + len(helper_data) > room:
            raise CompileError(f'the global variables need {data_words + len(helper_data)} words, but the RAM bank '
                               f'data holds {mem.data.size}' + (' and the stack needs room in it too'
                                                                if mem.stack_in_data else ''))
        return '\n'.join(out) + '\n'

    def tail_lines(self):
        """The end of the global variables: the heap is from there to the stack (or to the end of data)."""
        return ['rt_data_end:',
                '___heap_start:            ; free RAM from here up to the stack',
                f'___heap_last = 0x{self.memory.data.end - 1:04x}  ; the last word of the RAM bank data']

    def tail_text(self):
        """The last file of a program made of C and assembly files: the end of the variables."""
        return '\n'.join(['; the end of the global variables of all the files (made by beagcc)',
                          '.globl rt_data_end, ___heap_start, ___heap_last',
                          '#bank data'] + self.tail_lines()) + '\n'

    def const_value(self, e):
        """int, or (label, offset) for addresses."""
        k = e.kind
        if k == 'num':
            return e.val
        if k == 'cast':
            return self.const_value(e.a)
        if k == 'addr':
            return self.const_addr(e.a)
        if k == 'binop' and e.op in ('+', '-'):
            a, b = self.const_value(e.a), self.const_value(e.b)
            if isinstance(a, int) and isinstance(b, tuple) and e.op == '+':
                a, b = b, a
            if isinstance(a, tuple):
                return (a[0], a[1] + b if e.op == '+' else a[1] - b)
            return a + b if e.op == '+' else a - b
        raise CompileError('a global or static variable needs a constant initialiser', e.tok)

    def const_addr(self, lv):
        if lv.kind == 'var':
            return (lv.sym.label, 0)
        if lv.kind == 'str':
            return (lv.label, 0)
        if lv.kind == 'deref':
            return self.const_value(lv.a)
        if lv.kind == 'member':
            v = self.const_value(lv.a)
            return (v[0], v[1] + lv.offset)
        raise CompileError('a global or static variable needs a constant initialiser', lv.tok)

    def init_records(self, objs):
        """[(address text, words, name)]: the runs of initial values of the variables, for rt_idata.
        Zeros need no record (the variables are cleared first); a gap of up to 2 zeros stays in a run."""
        records = []
        for s in objs:
            if not s.init:
                continue
            vals = {}
            for off, e in s.init:
                v = self.const_value(e)
                if v != 0:
                    vals[off] = v
            offs = sorted(vals)
            run = []
            for o in offs + [None]:
                if run and (o is None or o - run[-1] > 3):
                    start = run[0]
                    words = [vals.get(k, 0) for k in range(start, run[-1] + 1)]
                    records.append((addr_text(s.label, start), words, s.name))
                    run = []
                if o is not None:
                    run.append(o)
        return records

    def init_code(self, label, vals, what):
        """Code that stores the non-zero words of an initialiser. r3 = 1."""
        lines = [f'    ; {what}']
        vals = sorted((o, v) for o, v in vals if v != 0)
        cur = None                  # offset r2 points at
        last = None                 # value in r1
        for off, v in vals:
            if cur is None or off - cur > 2:
                lines.append(f'    li   r2,{addr_text(label, off)}')
                cur = off
            while cur < off:
                lines.append('    add  r2,r2,r3')
                cur += 1
            if v != last:
                if isinstance(v, tuple):
                    lines.append(f'    li   r1,{addr_text(v[0], v[1])}')
                else:
                    sv = s16(v)
                    lines.append(f'    lli  r1,{sv}' if -128 <= sv <= 127 else f'    li   r1,{sv}')
                last = v
            lines.append('    sw   r1,(r2)')
        return lines if vals else []


def rom_value(e):
    """The value of a constant initialiser for a table in ROM: int, (label, offset), or None."""
    k = e.kind
    if k == 'num':
        return e.val
    if k == 'cast':
        return rom_value(e.a)
    if k == 'addr' and e.a.kind == 'str':
        return (e.a.label, 0)
    if k == 'addr' and e.a.kind == 'var' and e.a.sym.storage in ('global', 'static'):
        return (e.a.sym.label, 0)
    return None


def word_text(v):
    if isinstance(v, tuple):
        return addr_text(v[0], v[1])
    return str(s16(v))


def d16_lines(label, words, comment=None):
    """#d16 lines for a table in ROM, 8 words per line."""
    out = []
    for k in range(0, max(len(words), 1), 8):
        head = f'{label}:'.ljust(20) if (label and k == 0) else ' ' * 20
        line = head + ' #d16 ' + ', '.join(word_text(v) for v in words[k:k + 8])
        if comment and k == 0:
            line = line.ljust(60) + f' ; {comment}'
        out.append(line)
    return out


def source_name(path):
    """A short name for a source file: lib/name.c for the library, otherwise the file's name."""
    import os
    parts = os.path.normpath(path).split(os.sep)
    if len(parts) > 1 and parts[-2] == 'lib':
        return 'lib/' + parts[-1]
    return parts[-1]


def format_lines(lines):
    out = []
    for ln in lines:
        k = ln[0]
        if k == 'ins':
            op, args, com = ln[1], ln[2], ln[3]
            s = f'    {op:<4} {args}'
            if com:
                s = s.ljust(28) + f'; {com}'
            out.append(s.rstrip())
        elif k == 'label':
            out.append(f'{ln[1]}:')
        elif k == 'comment':
            out.append(f'    ; {ln[1]}')
        elif k == 'asm':
            for a in ln[1].split('\n'):
                a = a.strip()
                if a:
                    out.append(a if a.endswith(':') else '    ' + a)
    return out
