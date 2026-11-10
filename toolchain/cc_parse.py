"""Types, syntax tree and parser of beagcc, the C compiler for the BEAG computer.

Every scalar (char, short, int, unsigned, pointer) is one 16-bit word: BEAG memory is
word-addressed, so sizeof(char) == sizeof(int) == 1 and CHAR_BIT is 16.
"""

from cc_lex import CompileError, warn, parse_number

# ----------------------------------------------------------------------------------------------
# Types


class Type:
    kind = None
    volatile = False             # every access must really be made (memory-mapped I/O)
    const = False                # it cannot be changed (and a global one can be kept in ROM)

    def size(self):
        raise NotImplementedError

    is_void = property(lambda s: s.kind == 'void')
    is_int = property(lambda s: s.kind == 'int')
    is_ptr = property(lambda s: s.kind == 'ptr')
    is_array = property(lambda s: s.kind == 'array')
    is_func = property(lambda s: s.kind == 'func')
    is_struct = property(lambda s: s.kind == 'struct')
    is_scalar = property(lambda s: s.kind in ('int', 'ptr'))
    unsigned = False

    def replace(self, old, new):
        return new if self is old else self


class VoidType(Type):
    kind = 'void'

    def size(self):
        return 1

    def __str__(self):
        return 'void'


class IntType(Type):
    kind = 'int'

    def __init__(self, name, unsigned):
        self.name, self.unsigned = name, unsigned

    def size(self):
        return 1

    def __eq__(self, o):
        return isinstance(o, IntType) and o.name == self.name and o.unsigned == self.unsigned

    def __hash__(self):
        return hash((self.name, self.unsigned))

    def __str__(self):
        v = ('const ' if self.const else '') + ('volatile ' if self.volatile else '')
        if self.name == 'enum':
            return v + 'enum'
        return v + ('unsigned ' if self.unsigned else '') + self.name


class PtrType(Type):
    kind = 'ptr'
    unsigned = True

    def __init__(self, base):
        self.base = base

    def size(self):
        return 1

    def replace(self, old, new):
        if self is old:
            return new
        p = PtrType(self.base.replace(old, new))
        p.volatile, p.const = self.volatile, self.const
        return p

    def __eq__(self, o):
        return isinstance(o, PtrType) and o.base == self.base

    def __hash__(self):
        return hash(('ptr', self.base))

    def __str__(self):
        if self.base.is_func:
            return self.base.str_with('(*)')
        if self.base.is_array:
            return f'{self.base.base} (*)[{self.base.length or ""}]'
        return f'{self.base} *' + (' const' if self.const else '') + (' volatile' if self.volatile else '')


class ArrayType(Type):
    kind = 'array'

    def __init__(self, base, length):
        self.base, self.length = base, length

    def size(self):
        if self.length is None:
            return 0
        return self.length * self.base.size()

    def replace(self, old, new):
        return new if self is old else ArrayType(self.base.replace(old, new), self.length)

    def __eq__(self, o):
        return isinstance(o, ArrayType) and o.base == self.base and o.length == self.length

    def __hash__(self):
        return hash(('array', self.base, self.length))

    def __str__(self):
        return f'{self.base} [{self.length if self.length is not None else ""}]'


class FuncType(Type):
    kind = 'func'

    def __init__(self, ret, params, varargs=False, proto=True, names=None):
        self.ret, self.params, self.varargs, self.proto = ret, params, varargs, proto
        self.names = names or [None] * len(params)

    def size(self):
        return 1

    def replace(self, old, new):
        if self is old:
            return new
        return FuncType(self.ret.replace(old, new), self.params, self.varargs, self.proto, self.names)

    def __eq__(self, o):
        return (isinstance(o, FuncType) and o.ret == self.ret and
                (not o.proto or not self.proto or (o.params == self.params and o.varargs == self.varargs)))

    def __hash__(self):
        return hash(('func', self.ret))

    def str_with(self, inner):
        ps = ', '.join(str(p) for p in self.params) + (', ...' if self.varargs else '')
        if not self.params and not self.varargs and self.proto:
            ps = 'void'
        return f'{self.ret} {inner}({ps})'

    def __str__(self):
        return self.str_with('')


class StructType(Type):
    kind = 'struct'

    def __init__(self, tag, is_union):
        self.tag, self.is_union = tag, is_union
        self.members = None          # list of (name, type, offset); None while incomplete
        self.bytes = 0

    def size(self):
        return self.bytes

    def member(self, name):
        for m in self.members or []:
            if m[0] == name:
                return m
        return None

    def __str__(self):
        return f'{"union" if self.is_union else "struct"} {self.tag or "(anonymous)"}'


VOID = VoidType()
INT = IntType('int', False)
UINT = IntType('int', True)
CHAR = IntType('char', False)
UCHAR = IntType('char', True)
SHORT = IntType('short', False)
USHORT = IntType('short', True)
ENUM = IntType('enum', False)


class Placeholder(Type):
    kind = 'placeholder'


def qualified(t, volatile=False, const=False):
    """t with the volatile and/or const qualifier (a struct or a function keeps its type)."""
    if not (volatile or const):
        return t
    if t.is_int:
        n = IntType(t.name, t.unsigned)
    elif t.is_ptr:
        n = PtrType(t.base)
    elif t.is_array:
        return ArrayType(qualified(t.base, volatile, const), t.length)
    else:
        return t
    n.volatile = t.volatile or volatile
    n.const = t.const or const
    return n


def make_volatile(t):
    return qualified(t, volatile=True)


def is_const_object(t):
    """Every word of an object of type t is const (a const scalar, or an array of them)."""
    while t.is_array:
        t = t.base
    return t.const


def norm(v, t):
    """Value v as type t holds it (16 bits, signed or unsigned)."""
    v &= 0xFFFF
    if not t.unsigned and v & 0x8000:
        v -= 0x10000
    return v


def promote(t):
    if t.is_int:
        return UINT if t.unsigned else INT
    return t


def arith_type(a, b):
    a, b = promote(a), promote(b)
    return UINT if (a.unsigned or b.unsigned) else INT


# ----------------------------------------------------------------------------------------------
# Syntax tree


class Node:
    """Expression or statement. Common fields: kind, tok (for messages), type."""

    def __init__(self, kind, tok, type=None, **kw):
        self.kind, self.tok, self.type = kind, tok, type
        self.lvalue = False
        self.__dict__.update(kw)

    def __repr__(self):
        fields = {k: v for k, v in self.__dict__.items() if k not in ('tok', 'kind')}
        return f'Node({self.kind}, {fields})'


class Symbol:
    def __init__(self, name, kind, type, storage, tok):
        self.name, self.kind, self.type, self.storage, self.tok = name, kind, type, storage, tok
        self.label = None            # assembly label of a global or a static
        self.offset = None           # frame offset of a local or a parameter
        self.value = None            # value of an enum constant
        self.defined = False
        self.init = None             # initialiser of a global: list of (offset, Node)
        self.func = None             # FuncDef of a defined function

    def __repr__(self):
        return f'Symbol({self.name},{self.kind},{self.storage})'


class FuncDef:
    def __init__(self, sym, params, tok):
        self.sym, self.params, self.tok = sym, params, tok
        self.body = None
        self.frame = 0               # words of locals
        self.labels = {}             # goto labels: name -> Node
        self.statics = []            # static locals (Symbols)


class Program:
    """Everything the parser produces for all translation units."""

    def __init__(self):
        self.globals = {}            # external name -> Symbol
        self.objects = []            # Symbols of global/static variables with storage (in order)
        self.funcs = []              # FuncDefs
        self.strings = {}            # tuple of codes -> label
        self.n_static = 0

    def string_label(self, codes):
        key = tuple(codes)
        if key not in self.strings:
            self.strings[key] = f'S{len(self.strings) + 1}'
        return self.strings[key]


# ----------------------------------------------------------------------------------------------
# Parser

TYPE_WORDS = {'void', 'char', 'short', 'int', 'long', 'signed', 'unsigned', 'float', 'double',
              '_Bool', 'struct', 'union', 'enum'}
QUALIFIERS = {'const', 'volatile', 'restrict', '__restrict', 'inline', '__inline', '__inline__',
              '_Noreturn', '__volatile__', '__const'}
STORAGE = {'typedef', 'extern', 'static', 'auto', 'register'}
KEYWORDS = TYPE_WORDS | QUALIFIERS | STORAGE | {
    'if', 'else', 'while', 'do', 'for', 'switch', 'case', 'default', 'break', 'continue', 'return',
    'goto', 'sizeof', 'asm', '__asm__', '__asm'}

ASSIGN_OPS = {'=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '<<=', '>>='}
BINARY_PREC = {'||': 1, '&&': 2, '|': 3, '^': 4, '&': 5, '==': 6, '!=': 6, '<': 7, '>': 7, '<=': 7,
               '>=': 7, '<<': 8, '>>': 8, '+': 9, '-': 9, '*': 10, '/': 10, '%': 10}


class InitList:
    def __init__(self, items, tok):
        self.items, self.tok = items, tok      # items: list of (designator or None, InitList|Node)


class Parser:
    def __init__(self, toks, prog, tu):
        self.toks = toks
        self.i = 0
        self.prog = prog
        self.tu = tu
        self.scopes = [{}]           # ordinary identifiers
        self.tags = [{}]             # struct/union/enum tags
        self.func = None             # FuncDef being parsed
        self.loops = 0
        self.switches = []           # stack of switch Nodes
        self.n_label = 0
        self.weak = False            # a library file: its functions give way to the program's

    # -- tokens -------------------------------------------------------------------------------

    @property
    def tok(self):
        return self.toks[self.i]

    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else self.toks[-1]

    def next(self):
        t = self.toks[self.i]
        if t.kind != 'eof':
            self.i += 1
        return t

    def at(self, text):
        t = self.tok
        return t.text == text and t.kind in ('punct', 'id')

    def accept(self, text):
        if self.at(text):
            return self.next()
        return None

    def expect(self, text, what=None):
        if self.at(text):
            return self.next()
        t = self.tok
        found = 'the end of the file' if t.kind == 'eof' else repr(t.text)
        prev = self.toks[self.i - 1] if self.i else t
        if text == ';' and t.line != prev.line and prev.kind != 'eof':
            raise CompileError(f"expected ';' after {prev.text!r}", prev)
        raise CompileError(f'expected {what or repr(text)}, found {found}', t)

    def ident(self, what='a name'):
        t = self.tok
        if t.kind != 'id' or t.text in KEYWORDS:
            found = 'the end of the file' if t.kind == 'eof' else repr(t.text)
            raise CompileError(f'expected {what}, found {found}', t)
        return self.next()

    # -- scopes -------------------------------------------------------------------------------

    def lookup(self, name):
        for s in reversed(self.scopes):
            if name in s:
                return s[name]
        return None

    def lookup_tag(self, name):
        for s in reversed(self.tags):
            if name in s:
                return s[name]
        return None

    def push_scope(self):
        self.scopes.append({})
        self.tags.append({})

    def pop_scope(self):
        self.scopes.pop()
        self.tags.pop()

    def is_typedef(self, t):
        if t.kind != 'id' or t.text in KEYWORDS:
            return False
        s = self.lookup(t.text)
        return s is not None and s.kind == 'typedef'

    def starts_type(self, t=None):
        t = t or self.tok
        if t.kind != 'id':
            return False
        return t.text in TYPE_WORDS or t.text in QUALIFIERS or t.text in STORAGE or self.is_typedef(t)

    # -- translation unit ---------------------------------------------------------------------

    def parse(self):
        while self.tok.kind != 'eof':
            if self.accept(';'):
                continue
            self.external_declaration()

    def external_declaration(self):
        start = self.tok
        base, storage = self.specifiers()
        if self.accept(';'):
            return
        first = True
        while True:
            dtok = self.tok
            name_tok, t = self.declarator(base)
            if name_tok is None:
                raise CompileError('expected a name in the declaration', dtok)
            if first and t.is_func and self.at('{'):
                if storage == 'typedef':
                    raise CompileError('a function definition cannot be a typedef', name_tok)
                self.function_definition(name_tok, t, storage)
                return
            first = False
            self.declare_global(name_tok, t, storage)
            if not self.accept(','):
                break
        self.expect(';')

    # -- declaration specifiers ---------------------------------------------------------------

    def specifiers(self, allow_storage=True):
        """(base type, storage class) of declaration specifiers."""
        storage = None
        words = []
        base = None
        vol = False
        con = False
        t0 = self.tok
        while True:
            t = self.tok
            if t.kind != 'id':
                break
            w = t.text
            if w in STORAGE:
                if not allow_storage:
                    raise CompileError(f'{w!r} is not allowed here', t)
                if storage:
                    raise CompileError('more than one storage class', t)
                storage = w
                self.next()
            elif w in QUALIFIERS:
                vol = vol or w in ('volatile', '__volatile__')
                con = con or w in ('const', '__const')
                self.next()
            elif w in ('struct', 'union'):
                if base or words:
                    raise CompileError('two types in one declaration', t)
                base = self.struct_specifier()
            elif w == 'enum':
                if base or words:
                    raise CompileError('two types in one declaration', t)
                base = self.enum_specifier()
            elif w in TYPE_WORDS:
                if base:
                    raise CompileError('two types in one declaration', t)
                words.append(t)
                self.next()
            elif self.is_typedef(t) and not base and not words:
                base = self.lookup(w).type
                self.next()
            else:
                break
        if base is None:
            base = self.combine(words, t0)
        elif words:
            raise CompileError('two types in one declaration', words[0])
        base = qualified(base, volatile=vol, const=con)
        return base, storage

    def combine(self, words, t0):
        names = [w.text for w in words]
        if not names:
            raise CompileError(f'expected a type, found {t0.text!r}', t0)
        for bad in ('float', 'double'):
            if bad in names:
                raise CompileError(f'{bad} is not supported: BEAG has only 16-bit integers', words[names.index(bad)])
        if 'long' in names:
            raise CompileError('long is not supported: BEAG is a 16-bit computer, use int (16 bits)',
                               words[names.index('long')])
        unsigned = 'unsigned' in names
        if unsigned and 'signed' in names:
            raise CompileError('both signed and unsigned', words[0])
        rest = [n for n in names if n not in ('signed', 'unsigned')]
        if rest == ['void']:
            if len(names) > 1:
                raise CompileError('void cannot be signed or unsigned', words[0])
            return VOID
        if rest == ['_Bool']:
            return UINT
        if rest == ['char']:
            return UCHAR if unsigned else CHAR
        if rest in (['short'], ['short', 'int'], ['int', 'short']):
            return USHORT if unsigned else SHORT
        if rest in (['int'], []):
            return UINT if unsigned else INT
        raise CompileError(f'invalid type {" ".join(names)!r}', words[0])

    def struct_specifier(self):
        kw = self.next()
        is_union = kw.text == 'union'
        tag = None
        if self.tok.kind == 'id' and self.tok.text not in KEYWORDS:
            tag = self.next().text
        if self.at('{'):
            st = self.tags[-1].get(tag) if tag else None
            if st is not None and (not isinstance(st, StructType) or st.members is not None):
                raise CompileError(f'redefinition of {kw.text} {tag}', kw)
            if st is None:
                st = StructType(tag, is_union)
                if tag:
                    self.tags[-1][tag] = st
            self.struct_body(st)
            return st
        if tag is None:
            raise CompileError(f'expected a name or {{ after {kw.text}', self.tok)
        st = self.lookup_tag(tag)
        if st is None:
            st = StructType(tag, is_union)
            self.tags[-1][tag] = st
        elif not isinstance(st, StructType) or st.is_union != is_union:
            raise CompileError(f'{tag} is not a {kw.text}', kw)
        return st

    def struct_body(self, st):
        self.expect('{')
        members = []
        off = 0
        size = 0
        while not self.accept('}'):
            base, storage = self.specifiers(allow_storage=False)
            if self.accept(';'):
                if base.is_struct and base.tag is None:          # anonymous struct/union member
                    for (n, t, o) in base.members:
                        members.append((n, t, (0 if st.is_union else off) + o))
                    sz = base.size()
                    off = off if st.is_union else off + sz
                    size = max(size, sz) if st.is_union else off
                continue
            while True:
                dt = self.tok
                name, t = self.declarator(base)
                if self.at(':'):
                    raise CompileError('bit-fields are not supported', self.tok)
                if name is None:
                    raise CompileError('expected a member name', dt)
                if t.is_func:
                    raise CompileError('a struct cannot contain a function (use a function pointer)', name)
                if t.is_struct and t.members is None or (t.is_array and t.length is None):
                    raise CompileError(f'member {name.text!r} has an incomplete type', name)
                if any(m[0] == name.text for m in members):
                    raise CompileError(f'duplicate member {name.text!r}', name)
                members.append((name.text, t, 0 if st.is_union else off))
                if st.is_union:
                    size = max(size, t.size())
                else:
                    off += t.size()
                    size = off
                if not self.accept(','):
                    break
            self.expect(';')
        if not members:
            raise CompileError('a struct needs at least one member', self.toks[self.i - 1])
        st.members = members
        st.bytes = size

    def enum_specifier(self):
        kw = self.next()
        tag = None
        if self.tok.kind == 'id' and self.tok.text not in KEYWORDS:
            tag = self.next().text
        if self.accept('{'):
            v = 0
            while not self.at('}'):
                nt = self.ident('an enumerator name')
                if self.accept('='):
                    v = self.const_int(self.conditional())
                sym = Symbol(nt.text, 'enum', ENUM, 'const', nt)
                sym.value = norm(v, INT)
                self.declare_local_name(sym, nt)
                v += 1
                if not self.accept(','):
                    break
            self.expect('}')
            if tag:
                self.tags[-1][tag] = ENUM
        elif tag is None:
            raise CompileError('expected a name or { after enum', self.tok)
        return ENUM

    # -- declarators --------------------------------------------------------------------------

    def declarator(self, base, abstract=False):
        """(name token or None, type)."""
        while self.accept('*'):
            vol = con = False
            while self.tok.kind == 'id' and self.tok.text in QUALIFIERS:
                vol = vol or self.tok.text in ('volatile', '__volatile__')
                con = con or self.tok.text in ('const', '__const')
                self.next()
            base = PtrType(base)
            base.volatile, base.const = vol, con
        if self.at('(') and self.nested_declarator_follows():
            self.next()
            ph = Placeholder()
            name, inner = self.declarator(ph, abstract)
            self.expect(')')
            outer = self.suffixes(base)
            return name, inner.replace(ph, outer)
        name = None
        if self.tok.kind == 'id' and self.tok.text not in KEYWORDS and not self.is_typedef(self.tok):
            name = self.next()
        elif self.tok.kind == 'id' and self.is_typedef(self.tok) and not abstract:
            name = self.next()           # a typedef name redeclared as a variable
        return name, self.suffixes(base)

    def nested_declarator_follows(self):
        t = self.peek(1)
        if t.text in ('*', '('):
            return True
        if t.kind == 'id' and t.text not in KEYWORDS and not self.is_typedef(t):
            return True
        return False

    def suffixes(self, base):
        if self.accept('['):
            if self.accept(']'):
                n = None
            else:
                et = self.tok
                n = self.const_int(self.assignment())
                if n <= 0:
                    raise CompileError('an array needs a size of at least 1', et)
                self.expect(']')
            elem = self.suffixes(base)
            if elem.is_func:
                raise CompileError('array of functions (use an array of function pointers)', self.tok)
            if elem.is_array and elem.length is None:
                raise CompileError('only the first dimension of an array can be left out', self.tok)
            return ArrayType(elem, n)
        if self.at('('):
            ptok = self.next()
            params, names, varargs, proto = self.parameter_list()
            ret = self.suffixes(base)
            if ret.is_func or ret.is_array:
                raise CompileError('a function cannot return a function or an array', ptok)
            return FuncType(ret, params, varargs, proto, names)
        return base

    def parameter_list(self):
        if self.accept(')'):
            return [], [], False, False
        if self.at('void') and self.peek(1).text == ')':
            self.next()
            self.next()
            return [], [], False, True
        params, names = [], []
        varargs = False
        while True:
            if self.accept('...'):
                varargs = True
                break
            pt = self.tok
            base, storage = self.specifiers()
            if storage not in (None, 'register'):
                raise CompileError(f'{storage!r} is not allowed for a parameter', pt)
            name, t = self.declarator(base, abstract=True)
            if t.is_array:
                t = PtrType(t.base)
            elif t.is_func:
                t = PtrType(t)
            if t.is_void:
                raise CompileError('a parameter cannot be void', pt)
            if t.is_struct:
                raise CompileError('passing a struct by value is not supported; pass a pointer to it',
                                   name or pt)
            params.append(t)
            names.append(name)
            if not self.accept(','):
                break
        self.expect(')')
        return params, names, varargs, True

    def type_name(self):
        base, storage = self.specifiers(allow_storage=False)
        name, t = self.declarator(base, abstract=True)
        if name is not None:
            raise CompileError('unexpected name in a type', name)
        return t

    # -- declarations -------------------------------------------------------------------------

    def declare_local_name(self, sym, tok):
        scope = self.scopes[-1]
        old = scope.get(sym.name)
        if old is not None:
            if len(self.scopes) == 1 or old.storage == 'extern' or sym.storage == 'extern':
                return self.merge(old, sym, tok)
            raise CompileError(f'redefinition of {sym.name!r}', tok)
        scope[sym.name] = sym
        return sym

    def merge(self, old, new, tok):
        if old.kind != new.kind or (old.kind != 'typedef' and not same_type(old.type, new.type)):
            raise CompileError(f'conflicting declarations of {new.name!r}: {old.type} and {new.type}', tok)
        if old.kind == 'typedef':
            return old
        if old.type.is_array and old.type.length is None and new.type.is_array:
            old.type = new.type
        if old.type.is_func and new.type.is_func and new.type.proto and not old.type.proto:
            old.type = new.type
        return old

    def global_symbol(self, name_tok, t, storage, kind):
        """The Symbol for a file-scope name, shared between translation units when external."""
        name = name_tok.text
        if storage == 'static':
            existing = self.scopes[0].get(name)
            if existing is not None:
                return self.merge(existing, Symbol(name, kind, t, 'static', name_tok), name_tok)
            sym = Symbol(name, kind, t, 'static', name_tok)
            sym.label = f'_{name}.{self.tu}'
            self.scopes[0][name] = sym
            return sym
        existing = self.scopes[0].get(name)
        if existing is not None:
            return self.merge(existing, Symbol(name, kind, t, 'global', name_tok), name_tok)
        sym = self.prog.globals.get(name)
        if sym is not None:
            sym = self.merge(sym, Symbol(name, kind, t, 'global', name_tok), name_tok)
        else:
            sym = Symbol(name, kind, t, 'global', name_tok)
            sym.label = f'_{name}'
            self.prog.globals[name] = sym
        self.scopes[0][name] = sym
        return sym

    def declare_global(self, name_tok, t, storage):
        if storage == 'typedef':
            self.declare_local_name(Symbol(name_tok.text, 'typedef', t, 'typedef', name_tok), name_tok)
            return
        if storage in ('auto', 'register'):
            raise CompileError(f'{storage!r} is only allowed inside a function', name_tok)
        if t.is_func:
            sym = self.global_symbol(name_tok, t, storage, 'func')
            if self.at('='):
                raise CompileError('a function cannot be initialised', self.tok)
            return
        sym = self.global_symbol(name_tok, t, storage, 'var')
        if self.accept('='):
            if storage == 'extern':
                warn(f'{name_tok.text!r} is declared extern and initialised', name_tok)
            if sym.init is not None:
                raise CompileError(f'redefinition of {name_tok.text!r}', name_tok)
            sym.init, sym.type = self.initializer_for(sym.type, name_tok, static=True)
            self.define_object(sym, name_tok)
        elif storage != 'extern':
            self.define_object(sym, name_tok)       # a tentative definition

    def define_object(self, sym, tok):
        if sym.type.is_void:
            raise CompileError(f'variable {sym.name!r} has type void', tok)
        if not sym.defined:
            sym.defined = True
            self.prog.objects.append(sym)

    def function_definition(self, name_tok, t, storage):
        sym = self.global_symbol(name_tok, t, storage, 'func')
        if sym.defined:
            if self.weak:                 # the program has its own version of a library function
                sym = Symbol(name_tok.text, 'func', t, 'static', name_tok)
                sym.label = f'_{name_tok.text}.unused{self.tu}'
            else:
                raise CompileError(f'redefinition of function {name_tok.text!r}', name_tok,
                                   note=f'first defined at {sym.tok.file}:{sym.tok.line}')
        sym.defined = True
        sym.tok = name_tok
        sym.type = t
        fd = FuncDef(sym, [], name_tok)
        fd.weak = self.weak
        sym.func = fd
        self.func = fd
        self.push_scope()
        for k, (pt, pn) in enumerate(zip(t.params, t.names)):
            if pn is None:
                raise CompileError('a parameter in a function definition needs a name', name_tok)
            ps = Symbol(pn.text, 'var', pt, 'param', pn)
            ps.offset = 2 + k
            self.declare_local_name(ps, pn)
            fd.params.append(ps)
        fd.body = self.compound(new_scope=False)
        self.pop_scope()
        for name, node in fd.labels.items():
            if not node.defined:
                raise CompileError(f'label {name!r} is used but not defined', node.tok)
        self.func = None
        self.prog.funcs.append(fd)

    def local_declaration(self):
        """Declarations inside a function; returns a 'decl' statement Node."""
        start = self.tok
        base, storage = self.specifiers()
        items = []
        if self.accept(';'):
            return Node('empty', start)
        while True:
            dtok = self.tok
            name_tok, t = self.declarator(base)
            if name_tok is None:
                raise CompileError('expected a name in the declaration', dtok)
            if storage == 'typedef':
                self.declare_local_name(Symbol(name_tok.text, 'typedef', t, 'typedef', name_tok), name_tok)
            elif t.is_func or storage == 'extern':
                kind = 'func' if t.is_func else 'var'
                sym = self.global_symbol_from_block(name_tok, t, kind)
                self.scopes[-1][name_tok.text] = sym
            elif storage == 'static':
                sym = Symbol(name_tok.text, 'var', t, 'static', name_tok)
                self.prog.n_static += 1
                sym.label = f'_{self.func.sym.name}.{name_tok.text}.{self.prog.n_static}'
                self.declare_local_name(sym, name_tok)
                if self.accept('='):
                    sym.init, sym.type = self.initializer_for(t, name_tok, static=True)
                self.define_object(sym, name_tok)
            else:
                sym = Symbol(name_tok.text, 'var', t, 'local', name_tok)
                self.declare_local_name(sym, name_tok)
                init = None
                if self.accept('='):
                    init, sym.type = self.initializer_for(t, name_tok, static=False)
                if sym.type.is_void:
                    raise CompileError(f'variable {name_tok.text!r} has type void', name_tok)
                if (sym.type.is_array and sym.type.length is None) or \
                        (sym.type.is_struct and sym.type.members is None):
                    raise CompileError(f'{name_tok.text!r} has an incomplete type', name_tok)
                self.func.frame += sym.type.size()
                sym.offset = -self.func.frame
                items.append((sym, init))
            if not self.accept(','):
                break
        self.expect(';')
        return Node('decl', start, items=items)

    def global_symbol_from_block(self, name_tok, t, kind):
        sym = self.prog.globals.get(name_tok.text)
        if sym is not None:
            return self.merge(sym, Symbol(name_tok.text, kind, t, 'global', name_tok), name_tok)
        sym = Symbol(name_tok.text, kind, t, 'global', name_tok)
        sym.label = f'_{name_tok.text}'
        self.prog.globals[name_tok.text] = sym
        return sym

    # -- initialisers -------------------------------------------------------------------------

    def initializer_for(self, t, name_tok, static):
        """(list of (offset, Node), completed type) for an initialiser of an object of type t."""
        init = self.initializer()
        if t.is_array and t.length is None:
            n = self.count_elements(t, init)
            t = ArrayType(t.base, n)
        out = []
        self.place(t, init, 0, out, top=True)
        if static:
            for off, e in out:
                self.const_init(e)            # checks that it is a constant
        return out, t

    def initializer(self):
        if self.at('{'):
            tok = self.next()
            items = []
            while not self.at('}'):
                desig = None
                if self.at('.') or self.at('['):
                    desig = []
                    while True:
                        if self.accept('.'):
                            desig.append(('member', self.ident('a member name')))
                        elif self.accept('['):
                            dt = self.tok
                            desig.append(('index', self.const_int(self.conditional()), dt))
                            self.expect(']')
                        else:
                            break
                    self.expect('=')
                items.append((desig, self.initializer()))
                if not self.accept(','):
                    break
            self.expect('}')
            return InitList(items, tok)
        return self.assignment()

    def is_string_init(self, t, init):
        """A char array initialised from a string literal (optionally in braces)."""
        if not (t.is_array and t.base.is_int):
            return None
        if isinstance(init, InitList) and len(init.items) == 1 and init.items[0][0] is None:
            init = init.items[0][1]
        if isinstance(init, Node) and init.kind == 'str':
            return init
        return None

    def count_elements(self, t, init):
        s = self.is_string_init(t, init)
        if s is not None:
            return len(s.codes)
        if not isinstance(init, InitList):
            raise CompileError('an array needs a {...} initialiser', getattr(init, 'tok', None))
        # count top-level positions, taking brace elision into account
        n = 0
        pos = 0
        items = list(init.items)
        k = 0
        elem = t.base
        while k < len(items):
            desig, it = items[k]
            if desig:
                if desig[0][0] != 'index':
                    raise CompileError('a designator .name needs a struct', init.tok)
                pos = desig[0][1]
            if isinstance(it, InitList) or not (elem.is_array or elem.is_struct) or \
                    self.is_string_init(elem, it) is not None:
                k += 1
            else:
                k += self.scalars_in(elem)
            pos += 1
            n = max(n, pos)
        return max(n, 1)

    def scalars_in(self, t):
        if t.is_array:
            return t.length * self.scalars_in(t.base)
        if t.is_struct:
            if t.is_union:
                return self.scalars_in(t.members[0][1])
            return sum(self.scalars_in(m[1]) for m in t.members)
        return 1

    def place(self, t, init, off, out, top=False):
        """Put the initialiser init for an object of type t at offset off."""
        s = self.is_string_init(t, init)
        if s is not None:
            if t.length is not None and len(s.codes) - 1 > t.length:
                raise CompileError(f'the string is longer than the array ({t.length} elements)', s.tok)
            for k, c in enumerate(s.codes[:t.length]):
                out.append((off + k, Node('num', s.tok, t.base, val=c)))
            return
        if isinstance(init, InitList):
            if t.is_array or t.is_struct:
                it = _InitIter(init.items)
                self.fill(t, it, off, out)
                if not it.done():
                    raise CompileError('too many values in the initialiser', init.tok)
                return
            if len(init.items) != 1 or init.items[0][0] is not None:
                raise CompileError('too many values for a scalar initialiser', init.tok)
            return self.place(t, init.items[0][1], off, out)
        if t.is_array:
            raise CompileError('an array needs a {...} initialiser', init.tok)
        if t.is_struct:
            e = self.rv(init)
            if not (e.type.is_struct and e.type is t):
                raise CompileError(f'cannot initialise {t} with {e.type}', init.tok)
            # copy a struct value word by word
            for k in range(t.size()):
                src = Node('deref', init.tok, INT,
                           a=self.ptr_add(Node('addr', init.tok, PtrType(INT), a=e), k))
                src.lvalue = True
                out.append((off + k, src))
            return
        e = self.convert(self.rv(init), t, 'initialisation')
        out.append((off, e))

    def fill(self, t, it, off, out):
        """Fill aggregate t from the iterator of initialiser items (brace elision)."""
        if t.is_array:
            k = 0
            while not it.done() and (t.length is None or k < t.length or it.peek_desig()):
                desig = it.peek_desig()
                if desig:
                    if desig[0][0] != 'index':
                        if k == 0 and not it.is_top_of(t):
                            return
                        raise CompileError('a designator .name needs a struct', it.tok())
                    k = desig[0][1]
                    if t.length is not None and not 0 <= k < t.length:
                        raise CompileError(f'index {k} is outside the array', desig[0][2])
                    it.strip_desig()
                    if len(desig) > 1:
                        self.place_desig(t.base, desig[1:], it.take(), off + k * t.base.size(), out)
                        k += 1
                        continue
                elif t.length is not None and k >= t.length:
                    break
                self.place_one(t.base, it, off + k * t.base.size(), out)
                k += 1
            return
        members = t.members if not t.is_union else t.members[:1]
        mi = 0
        while not it.done():
            desig = it.peek_desig()
            if desig:
                if desig[0][0] != 'member':
                    if mi == 0:
                        raise CompileError('a designator [n] needs an array', it.tok())
                    return
                name = desig[0][1].text
                found = [k for k, m in enumerate(t.members) if m[0] == name]
                if not found:
                    raise CompileError(f'{t} has no member {name!r}', desig[0][1])
                mi = found[0]
                it.strip_desig()
                m = t.members[mi]
                if len(desig) > 1:
                    self.place_desig(m[1], desig[1:], it.take(), off + m[2], out)
                    mi += 1
                    continue
                self.place_one(m[1], it, off + m[2], out)
                mi += 1
                continue
            if mi >= len(members):
                break
            m = members[mi]
            self.place_one(m[1], it, off + m[2], out)
            mi += 1

    def place_desig(self, t, desig, init, off, out):
        d = desig[0]
        if d[0] == 'index':
            if not t.is_array:
                raise CompileError('[n] designator for something that is not an array', d[2])
            sub, o = t.base, d[1] * t.base.size()
        else:
            if not t.is_struct:
                raise CompileError('.name designator for something that is not a struct', d[1])
            m = t.member(d[1].text)
            if m is None:
                raise CompileError(f'{t} has no member {d[1].text!r}', d[1])
            sub, o = m[1], m[2]
        if len(desig) > 1:
            self.place_desig(sub, desig[1:], init, off + o, out)
        else:
            self.place(sub, init, off + o, out)

    def place_one(self, t, it, off, out):
        init = it.peek()
        if isinstance(init, InitList) or not (t.is_array or t.is_struct) or \
                self.is_string_init(t, init) is not None or \
                (t.is_struct and isinstance(init, Node) and self.rv(init).type is t):
            self.place(t, it.take(), off, out)
        else:
            self.fill(t, it, off, out)           # brace elision

    def const_init(self, e):
        """Value of a constant initialiser: int, or (label, offset) for an address."""
        e0 = e
        if e.kind == 'num':
            return e.val
        if e.kind == 'cast':
            return self.const_init(e.a)
        if e.kind == 'addr':
            return self.const_addr(e.a, e0)
        if e.kind == 'binop' and e.op in ('+', '-'):
            a = self.const_init(e.a)
            b = self.const_init(e.b)
            if isinstance(a, int) and isinstance(b, tuple) and e.op == '+':
                a, b = b, a
            if isinstance(a, tuple) and isinstance(b, int):
                return (a[0], a[1] + b if e.op == '+' else a[1] - b)
            if isinstance(a, int) and isinstance(b, int):
                return a + b if e.op == '+' else a - b
        raise CompileError('a global or static variable needs a constant initialiser', e.tok)

    def const_addr(self, lv, e0):
        if lv.kind == 'var' and lv.sym.storage in ('global', 'static'):
            return (lv.sym.label, 0)
        if lv.kind == 'str':
            return (lv.label, 0)
        if lv.kind == 'deref':
            v = self.const_init(lv.a)
            if isinstance(v, tuple):
                return v
        if lv.kind == 'member':
            v = self.const_init(lv.a)
            if isinstance(v, tuple):
                return (v[0], v[1] + lv.offset)
        raise CompileError('a global or static variable needs a constant initialiser', e0.tok)

    # -- statements ---------------------------------------------------------------------------

    def compound(self, new_scope=True):
        tok = self.expect('{')
        if new_scope:
            self.push_scope()
        items = []
        while not self.accept('}'):
            if self.tok.kind == 'eof':
                raise CompileError('missing } at the end of the file', tok)
            items.append(self.block_item())
        if new_scope:
            self.pop_scope()
        return Node('block', tok, items=items)

    def block_item(self):
        if self.starts_type() and not (self.peek(1).text == ':' and self.is_typedef(self.tok)):
            return self.local_declaration()
        return self.statement()

    def statement(self):
        t = self.tok
        w = t.text if t.kind == 'id' else None
        if t.kind == 'punct' and t.text == '{':
            return self.compound()
        if t.kind == 'punct' and t.text == ';':
            self.next()
            return Node('empty', t)
        if w == 'if':
            self.next()
            self.expect('(')
            c = self.condition()
            self.expect(')')
            then = self.statement()
            other = self.statement() if self.accept('else') else None
            return Node('if', t, c=c, then=then, other=other)
        if w == 'while':
            self.next()
            self.expect('(')
            c = self.condition()
            self.expect(')')
            self.loops += 1
            body = self.statement()
            self.loops -= 1
            return Node('while', t, c=c, body=body)
        if w == 'do':
            self.next()
            self.loops += 1
            body = self.statement()
            self.loops -= 1
            self.expect('while')
            self.expect('(')
            c = self.condition()
            self.expect(')')
            self.expect(';')
            return Node('do', t, c=c, body=body)
        if w == 'for':
            self.next()
            self.expect('(')
            self.push_scope()
            init = None
            if self.starts_type():
                init = self.local_declaration()
            elif not self.accept(';'):
                init = Node('expr', self.tok, e=self.expression())
                self.expect(';')
            c = None if self.at(';') else self.condition()
            self.expect(';')
            step = None if self.at(')') else self.expression()
            self.expect(')')
            self.loops += 1
            body = self.statement()
            self.loops -= 1
            self.pop_scope()
            return Node('for', t, init=init, c=c, step=step, body=body)
        if w == 'switch':
            self.next()
            self.expect('(')
            e = self.rv(self.expression())
            if not e.type.is_int:
                raise CompileError(f'switch needs an integer, not {e.type}', e.tok)
            self.expect(')')
            sw = Node('switch', t, e=e, cases=[], default=None)
            self.switches.append(sw)
            sw.body = self.statement()
            self.switches.pop()
            return sw
        if w == 'case':
            self.next()
            if not self.switches:
                raise CompileError('case outside a switch', t)
            v = self.const_int(self.conditional())
            sw = self.switches[-1]
            v = norm(v, promote(sw.e.type))
            if any(c.val == v for c in sw.cases):
                raise CompileError(f'duplicate case {v}', t)
            self.expect(':')
            node = Node('case', t, val=v)
            sw.cases.append(node)
            node.stmt = self.statement() if not self.at('}') else Node('empty', t)
            return node
        if w == 'default':
            self.next()
            if not self.switches:
                raise CompileError('default outside a switch', t)
            sw = self.switches[-1]
            if sw.default is not None:
                raise CompileError('two defaults in one switch', t)
            self.expect(':')
            node = Node('default', t)
            sw.default = node
            node.stmt = self.statement() if not self.at('}') else Node('empty', t)
            return node
        if w == 'break':
            self.next()
            if not self.loops and not self.switches:
                raise CompileError('break outside a loop or switch', t)
            self.expect(';')
            return Node('break', t)
        if w == 'continue':
            self.next()
            if not self.loops:
                raise CompileError('continue outside a loop', t)
            self.expect(';')
            return Node('continue', t)
        if w == 'return':
            self.next()
            ret = self.func.sym.type.ret
            e = None
            if not self.at(';'):
                e = self.rv(self.expression())
                if ret.is_void:
                    if not e.type.is_void:
                        raise CompileError(f'{self.func.sym.name}() is void and cannot return a value', t)
                elif ret.is_struct:
                    raise CompileError('returning a struct is not supported; return a pointer to it', t)
                else:
                    e = self.convert(e, ret, 'return')
            elif not ret.is_void:
                warn(f'return without a value in {self.func.sym.name}(), which returns {ret}', t)
            self.expect(';')
            return Node('return', t, e=e)
        if w == 'goto':
            self.next()
            name = self.ident('a label')
            self.expect(';')
            lab = self.func_label(name)
            return Node('goto', t, label=lab)
        if w in ('asm', '__asm__', '__asm'):
            self.next()
            while self.tok.kind == 'id' and self.tok.text in QUALIFIERS:
                self.next()
            self.expect('(')
            st = self.tok
            if st.kind != 'str':
                raise CompileError('asm needs a string with BEAG assembly', st)
            codes = []
            while self.tok.kind == 'str':
                codes.extend(self.next().value)
            self.expect(')')
            self.expect(';')
            return Node('asm', t, text=''.join(chr(c) for c in codes))
        if t.kind == 'id' and t.text not in KEYWORDS and self.peek(1).text == ':':
            self.next()
            self.next()
            lab = self.func_label(t)
            if lab.defined:
                raise CompileError(f'label {t.text!r} is defined twice', t)
            lab.defined = True
            stmt = self.statement() if not self.at('}') else Node('empty', t)
            return Node('label', t, label=lab, stmt=stmt)
        e = self.expression()
        self.expect(';')
        return Node('expr', t, e=e)

    def func_label(self, tok):
        labs = self.func.labels
        if tok.text not in labs:
            labs[tok.text] = Node('goto_label', tok, name=tok.text, defined=False, asm=None)
        return labs[tok.text]

    def condition(self):
        e = self.rv(self.expression())
        if not e.type.is_scalar:
            raise CompileError(f'a condition needs a number or a pointer, not {e.type}', e.tok)
        return e

    # -- expressions --------------------------------------------------------------------------

    def expression(self):
        e = self.assignment()
        while self.at(','):
            t = self.next()
            b = self.assignment()
            e = Node('comma', t, self.rv(b).type, a=e, b=self.rv(b))
        return e

    def assignment(self):
        lhs = self.conditional()
        if self.tok.kind == 'punct' and self.tok.text in ASSIGN_OPS:
            t = self.next()
            rhs = self.assignment()
            return self.make_assign(t, t.text, lhs, rhs)
        return lhs

    def conditional(self):
        c = self.binary(1)
        if self.at('?'):
            t = self.next()
            c = self.rv(c)
            self.check_scalar(c, 'the condition of ?:')
            a = self.rv(self.expression())
            self.expect(':')
            b = self.rv(self.conditional())
            if a.type.is_int and b.type.is_int:
                rt = arith_type(a.type, b.type)
            elif a.type.is_ptr and (b.type.is_ptr or self.is_null(b)):
                rt = a.type
            elif b.type.is_ptr and self.is_null(a):
                rt = b.type
            elif a.type.is_void and b.type.is_void:
                rt = VOID
            elif a.type.is_struct and a.type is b.type:
                raise CompileError('?: with struct values is not supported', t)
            else:
                raise CompileError(f'the two sides of ?: have different types ({a.type} and {b.type})', t)
            if c.kind == 'num':
                return a if c.val else b
            return Node('cond', t, rt, c=c, a=a, b=b)
        return c

    def binary(self, prec):
        if prec > 10:
            return self.cast()
        e = self.binary(prec + 1)
        while self.tok.kind == 'punct' and BINARY_PREC.get(self.tok.text) == prec:
            t = self.next()
            rhs = self.binary(prec + 1)
            e = self.make_binary(t, t.text, e, rhs)
        return e

    def cast(self):
        if self.at('(') and self.starts_type(self.peek(1)):
            t = self.next()
            ty = self.type_name()
            self.expect(')')
            if self.at('{'):
                raise CompileError('compound literals are not supported', self.tok)
            e = self.rv(self.cast())
            return self.make_cast(t, ty, e)
        return self.unary()

    def unary(self):
        t = self.tok
        if t.kind == 'punct':
            op = t.text
            if op in ('++', '--'):
                self.next()
                e = self.unary()
                return self.make_incdec(t, op, e, post=False)
            if op == '&':
                self.next()
                e = self.cast()
                return self.make_addr(t, e)
            if op == '*':
                self.next()
                e = self.rv(self.cast())
                return self.make_deref(t, e)
            if op in ('-', '+', '~', '!'):
                self.next()
                e = self.rv(self.cast())
                return self.make_unary(t, op, e)
        if t.kind == 'id' and t.text == 'sizeof':
            self.next()
            if self.at('(') and self.starts_type(self.peek(1)):
                self.next()
                ty = self.type_name()
                self.expect(')')
            else:
                ty = self.unary().type
            if ty.is_func:
                raise CompileError('sizeof cannot be applied to a function', t)
            if (ty.is_array and ty.length is None) or (ty.is_struct and ty.members is None) or ty.is_void:
                raise CompileError(f'sizeof of an incomplete type ({ty})', t)
            return Node('num', t, UINT, val=ty.size())
        return self.postfix()

    def postfix(self):
        e = self.primary()
        while True:
            t = self.tok
            if t.kind != 'punct':
                return e
            if t.text == '[':
                self.next()
                idx = self.expression()
                self.expect(']')
                a, b = self.rv(e), self.rv(idx)
                if b.type.is_ptr and a.type.is_int:
                    a, b = b, a
                if not a.type.is_ptr:
                    raise CompileError(f'subscripted value is not an array or a pointer (it is {e.type})', t)
                if not b.type.is_int:
                    raise CompileError('an array index must be an integer', idx.tok)
                e = self.make_deref(t, self.make_binary(t, '+', a, b))
            elif t.text == '(':
                self.next()
                args = []
                if not self.at(')'):
                    while True:
                        args.append(self.assignment())
                        if not self.accept(','):
                            break
                self.expect(')')
                e = self.make_call(t, e, args)
            elif t.text in ('.', '->'):
                self.next()
                name = self.ident('a member name')
                if t.text == '.':
                    if not e.type.is_struct:
                        raise CompileError(f'. needs a struct on its left, not {e.type}', t,
                                           note='use -> with a pointer to a struct' if e.type.is_ptr else None)
                    base = Node('addr', t, PtrType(e.type), a=e)
                    st = e.type
                else:
                    p = self.rv(e)
                    if not (p.type.is_ptr and p.type.base.is_struct):
                        raise CompileError(f'-> needs a pointer to a struct on its left, not {p.type}', t)
                    base, st = p, p.type.base
                if st.members is None:
                    raise CompileError(f'{st} is incomplete here', t)
                m = st.member(name.text)
                if m is None:
                    names = ', '.join(x[0] for x in st.members)
                    raise CompileError(f'{st} has no member {name.text!r}', name, note=f'its members: {names}')
                e = Node('member', name, m[1], a=base, offset=m[2])
                e.lvalue = True
            elif t.text in ('++', '--'):
                self.next()
                e = self.make_incdec(t, t.text, e, post=True)
            else:
                return e

    def primary(self):
        t = self.tok
        if t.kind == 'num':
            self.next()
            v, uns, lng, dec = parse_number(t.text, t)
            if lng:
                raise CompileError('long constants are not supported: BEAG is a 16-bit computer', t)
            if v > 0xFFFF:
                raise CompileError(f'{t.text} does not fit in 16 bits', t)
            ty = UINT if (uns or v > 0x7FFF) else INT
            # a decimal constant above 32767 would be long in C; it is unsigned here, but -32768
            # is still the int -32768
            return Node('num', t, ty, val=v, big=dec and not uns and v > 0x7FFF)
        if t.kind == 'char':
            self.next()
            return Node('num', t, INT, val=t.value)
        if t.kind == 'str':
            codes = []
            while self.tok.kind == 'str':
                codes.extend(self.next().value)
            codes.append(0)
            label = self.prog.string_label(codes)
            e = Node('str', t, ArrayType(CHAR, len(codes)), codes=codes, label=label)
            e.lvalue = True
            return e
        if t.kind == 'punct' and t.text == '(':
            self.next()
            e = self.expression()
            self.expect(')')
            return e
        if t.kind == 'id' and t.text not in KEYWORDS:
            self.next()
            sym = self.lookup(t.text)
            if sym is None:
                if self.at('('):
                    raise CompileError(f'function {t.text!r} is not declared',
                                       t, note='declare it before use, or #include the right header')
                raise CompileError(f'{t.text!r} is not declared', t)
            if sym.kind == 'typedef':
                raise CompileError(f'{t.text!r} is a type, not a value', t)
            if sym.kind == 'enum':
                return Node('num', t, INT, val=sym.value)
            e = Node('var', t, sym.type, sym=sym)
            e.lvalue = sym.kind == 'var'
            return e
        if t.kind == 'eof':
            raise CompileError('unexpected end of the file', t)
        raise CompileError(f'expected an expression, found {t.text!r}', t)

    # -- building typed nodes -----------------------------------------------------------------

    def rv(self, e):
        """The value of e: arrays and functions decay to pointers."""
        if e.type.is_array:
            return Node('addr', e.tok, PtrType(e.type.base), a=e)
        if e.type.is_func:
            return Node('addr', e.tok, PtrType(e.type), a=e)
        return e

    def is_null(self, e):
        return e.kind == 'num' and e.val == 0 and e.type.is_int or \
            (e.kind == 'cast' and e.type.is_ptr and e.type.base.is_void and self.is_null(e.a))

    def check_scalar(self, e, what):
        if not e.type.is_scalar:
            raise CompileError(f'{what} needs a number or a pointer, not {e.type}', e.tok)

    def const_int(self, e):
        e = self.rv(e)
        if e.kind != 'num':
            raise CompileError('a constant integer expression is needed here', e.tok)
        return e.val

    def convert(self, e, t, what):
        """Implicit conversion of the value e to type t (assignment, argument, return)."""
        if t.is_void:
            return e
        if t.is_struct:
            if e.type is not t:
                raise CompileError(f'{what}: cannot convert {e.type} to {t}', e.tok)
            return e
        if e.type.is_struct or e.type.is_void:
            raise CompileError(f'{what}: cannot convert {e.type} to {t}', e.tok)
        if t.is_ptr and e.type.is_int and not self.is_null(e):
            warn(f'{what}: integer converted to the pointer type {t} without a cast', e.tok)
        elif t.is_int and e.type.is_ptr:
            warn(f'{what}: pointer converted to {t} without a cast', e.tok)
        elif t.is_ptr and e.type.is_ptr and not (t.base.is_void or e.type.base.is_void) and \
                not same_type(t.base, e.type.base) and not (t.base.is_int and e.type.base.is_int):
            warn(f'{what}: {e.type} converted to the incompatible pointer type {t}', e.tok)
        if e.kind == 'num':
            return Node('num', e.tok, t, val=norm(e.val, t))
        if e.type == t:
            return e
        return Node('cast', e.tok, t, a=e)

    def make_cast(self, t, ty, e):
        if ty.is_void:
            return Node('cast', t, VOID, a=e)
        if not ty.is_scalar:
            raise CompileError(f'cannot cast to {ty}', t)
        if not e.type.is_scalar:
            raise CompileError(f'cannot cast {e.type} to {ty}', t)
        if e.kind == 'num':
            return Node('num', t, ty, val=norm(e.val, ty))
        return Node('cast', t, ty, a=e)

    def make_unary(self, t, op, e):
        if op == '!':
            self.check_scalar(e, '!')
            if e.kind == 'num':
                return Node('num', t, INT, val=int(e.val == 0))
            return Node('not', t, INT, a=e)
        if not e.type.is_int:
            raise CompileError(f'unary {op} needs an integer, not {e.type}', t)
        ty = promote(e.type)
        if op == '+':
            return e if e.type == ty else Node('cast', t, ty, a=e)
        if e.kind == 'num':
            v = -e.val if op == '-' else ~e.val
            if op == '-' and getattr(e, 'big', False) and v >= -32768:
                return Node('num', t, INT, val=v)
            return Node('num', t, ty, val=norm(v, ty))
        return Node('unary', t, ty, op=op, a=e)

    def make_addr(self, t, e):
        if e.type.is_func:
            return Node('addr', t, PtrType(e.type), a=e)
        if not e.lvalue:
            raise CompileError('& needs a variable or another object in memory', t)
        if e.kind == 'var' and e.sym.storage == 'register':
            pass
        return Node('addr', t, PtrType(e.type), a=e)

    def make_deref(self, t, e):
        if not e.type.is_ptr:
            raise CompileError(f'* needs a pointer, not {e.type}', t)
        base = e.type.base
        if base.is_void:
            raise CompileError('cannot dereference a void * (cast it to another pointer type first)', t)
        if e.kind == 'addr' and not e.a.type.is_func and same_type(e.a.type, base) and \
                not e.a.type.is_array:
            return e.a                 # *&x is x (but not *a for an array a: that is a[0])
        n = Node('deref', t, base, a=e)
        n.lvalue = not base.is_func
        return n

    def ptr_add(self, p, k):
        """p + k words (no scaling)."""
        if k == 0:
            return p
        return Node('binop', p.tok, p.type, op='+', a=p, b=Node('num', p.tok, INT, val=k), uns=False)

    def scaled(self, t, n, size):
        if size == 1:
            return n
        if n.kind == 'num':
            return Node('num', t, INT, val=norm(n.val * size, INT))
        return Node('binop', t, INT, op='*', a=n, b=Node('num', t, INT, val=size), uns=False)

    def make_binary(self, t, op, a, b):
        if op in ('&&', '||'):
            a, b = self.rv(a), self.rv(b)
            self.check_scalar(a, op)
            self.check_scalar(b, op)
            if a.kind == 'num':
                if (op == '&&') == (a.val != 0):
                    if b.kind == 'num':
                        return Node('num', t, INT, val=int(b.val != 0))
                    return Node('bool', t, INT, a=b)
                return Node('num', t, INT, val=int(op == '||'))
            return Node('logand' if op == '&&' else 'logor', t, INT, a=a, b=b)
        a, b = self.rv(a), self.rv(b)
        ta, tb = a.type, b.type
        if op in ('==', '!=', '<', '>', '<=', '>='):
            if ta.is_int and tb.is_int:
                ct = arith_type(ta, tb)
                if a.kind == 'num' and b.kind == 'num':
                    x, y = norm(a.val, ct), norm(b.val, ct)
                    r = {'==': x == y, '!=': x != y, '<': x < y, '>': x > y, '<=': x <= y, '>=': x >= y}[op]
                    return Node('num', t, INT, val=int(r))
                return Node('cmp', t, INT, op=op, a=a, b=b, uns=ct.unsigned)
            if ta.is_ptr and tb.is_ptr or ta.is_ptr and self.is_null(b) or tb.is_ptr and self.is_null(a):
                if ta.is_ptr and tb.is_ptr and not same_type(ta.base, tb.base) and \
                        not (ta.base.is_void or tb.base.is_void):
                    warn(f'comparison of different pointer types ({ta} and {tb})', t)
                return Node('cmp', t, INT, op=op, a=a, b=b, uns=True)
            if ta.is_scalar and tb.is_scalar:
                warn(f'comparison between {ta} and {tb}', t)
                return Node('cmp', t, INT, op=op, a=a, b=b, uns=True)
            raise CompileError(f'cannot compare {ta} and {tb}', t)
        if op == '+':
            if ta.is_int and tb.is_ptr:
                a, b, ta, tb = b, a, tb, ta
            if ta.is_ptr and tb.is_int:
                self.check_complete_pointee(ta, t)
                off = self.scaled(t, b, ta.base.size())
                if off.kind == 'num' and off.val == 0:
                    return a
                return Node('binop', t, ta, op='+', a=a, b=off, uns=False)
        if op == '-':
            if ta.is_ptr and tb.is_int:
                self.check_complete_pointee(ta, t)
                return Node('binop', t, ta, op='-', a=a, b=self.scaled(t, b, ta.base.size()), uns=False)
            if ta.is_ptr and tb.is_ptr:
                if not same_type(ta.base, tb.base):
                    raise CompileError(f'subtracting pointers of different types ({ta} and {tb})', t)
                self.check_complete_pointee(ta, t)
                d = Node('binop', t, INT, op='-', a=a, b=b, uns=False)
                sz = ta.base.size()
                if sz != 1:
                    d = Node('binop', t, INT, op='/', a=d, b=Node('num', t, INT, val=sz), uns=False)
                return d
        if not (ta.is_int and tb.is_int):
            raise CompileError(f'invalid operands to {op} ({ta} and {tb})', t)
        if op in ('<<', '>>'):
            rt = promote(ta)
        else:
            rt = arith_type(ta, tb)
        if a.kind == 'num' and b.kind == 'num':
            return Node('num', t, rt, val=fold(op, a.val, b.val, rt, t))
        return Node('binop', t, rt, op=op, a=a, b=b, uns=rt.unsigned)

    def check_complete_pointee(self, pt, t):
        b = pt.base
        if b.is_void:
            raise CompileError('arithmetic on a void * (cast it to another pointer type first)', t)
        if b.is_func:
            raise CompileError('arithmetic on a function pointer', t)
        if b.is_struct and b.members is None:
            raise CompileError(f'arithmetic on a pointer to an incomplete {b}', t)

    def check_modifiable(self, e, t, what):
        if not e.lvalue:
            raise CompileError(f'{what} needs a variable (or another object in memory) on the left', t)
        if e.type.is_array:
            raise CompileError('an array cannot be assigned to (copy it element by element)', t)
        if e.type.const:
            name = f' {e.sym.name!r}' if e.kind == 'var' else ''
            raise CompileError(f'{what}: the object{name} is const and cannot be changed', t)

    def make_assign(self, t, op, lhs, rhs):
        self.check_modifiable(lhs, t, 'assignment' if op == '=' else op)
        rhs = self.rv(rhs)
        if op == '=':
            if lhs.type.is_struct:
                if rhs.type is not lhs.type:
                    raise CompileError(f'cannot assign {rhs.type} to {lhs.type}', t)
                return Node('assign', t, lhs.type, op='=', a=lhs, b=rhs)
            return Node('assign', t, lhs.type, op='=', a=lhs, b=self.convert(rhs, lhs.type, 'assignment'))
        bop = op[:-1]
        lt = lhs.type
        if lt.is_ptr and bop in ('+', '-'):
            if not rhs.type.is_int:
                raise CompileError(f'{op} on a pointer needs an integer', t)
            self.check_complete_pointee(lt, t)
            return Node('assign', t, lt, op=bop, a=lhs, b=self.scaled(t, rhs, lt.base.size()), uns=False)
        if not (lt.is_int and rhs.type.is_int):
            raise CompileError(f'invalid operands to {op} ({lt} and {rhs.type})', t)
        ct = promote(lt) if bop in ('<<', '>>') else arith_type(lt, rhs.type)
        return Node('assign', t, lt, op=bop, a=lhs, b=rhs, uns=ct.unsigned)

    def make_incdec(self, t, op, e, post):
        self.check_modifiable(e, t, op)
        if not e.type.is_scalar:
            raise CompileError(f'{op} needs a number or a pointer, not {e.type}', t)
        step = 1
        if e.type.is_ptr:
            self.check_complete_pointee(e.type, t)
            step = e.type.base.size()
        return Node('incdec', t, e.type, op=op, post=post, a=e, step=step if op == '++' else -step)

    def make_call(self, t, f, args):
        fp = self.rv(f)
        if not (fp.type.is_ptr and fp.type.base.is_func):
            raise CompileError(f'called object is not a function (it is {f.type})', t)
        ft = fp.type.base
        name = f.sym.name if f.kind == 'var' else 'the function'
        conv = []
        if ft.proto:
            if len(args) < len(ft.params) or (len(args) > len(ft.params) and not ft.varargs):
                n = len(ft.params)
                raise CompileError(f'{name}() takes {n} argument{"s" if n != 1 else ""}'
                                   f'{" or more" if ft.varargs else ""}, found {len(args)}', t,
                                   note=f'it is declared as {ft.str_with(name)}')
        for k, a in enumerate(args):
            a = self.rv(a)
            if a.type.is_struct:
                raise CompileError('passing a struct by value is not supported; pass a pointer to it', a.tok)
            if a.type.is_void:
                raise CompileError('a void value cannot be an argument', a.tok)
            if ft.proto and k < len(ft.params):
                a = self.convert(a, ft.params[k], f'argument {k + 1} of {name}()')
            conv.append(a)
        if ft.ret.is_struct:
            raise CompileError('functions returning a struct are not supported; return a pointer', t)
        direct = f.sym if f.kind == 'var' and f.sym.kind == 'func' else None
        return Node('call', t, ft.ret, f=fp, args=conv, direct=direct)


class _InitIter:
    def __init__(self, items):
        self.items, self.k = items, 0

    def done(self):
        return self.k >= len(self.items)

    def peek(self):
        return self.items[self.k][1]

    def peek_desig(self):
        return self.items[self.k][0] if not self.done() else None

    def strip_desig(self):
        self.items = list(self.items)
        self.items[self.k] = (None, self.items[self.k][1])

    def take(self):
        it = self.items[self.k][1]
        self.k += 1
        return it

    def tok(self):
        it = self.items[min(self.k, len(self.items) - 1)][1]
        return it.tok

    def is_top_of(self, t):
        return False


def same_type(a, b):
    if a is b:
        return True
    if a.is_struct or b.is_struct:
        return a is b
    if a.is_int and b.is_int:
        return a.unsigned == b.unsigned and (a.name == b.name or {a.name, b.name} <= {'int', 'enum'})
    if a.kind != b.kind:
        return False
    if a.is_ptr:
        return same_type(a.base, b.base) or a.base.is_void or b.base.is_void
    if a.is_array:
        return same_type(a.base, b.base) and (a.length is None or b.length is None or a.length == b.length)
    if a.is_func:
        if not same_type(a.ret, b.ret):
            return False
        if a.proto and b.proto:
            return a.varargs == b.varargs and len(a.params) == len(b.params) and \
                all(same_type(x, y) for x, y in zip(a.params, b.params))
        return True
    return a.kind == b.kind


def fold(op, x, y, t, tok):
    """Constant folding with 16-bit results, as BEAG computes them."""
    x, y = norm(x, t), norm(y, t)
    if op == '+': v = x + y
    elif op == '-': v = x - y
    elif op == '*': v = x * y
    elif op in ('/', '%'):
        if y == 0:
            raise CompileError('division by zero in a constant expression', tok)
        q = abs(x) // abs(y) * (1 if (x < 0) == (y < 0) else -1)
        v = q if op == '/' else x - q * y
    elif op == '&': v = x & y
    elif op == '|': v = x | y
    elif op == '^': v = x ^ y
    elif op == '<<': v = x << y if 0 <= y < 16 else 0
    elif op == '>>':
        if y >= 16:
            y = 15
        v = x >> y if t.unsigned else x >> y      # Python's >> floors, as an arithmetic shift does
    else:
        raise CompileError(f'cannot fold {op}', tok)
    return norm(v, t)
