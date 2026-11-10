"""Lexer and preprocessor of beagcc, the C compiler for the BEAG computer."""

import os
import re


class CompileError(Exception):
    def __init__(self, msg, tok=None, note=None):
        super().__init__(msg)
        self.msg, self.tok, self.note = msg, tok, note

    def __str__(self):
        if self.tok is None or self.tok.file is None:
            return f'error: {self.msg}'
        return f'{location(self.tok)}: error: {self.msg}' + source_excerpt(self.tok) + \
            (f'\n    note: {self.note}' if self.note else '')


SOURCES = {}            # file name -> list of lines, for error messages and comments in the output
WARNINGS = []


def location(tok):
    return f'{tok.file}:{tok.line}:{tok.col}'


def source_excerpt(tok):
    lines = SOURCES.get(tok.file)
    if not lines or not 0 < tok.line <= len(lines):
        return ''
    text = lines[tok.line - 1].rstrip('\n').expandtabs(4)
    return f'\n    {text}\n    {" " * max(tok.col - 1, 0)}^'


def warn(msg, tok=None):
    if tok is not None and tok.file:
        WARNINGS.append(f'{location(tok)}: warning: {msg}' + source_excerpt(tok))
    else:
        WARNINGS.append(f'warning: {msg}')


class Token:
    __slots__ = ('kind', 'value', 'text', 'file', 'line', 'col', 'bol', 'space', 'hide')

    def __init__(self, kind, value, text, file, line, col, bol=False, space=False, hide=frozenset()):
        self.kind, self.value, self.text = kind, value, text
        self.file, self.line, self.col = file, line, col
        self.bol, self.space, self.hide = bol, space, hide

    def copy(self, **kw):
        t = Token(self.kind, self.value, self.text, self.file, self.line, self.col, self.bol,
                  self.space, self.hide)
        for k, v in kw.items():
            setattr(t, k, v)
        return t

    def __repr__(self):
        return f'Token({self.kind},{self.text!r},{self.line})'


PUNCTUATORS = ['...', '<<=', '>>=', '->', '++', '--', '<<', '>>', '<=', '>=', '==', '!=', '&&', '||',
               '+=', '-=', '*=', '/=', '%=', '&=', '^=', '|=', '##',
               '[', ']', '(', ')', '{', '}', '.', '&', '*', '+', '-', '~', '!', '/', '%', '<', '>',
               '^', '|', '?', ':', ';', '=', ',', '#']

TOKEN_RE = re.compile(r"""
    (?P<nl>\n)
  | (?P<ws>[ \t\r\f\v]+|\\\n)
  | (?P<lcomment>//[^\n]*)
  | (?P<bcomment>/\*.*?\*/)
  | (?P<ubcomment>/\*)
  | (?P<num>(?:0[xX][0-9a-fA-F]+|[0-9]+(?:\.[0-9]*)?(?:[eE][-+]?[0-9]+)?|\.[0-9]+(?:[eE][-+]?[0-9]+)?)[a-zA-Z_0-9]*)
  | (?P<char>[LuU]?'(?:\\.|[^'\\\n])*')
  | (?P<str>[LuU]?(?:u8)?"(?:\\.|[^"\\\n])*")
  | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<punct>""" + '|'.join(re.escape(p) for p in PUNCTUATORS) + r""")
""", re.VERBOSE | re.DOTALL)

SIMPLE_ESCAPES = {'n': 10, 't': 9, 'r': 13, 'a': 7, 'b': 8, 'f': 12, 'v': 11, 'e': 27,
                  '\\': 92, "'": 39, '"': 34, '?': 63}


def decode_escapes(body, tok):
    out = []
    i = 0
    while i < len(body):
        c = body[i]
        if c != '\\':
            out.append(ord(c))
            i += 1
            continue
        i += 1
        e = body[i]
        if e in SIMPLE_ESCAPES:
            out.append(SIMPLE_ESCAPES[e])
            i += 1
        elif e == 'x':
            m = re.match(r'[0-9a-fA-F]+', body[i + 1:])
            if not m:
                raise CompileError('\\x needs hex digits', tok)
            out.append(int(m.group(), 16) & 0xFFFF)
            i += 1 + len(m.group())
        elif e in '01234567':
            m = re.match(r'[0-7]{1,3}', body[i:])
            out.append(int(m.group(), 8))
            i += len(m.group())
        else:
            raise CompileError(f'unknown escape sequence \\{e}', tok)
    return out


def parse_number(text, tok):
    """(value, unsigned_suffix, long_suffix, is_decimal) of an integer constant."""
    m = re.match(r'^(0[xX][0-9a-fA-F]+|[0-9]+)([uUlL]*)$', text)
    if not m:
        if re.match(r'^[0-9]*\.|^[0-9]+[eE]|^\.', text):
            raise CompileError('floating-point numbers are not supported (BEAG has only 16-bit integers)', tok)
        raise CompileError(f'invalid number {text!r}', tok)
    digits, suffix = m.groups()
    s = suffix.lower()
    if s not in ('', 'u', 'l', 'ul', 'lu', 'll', 'ull', 'llu'):
        raise CompileError(f'invalid suffix {suffix!r} on number', tok)
    if digits[:2] in ('0x', '0X'):
        v, dec = int(digits[2:], 16), False
    elif digits.startswith('0') and len(digits) > 1:
        if not re.match(r'^[0-7]+$', digits):
            raise CompileError(f'invalid octal number {digits!r}', tok)
        v, dec = int(digits, 8), False
    else:
        v, dec = int(digits), True
    return v, 'u' in s, 'l' in s, dec


def lex(text, filename):
    """Tokens of one file. Comments become spaces; bol marks the first token of a line."""
    SOURCES[filename] = text.split('\n')
    toks = []
    pos, line, line_start = 0, 1, 0
    bol, space = True, False
    n = len(text)
    while pos < n:
        m = TOKEN_RE.match(text, pos)
        if not m:
            t = Token('punct', text[pos], text[pos], filename, line, pos - line_start + 1)
            raise CompileError(f'unexpected character {text[pos]!r}', t)
        kind = m.lastgroup
        s = m.group()
        col = pos - line_start + 1
        tline = line
        if kind == 'nl':
            line += 1
            line_start = m.end()
            bol, space = True, False
        elif kind in ('ws', 'lcomment', 'bcomment'):
            nls = s.count('\n')
            if nls:
                line += nls
                line_start = pos + s.rfind('\n') + 1
                if kind == 'bcomment':
                    pass                    # a comment spanning lines does not start a new line
            space = True
        elif kind == 'ubcomment':
            raise CompileError('unterminated /* comment', Token('punct', '/*', '/*', filename, line, col))
        else:
            tok = Token(kind, None, s, filename, tline, col, bol, space)
            if kind == 'char':
                body = s[s.index("'") + 1:-1]
                codes = decode_escapes(body, tok)
                if len(codes) != 1:
                    raise CompileError('a character constant must hold exactly one character', tok)
                tok.value = codes[0]
            elif kind == 'str':
                body = s[s.index('"') + 1:-1]
                tok.value = decode_escapes(body, tok)
            toks.append(tok)
            bol, space = False, False
        pos = m.end()
    return toks


# ----------------------------------------------------------------------------------------------
# Preprocessor

class Macro:
    __slots__ = ('name', 'params', 'variadic', 'body', 'builtin')

    def __init__(self, name, params, variadic, body, builtin=None):
        self.name, self.params, self.variadic, self.body, self.builtin = name, params, variadic, body, builtin


def eof_token(file, line):
    return Token('eof', None, '', file, line, 1, True)


class Preprocessor:
    def __init__(self, include_dirs=(), defines=None):
        self.include_dirs = list(include_dirs)
        self.macros = {}
        self.once = set()
        self.depth = 0
        for name, val in {'__BEAG__': '1', '__STDC__': '1', '__STDC_VERSION__': '199901L',
                          '__CHAR_BIT__': '16', '__INT_MAX__': '32767'}.items():
            self.define_text(name, val)
        self.macros['__FILE__'] = Macro('__FILE__', None, False, [], builtin='file')
        self.macros['__LINE__'] = Macro('__LINE__', None, False, [], builtin='line')
        for d in (defines or []):
            name, _, val = d.partition('=')
            self.define_text(name, val or '1')

    def define_text(self, name, value):
        self.macros[name] = Macro(name, None, False, lex(value, '<command line>'))

    # -- files --------------------------------------------------------------------------------

    def find_include(self, name, angle, tok):
        dirs = ([] if angle else [os.path.dirname(tok.file)]) + self.include_dirs
        for d in dirs:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
        raise CompileError(f'cannot find the include file {name!r}', tok)

    def process_file(self, path, tok=None):
        try:
            with open(path, encoding='utf-8') as f:
                text = f.read()
        except OSError as e:
            raise CompileError(f'cannot read {path}: {e.strerror}', tok)
        if not text.endswith('\n'):
            text += '\n'
        self.depth += 1
        if self.depth > 40:
            raise CompileError('#include nested too deeply (does a file include itself?)', tok)
        out = self.process(lex(text, path), path)
        self.depth -= 1
        return out

    # -- directives ---------------------------------------------------------------------------

    def process(self, toks, path):
        out = []
        pending = []                  # ordinary lines waiting for macro expansion
        conds = []                    # stack of [active, taken, seen_else, tok]
        i = 0
        n = len(toks)

        def active():
            return all(c[0] for c in conds)

        while i < n:
            t = toks[i]
            if t.bol and t.kind == 'punct' and t.text == '#':
                j = i + 1
                while j < n and not toks[j].bol:
                    j += 1
                line = toks[i + 1:j]
                i = j
                if pending:
                    out.extend(self.expand(pending))
                    pending = []
                self.directive(t, line, conds, active, out)
                continue
            # an ordinary line
            j = i + 1
            while j < n and not toks[j].bol:
                j += 1
            if active():
                pending.extend(toks[i:j])
            i = j
        if pending:
            out.extend(self.expand(pending))
        if conds:
            raise CompileError('#if without #endif', conds[-1][3])
        return out

    def directive(self, hash_tok, line, conds, active, out):
        if not line:
            return
        d = line[0]
        name = d.text
        args = line[1:]
        if name in ('ifdef', 'ifndef'):
            if not args or args[0].kind != 'id':
                raise CompileError(f'#{name} needs a macro name', d)
            if not active():
                conds.append([False, True, False, d])
                return
            v = (args[0].text in self.macros) == (name == 'ifdef')
            conds.append([v, v, False, d])
        elif name == 'if':
            if not active():
                conds.append([False, True, False, d])
                return
            v = self.eval_if(args, d) != 0
            conds.append([v, v, False, d])
        elif name == 'elif':
            if not conds:
                raise CompileError('#elif without #if', d)
            c = conds[-1]
            if c[2]:
                raise CompileError('#elif after #else', d)
            parent = all(x[0] for x in conds[:-1])
            if c[1] or not parent:
                c[0] = False
            else:
                v = self.eval_if(args, d) != 0
                c[0] = v
                c[1] = v
        elif name == 'else':
            if not conds:
                raise CompileError('#else without #if', d)
            c = conds[-1]
            if c[2]:
                raise CompileError('#else after #else', d)
            c[2] = True
            c[0] = not c[1]
            c[1] = True
        elif name == 'endif':
            if not conds:
                raise CompileError('#endif without #if', d)
            conds.pop()
        elif not active():
            return
        elif name == 'define':
            self.define(args, d)
        elif name == 'undef':
            if args:
                self.macros.pop(args[0].text, None)
        elif name == 'include':
            self.include(args, d, out)
        elif name == 'error':
            raise CompileError('#error ' + ' '.join(a.text for a in args), d)
        elif name == 'warning':
            warn(' '.join(a.text for a in args), d)
        elif name == 'pragma':
            if args and args[0].text == 'once':
                self.once.add(os.path.abspath(d.file))
        elif name == 'line':
            pass
        else:
            raise CompileError(f'unknown preprocessor directive #{name}', d)

    def include(self, args, d, out):
        if args and args[0].kind == 'str':
            name, angle = args[0].text[1:-1], False
        elif args and args[0].text == '<':
            k = 1
            parts = []
            while k < len(args) and args[k].text != '>':
                parts.append(args[k].text)
                k += 1
            name, angle = ''.join(parts), True
        else:
            expanded = self.expand(args)
            if expanded and expanded[0].kind == 'str':
                name, angle = expanded[0].text[1:-1], False
            else:
                raise CompileError('#include needs "file" or <file>', d)
        path = self.find_include(name, angle, d)
        if os.path.abspath(path) in self.once:
            return
        out.extend(self.process_file(path, d))

    def define(self, args, d):
        if not args or args[0].kind != 'id':
            raise CompileError('#define needs a macro name', d)
        name = args[0].text
        if name == 'defined':
            raise CompileError('"defined" cannot be a macro name', args[0])
        params = None
        variadic = False
        body = args[1:]
        if len(args) > 1 and args[1].text == '(' and not args[1].space:
            params = []
            k = 2
            while True:
                if k >= len(args):
                    raise CompileError('unfinished macro parameter list', d)
                a = args[k]
                if a.text == ')':
                    k += 1
                    break
                if a.text == '...':
                    variadic = True
                    params.append('__VA_ARGS__')
                elif a.kind == 'id':
                    params.append(a.text)
                else:
                    raise CompileError(f'bad macro parameter {a.text!r}', a)
                k += 1
                if k < len(args) and args[k].text == ',':
                    k += 1
            body = args[k:]
        self.macros[name] = Macro(name, params, variadic, body)

    # -- #if expressions ----------------------------------------------------------------------

    def eval_if(self, args, d):
        toks = []
        k = 0
        while k < len(args):
            a = args[k]
            if a.kind == 'id' and a.text == 'defined':
                if k + 1 < len(args) and args[k + 1].text == '(':
                    nm = args[k + 2] if k + 2 < len(args) else None
                    k += 4
                else:
                    nm = args[k + 1] if k + 1 < len(args) else None
                    k += 2
                if nm is None or nm.kind != 'id':
                    raise CompileError('defined needs a macro name', a)
                toks.append(a.copy(kind='num', text='1' if nm.text in self.macros else '0'))
                continue
            toks.append(a)
            k += 1
        toks = self.expand(toks)
        toks = [t.copy(kind='num', text='0') if t.kind == 'id' else t for t in toks]
        if not toks:
            raise CompileError('#if needs an expression', d)
        p = _IfParser(toks, d)
        v = p.expr()
        if p.i != len(toks):
            raise CompileError(f'unexpected {toks[p.i].text!r} in #if', toks[p.i])
        return v

    # -- macro expansion ----------------------------------------------------------------------

    def expand(self, toks):
        out = []
        ts = list(toks)
        i = 0
        while i < len(ts):
            t = ts[i]
            m = self.macros.get(t.text) if t.kind == 'id' else None
            if m is None or t.text in t.hide:
                out.append(t)
                i += 1
                continue
            if m.builtin:
                if m.builtin == 'file':
                    s = '"' + t.file.replace('\\', '/') + '"'
                    out.append(t.copy(kind='str', text=s, value=[ord(c) for c in s[1:-1]]))
                else:
                    out.append(t.copy(kind='num', text=str(t.line)))
                i += 1
                continue
            if m.params is None:
                body = self.substitute(m, {}, t.hide | {m.name}, t)
                ts[i:i + 1] = body
                continue
            # function-like: needs '(' next
            if i + 1 >= len(ts) or ts[i + 1].text != '(':
                out.append(t)
                i += 1
                continue
            args, end = self.collect_args(ts, i + 1, t)
            if len(args) == 1 and not args[0] and not m.params:
                args = []
            if m.variadic:
                fixed = len(m.params) - 1
                if len(args) < fixed:
                    raise CompileError(f'macro {m.name} needs at least {fixed} arguments', t)
                rest = []
                for k, a in enumerate(args[fixed:]):
                    if k:
                        rest.append(t.copy(kind='punct', text=','))
                    rest.extend(a)
                args = args[:fixed] + [rest]
            if len(args) != len(m.params):
                raise CompileError(f'macro {m.name} takes {len(m.params)} arguments, found {len(args)}', t)
            hs = (t.hide & ts[end].hide) | {m.name}
            body = self.substitute(m, dict(zip(m.params, args)), hs, t)
            ts[i:end + 1] = body
        return out

    def collect_args(self, ts, k, mtok):
        assert ts[k].text == '('
        depth = 0
        args = [[]]
        k += 1
        while k < len(ts):
            a = ts[k]
            if a.text == '(':
                depth += 1
            elif a.text == ')':
                if depth == 0:
                    return args, k
                depth -= 1
            elif a.text == ',' and depth == 0:
                args.append([])
                k += 1
                continue
            args[-1].append(a)
            k += 1
        raise CompileError(f'unterminated call of macro {mtok.text}', mtok)

    def substitute(self, m, args, hs, origin):
        body = m.body
        res = []
        k = 0
        while k < len(body):
            b = body[k]
            if b.text == '#' and m.params is not None and k + 1 < len(body) and body[k + 1].text in args:
                arg = args[body[k + 1].text]
                s = ''
                for j, a in enumerate(arg):
                    if j and a.space:
                        s += ' '
                    s += a.text
                s = '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
                res.append(origin.copy(kind='str', text=s, value=[ord(c) for c in
                                                                   s[1:-1].replace('\\"', '"').replace('\\\\', '\\')],
                                       space=b.space))
                k += 2
                continue
            if b.kind == 'id' and b.text in args:
                pasted = (k + 1 < len(body) and body[k + 1].text == '##') or (k > 0 and body[k - 1].text == '##')
                arg = args[b.text] if pasted else self.expand(args[b.text])
                for j, a in enumerate(arg):
                    res.append(a.copy(space=b.space if j == 0 else a.space))
                if not arg and pasted:
                    res.append(origin.copy(kind='placemarker', text=''))
                k += 1
                continue
            res.append(b.copy())
            k += 1
        # token pasting
        out = []
        k = 0
        while k < len(res):
            if res[k].text == '##' and res[k].kind == 'punct' and out:
                left = out.pop()
                right = res[k + 1] if k + 1 < len(res) else None
                text = left.text + (right.text if right else '')
                if text:
                    newt = lex(text, '<paste>')
                    if len(newt) != 1:
                        raise CompileError(f'pasting gives {text!r}, which is not one token', origin)
                    out.append(newt[0].copy(space=left.space))
                k += 2
                continue
            out.append(res[k])
            k += 1
        final = []
        for x in out:
            if x.kind == 'placemarker':
                continue
            final.append(x.copy(file=origin.file, line=origin.line, col=origin.col, bol=False,
                                hide=x.hide | hs))
        if final:
            final[0].space = origin.space
        return final


class _IfParser:
    """Integer expressions of #if."""
    BIN = [('||',), ('&&',), ('|',), ('^',), ('&',), ('==', '!='), ('<', '>', '<=', '>='), ('<<', '>>'),
           ('+', '-'), ('*', '/', '%')]

    def __init__(self, toks, d):
        self.toks, self.i, self.d = toks, 0, d

    def peek(self):
        return self.toks[self.i].text if self.i < len(self.toks) else None

    def take(self):
        t = self.toks[self.i] if self.i < len(self.toks) else None
        if t is None:
            raise CompileError('#if expression is incomplete', self.d)
        self.i += 1
        return t

    def expr(self):
        c = self.binary(0)
        if self.peek() == '?':
            self.take()
            a = self.expr()
            if self.take().text != ':':
                raise CompileError('expected : in #if', self.d)
            b = self.expr()
            return a if c else b
        return c

    def binary(self, lvl):
        if lvl == len(self.BIN):
            return self.unary()
        v = self.binary(lvl + 1)
        while self.peek() in self.BIN[lvl]:
            op = self.take().text
            w = self.binary(lvl + 1)
            if op == '||': v = int(bool(v) or bool(w))
            elif op == '&&': v = int(bool(v) and bool(w))
            elif op == '|': v |= w
            elif op == '^': v ^= w
            elif op == '&': v &= w
            elif op == '==': v = int(v == w)
            elif op == '!=': v = int(v != w)
            elif op == '<': v = int(v < w)
            elif op == '>': v = int(v > w)
            elif op == '<=': v = int(v <= w)
            elif op == '>=': v = int(v >= w)
            elif op == '<<': v <<= w
            elif op == '>>': v >>= w
            elif op == '+': v += w
            elif op == '-': v -= w
            elif op == '*': v *= w
            elif op in '/%':
                if w == 0:
                    raise CompileError('division by zero in #if', self.d)
                q = abs(v) // abs(w) * (1 if (v < 0) == (w < 0) else -1)
                v = q if op == '/' else v - q * w
        return v

    def unary(self):
        t = self.take()
        if t.text == '-': return -self.unary()
        if t.text == '+': return self.unary()
        if t.text == '!': return int(not self.unary())
        if t.text == '~': return ~self.unary()
        if t.text == '(':
            v = self.expr()
            if self.take().text != ')':
                raise CompileError('expected ) in #if', self.d)
            return v
        if t.kind == 'num':
            return parse_number(t.text, t)[0]
        if t.kind == 'char':
            return t.value
        raise CompileError(f'unexpected {t.text!r} in #if', t)
