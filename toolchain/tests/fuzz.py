#!/usr/bin/env python3
"""Random test programs: compiled by beagcc and run in beagsim, and compiled by the computer's
own C compiler with every operation cut to 16 bits; the two outputs must be the same.

    python3 tests/fuzz.py [count] [--seed N] [--keep DIR]

The same program text serves both compilers: macros (I, U, WI, WU, ...) mean plain int and
unsigned for BEAG, and short / unsigned short with explicit 16-bit wrap-around natively.
"""

import argparse
import os
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import beagasm  # noqa: E402
import beagcc  # noqa: E402
import beagsim  # noqa: E402

BEAG_PRELUDE = r'''
#include <stdio.h>
#define I int
#define U unsigned
#define WI(x) (x)
#define WU(x) (x)
#define CI(x) ((int)(x))
#define CU(x) ((unsigned)(x))
#define SHLI(a, n) ((a) << (n))
'''

HOST_PRELUDE = r'''
#include <stdio.h>
#define I short
#define U unsigned short
#define WI(x) ((short)(x))
#define WU(x) ((unsigned short)(x))
#define CI(x) ((short)(x))
#define CU(x) ((unsigned short)(x))
#define SHLI(a, n) ((short)((unsigned)(unsigned short)(a) << (n)))
'''

COMMON = r'''
I nzi(I x) { return x ? x : 1; }
U nzu(U x) { return x ? x : 1u; }
I gi[8];
U gu[8];
I g1 = 1234, g2 = -77;
U h1 = 50000u;
I f1(I a) { return WI(a * 3 - 7); }
I f3(I a, I b, I c) { return WI(WI(a - b) * c); }
U fu(U a, U b) { return WU(a / nzu(b) + (a % nzu(b))); }
I rec(I n) { return n <= 0 ? 0 : WI(n + rec(n - 1)); }
'''


class Gen:
    def __init__(self, rnd):
        self.r = rnd

    def const(self, t):
        r = self.r
        k = r.random()
        if t == 'I':
            v = r.choice([0, 1, -1, 2, 7, 10, 100, 127, 128, -128, 255, 256, 1000, 32767, -32768, -32767,
                          16384, -16384]) if k < 0.6 else r.randint(-32768, 32767)
            return '(-32767-1)' if v == -32768 else f'({v})' if v < 0 else str(v)
        v = r.choice([0, 1, 2, 3, 15, 16, 255, 256, 32767, 32768, 40000, 65535]) if k < 0.6 else r.randint(0, 65535)
        return f'{v}u'

    def var(self, t):
        return self.r.choice(self.vars[t])

    def expr(self, t, d):
        r = self.r
        if d <= 0 or r.random() < 0.15:
            return self.const(t) if r.random() < 0.35 else self.var(t)
        k = r.random()
        W = 'WI' if t == 'I' else 'WU'
        if k < 0.40:
            op = r.choice(['+', '-', '*', '+', '-', '&', '|', '^'])
            return f'{W}({self.expr(t, d - 1)} {op} {self.expr(t, d - 1)})'
        if k < 0.50:
            op = r.choice(['/', '%'])
            nz = 'nzi' if t == 'I' else 'nzu'
            return f'{W}({self.expr(t, d - 1)} {op} {nz}({self.expr(t, d - 1)}))'
        if k < 0.58:
            n = str(r.randint(0, 15)) if r.random() < 0.6 else f'({self.expr("I", d - 1)} & 15)'
            if r.random() < 0.5:
                if t == 'I':
                    return f'SHLI({self.expr(t, d - 1)}, {n})'
                return f'WU({self.expr(t, d - 1)} << {n})'
            return f'{W}({self.expr(t, d - 1)} >> {n})'
        if k < 0.70:
            op = r.choice(['<', '<=', '>', '>=', '==', '!='])
            ct = r.choice(['I', 'U'])
            e = f'({self.expr(ct, d - 1)} {op} {self.expr(ct, d - 1)})'
            return e if t == 'I' else f'CU{e}'
        if k < 0.75:
            op = r.choice(['&&', '||'])
            e = f'({self.expr(t, d - 1)} {op} {self.expr(t, d - 1)})'
            return e if t == 'I' else f'CU{e}'
        if k < 0.80:
            op = r.choice(['-', '~', '!'])
            if op == '!':
                return f'{"" if t == "I" else "CU"}(!{self.expr(t, d - 1)})'
            return f'{W}({op}{self.expr(t, d - 1)})'
        if k < 0.85:
            return f'({self.cond(d - 1)} ? {self.expr(t, d - 1)} : {self.expr(t, d - 1)})'
        if k < 0.89:
            other = 'U' if t == 'I' else 'I'
            return f'C{t}({self.expr(other, d - 1)})'
        if k < 0.95:
            arr = r.choice(self.arrays[t])
            return f'{arr}[{self.expr("I", d - 1)} & 7]'
        if t == 'I':
            c = r.random()
            if c < 0.4:
                return f'f1({self.expr("I", d - 1)})'
            if c < 0.8:
                return f'f3({self.expr("I", d - 1)}, {self.expr("I", d - 1)}, {self.expr("I", d - 1)})'
            return f'rec({self.expr("I", d - 1)} & 7)'
        return f'fu({self.expr("U", d - 1)}, {self.expr("U", d - 1)})'

    def cond(self, d):
        t = self.r.choice(['I', 'U'])
        op = self.r.choice(['<', '<=', '>', '>=', '==', '!='])
        return f'({self.expr(t, d)} {op} {self.expr(t, d)})'

    def stmt(self, depth, out, ind):
        r = self.r
        k = r.random()
        t = r.choice(['I', 'U'])
        W = 'WI' if t == 'I' else 'WU'
        v = self.var(t)
        if v.startswith('g') and len(v) == 2 and v[1] in '12' or v == 'h1':
            pass
        if k < 0.45:
            out.append(f'{ind}{v} = {self.expr(t, r.randint(1, 4))};')
        elif k < 0.60:
            op = r.choice(['+', '-', '*', '&', '|', '^'])
            out.append(f'{ind}{v} = {W}({v} {op} {self.expr(t, r.randint(1, 3))});')
        elif k < 0.65:
            op = r.choice(['+=', '-=', '*='])
            out.append(f'{ind}{v} {op} {self.expr(t, r.randint(1, 2))}; {v} = {W}({v});')
        elif k < 0.70:
            out.append(f'{ind}{v}{r.choice(["++", "--"])}; {v} = {W}({v});')
        elif k < 0.78:
            arr = r.choice(self.arrays[t])
            out.append(f'{ind}{arr}[{self.expr("I", 2)} & 7] = {self.expr(t, r.randint(1, 3))};')
        elif k < 0.86 and depth < 2:
            out.append(f'{ind}if {self.cond(2)} {{')
            for _ in range(r.randint(1, 3)):
                self.stmt(depth + 1, out, ind + '    ')
            out.append(f'{ind}}} else {{')
            for _ in range(r.randint(1, 2)):
                self.stmt(depth + 1, out, ind + '    ')
            out.append(f'{ind}}}')
        elif k < 0.92 and depth < 2:
            self.nloop += 1
            lv = f'k{self.nloop}'
            out.append(f'{ind}for ({lv} = 0; {lv} < {r.randint(1, 5)}; {lv}++) {{')
            for _ in range(r.randint(1, 3)):
                self.stmt(depth + 1, out, ind + '    ')
            out.append(f'{ind}}}')
        else:
            out.append(f'{ind}printf("%d %u\\n", {self.expr("I", 3)}, {self.expr("U", 3)});')

    def program(self, nfuncs=2, nstmts=10):
        r = self.r
        parts = [COMMON]
        calls = []
        for fi in range(nfuncs):
            nl = r.randint(2, 8)
            ints = [f'a{i}' for i in range(nl)]
            uns = [f'b{i}' for i in range(r.randint(1, 5))]
            self.vars = {'I': ints + ['g1', 'g2'], 'U': uns + ['h1']}
            self.arrays = {'I': ['gi', 'li'], 'U': ['gu']}
            self.nloop = 0
            body = []
            for _ in range(nstmts):
                self.stmt(0, body, '    ')
            loops = ''.join(f' k{i + 1},' for i in range(self.nloop)).rstrip(',')
            idecl = ', '.join(v + ' = ' + self.const('I') for v in ints)
            udecl = ', '.join(v + ' = ' + self.const('U') for v in uns)
            decl = [f'    I {idecl};', f'    U {udecl};',
                    '    I li[8] = { 3, -1, 4, 1, -5, 9, 2, -6 };']
            if self.nloop:
                decl.append(f'    int{loops};')
            dump = ' '.join('%d' for _ in ints) + ' ' + ' '.join('%u' for _ in uns)
            body.append(f'    printf("{dump}\\n", {", ".join(ints + uns)});')
            body.append('    printf("%d %d %d %d\\n", li[0], li[3], li[5], li[7]);')
            parts.append(f'void t{fi}(void)\n{{\n' + '\n'.join(decl + body) + '\n}\n')
            calls.append(f'    t{fi}();')
        parts.append('int main(void)\n{\n    int i;\n' + '\n'.join(calls) +
                     '\n    for (i = 0; i < 8; i++)\n        printf("%d %u ", gi[i], gu[i]);\n'
                     '    printf("\\n%d %d %u\\n", g1, g2, h1);\n    return 0;\n}\n')
        return '\n'.join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('count', type=int, nargs='?', default=50)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--keep', help='directory to keep failing programs in')
    ap.add_argument('--no-andn-xor', action='store_true', help='compile without the andn and xor instructions')
    ap.add_argument('--vn', action='store_true', help='compile and run for a von Neumann BEAG')
    args = ap.parse_args()
    tmp = tempfile.mkdtemp()
    fails = 0
    total_words = 0
    for n in range(args.count):
        seed = args.seed + n
        src = Gen(random.Random(seed)).program()
        beag_c = os.path.join(tmp, f'f{seed}.c')
        host_c = os.path.join(tmp, f'h{seed}.c')
        with open(beag_c, 'w') as f:
            f.write(BEAG_PRELUDE + src)
        with open(host_c, 'w') as f:
            f.write(HOST_PRELUDE + src)
        exe = os.path.join(tmp, f'h{seed}')
        subprocess.run(['cc', '-w', '-o', exe, host_c], check=True)
        expected = subprocess.run([exe], capture_output=True).stdout.decode()
        try:
            memory = beagcc.MemoryMap.default().as_vonneumann() if args.vn else None
            asm = beagcc.compile_files([beag_c], memory=memory, logic_ops=not args.no_andn_xor)
            a = beagasm.assemble_text(asm, beag_c[:-2] + '.asm', memory)
            words = a.image_words('program')
            total_words += len(words)
            out = []

            class W:
                def write(self, s):
                    out.append(s)

                def flush(self):
                    pass

            m = beagsim.Beag(words, out=W(), warn=W(), memory=memory)
            m.run(50_000_000)
            got = ''.join(m.output)
            problem = None if got == expected and not m.error else (m.stop_reason if m.error else 'output differs')
        except Exception as e:                 # a compiler error is a failure too
            problem = f'{type(e).__name__}: {e}'
            got = ''
        if problem:
            fails += 1
            print(f'seed {seed}: {problem}')
            if args.keep:
                os.makedirs(args.keep, exist_ok=True)
                for p in (beag_c, host_c):
                    with open(p) as fi, open(os.path.join(args.keep, os.path.basename(p)), 'w') as fo:
                        fo.write(fi.read())
                with open(os.path.join(args.keep, f'f{seed}.expected'), 'w') as f:
                    f.write(expected)
                with open(os.path.join(args.keep, f'f{seed}.got'), 'w') as f:
                    f.write(got)
    print(f'{args.count - fails} of {args.count} random programs agree '
          f'(average {total_words // max(args.count, 1)} words)')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
