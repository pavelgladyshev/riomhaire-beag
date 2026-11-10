#!/usr/bin/env python3
"""Tests of the BEAG toolchain.

    python3 tests/run_tests.py            # all tests, in the simulator
    python3 tests/run_tests.py sort       # tests whose names contain 'sort'
    python3 tests/run_tests.py --logisim JAR [--circuit FILE]
                                          # also run each program in Logisim (slow)

tests/c/NAME.c        a C program; its output must equal NAME.expected
tests/c/NAME.input    keyboard input for it (optional)
tests/errors/NAME.c   a program that must not compile; its first line is '// error: TEXT',
                      and the compiler's message must contain TEXT
tests/asm/NAME.asm    assembler tests, compared with NAME.expected when there is one
tests/link/NAME/      several files (.c and .asm) linked into one program; it must print the
                      contents of tests/link/NAME/expected (the first .c or .asm file is the main one)
tests/memory/NAME/    a program for a computer with its own memory map (beag_memory.txt in the
                      folder); it must print NAME/expected, with NAME/input typed on the keyboard
tests/memory_errors/NAME.txt   memory maps that must be refused; the first line is '# error: TEXT'

For tests that do not depend on the size of int, NAME.expected can be made with the
computer's own C compiler: --host regenerates them (check the result before keeping it).
"""

import argparse
import glob
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import beagasm  # noqa: E402
import beagcc  # noqa: E402
import beagsim  # noqa: E402
import cc_lex  # noqa: E402
from beag_memory import MemoryMap, MemoryMapError  # noqa: E402

DEFAULT_CIRCUIT = os.path.join(ROOT, '..', 'circuits', 'beag_harvard.circ')


def run_sim(words, keys, vn=False):
    out = []

    class W:
        def write(self, s):
            out.append(s)

        def flush(self):
            pass

    m = beagsim.Beag(words, vonneumann=vn, keyboard=keys, out=W(), warn=W())
    m.run(50_000_000)
    return ''.join(m.output), m


def run_logisim(jar, circuit, mem, keys, seconds, expected_len):
    """Output of the program in Logisim's tty mode. A BEAG program never ends by itself, so
    Logisim is stopped when the expected amount of output has come, or after the time limit."""
    import threading
    import time
    vn = 'von_neumann' in os.path.basename(circuit)
    cmd = ['java', '-jar', jar, '-t', 'tty', '--load', mem] + ([] if vn else ['Program_ROM']) + ['--', circuit]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    p.stdin.write(keys.encode())
    p.stdin.close()
    out = []

    def reader():
        while True:
            b = p.stdout.read(1)
            if not b:
                break
            out.append(b)

    th = threading.Thread(target=reader, daemon=True)
    th.start()
    t0 = time.time()
    while time.time() - t0 < seconds and len(out) < expected_len and p.poll() is None:
        time.sleep(0.05)
    time.sleep(0.3)                  # anything printed after the expected output
    p.kill()
    th.join(1)
    return b''.join(out).decode(errors='replace')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pattern', nargs='?', default='')
    ap.add_argument('--host', action='store_true', help='regenerate .expected with the host C compiler')
    ap.add_argument('--logisim', metavar='JAR', help='also run in Logisim (logisim-evolution jar)')
    ap.add_argument('--circuit', default=DEFAULT_CIRCUIT)
    ap.add_argument('--seconds', type=float, default=60, help='time limit for each Logisim run')
    ap.add_argument('-v', action='store_true', help='show the differences')
    ap.add_argument('--vn', action='store_true', help='compile and run the C tests for a von Neumann BEAG '
                                                      '(constant data in ROM)')
    args = ap.parse_args()
    failed = []
    passed = 0
    tmp = tempfile.mkdtemp()

    for src in sorted(glob.glob(os.path.join(HERE, 'c', '*.c'))):
        name = os.path.splitext(os.path.basename(src))[0]
        if args.pattern not in name:
            continue
        base = os.path.splitext(src)[0]
        keys = open(base + '.input').read() if os.path.exists(base + '.input') else ''
        if args.host:
            exe = os.path.join(tmp, name)
            subprocess.run(['cc', '-w', '-include', os.path.join(HERE, 'host_prelude.h'), '-o', exe, src],
                           check=True)
            with open(base + '.expected', 'w') as f:
                f.write(subprocess.run([exe], input=keys.encode(), capture_output=True).stdout.decode())
        try:
            memory = MemoryMap.default().as_vonneumann() if args.vn else None
            asm = beagcc.compile_files([src], memory=memory)
            a = beagasm.assemble_text(asm, base + '.asm', memory)
        except (cc_lex.CompileError, beagasm.AsmError) as e:
            failed.append(name)
            print(f'FAIL {name}: does not compile\n{e}')
            continue
        words = a.image_words('program')
        out, m = run_sim(words, keys, vn=args.vn)
        expected = open(base + '.expected').read() if os.path.exists(base + '.expected') else None
        ok = expected is not None and out == expected and not m.error
        status = 'ok  ' if ok else 'FAIL'
        print(f'{status} {name:16s} {len(words):5d} words  {m.steps:9d} instructions'
              + ('' if expected is not None else '  (no .expected)'))
        if not ok:
            failed.append(name)
            if m.error:
                print('     ' + m.stop_reason)
            if args.v and expected is not None:
                import difflib
                sys.stdout.writelines(difflib.unified_diff(expected.splitlines(True), out.splitlines(True),
                                                           'expected', 'got'))
            continue
        passed += 1
        if args.logisim:
            mem = os.path.join(tmp, name + '.mem')
            with open(mem, 'w') as f:
                f.write(beagasm.format_logisim(words))
            lout = run_logisim(args.logisim, args.circuit, mem, keys, args.seconds, len(expected))
            if lout == expected:
                print(f'     Logisim: the same output')
            else:
                failed.append(name + ' (Logisim)')
                print(f'     Logisim: DIFFERENT output ({len(lout)} of {len(expected)} characters)')

    for src in sorted(glob.glob(os.path.join(HERE, 'errors', '*.c'))):
        name = os.path.splitext(os.path.basename(src))[0]
        if args.pattern not in name:
            continue
        first = open(src).readline()
        want = first.split('error:', 1)[1].strip() if 'error:' in first else ''
        try:
            beagcc.compile_files([src])
            msg = None
        except cc_lex.CompileError as e:
            msg = str(e)
        ok = msg is not None and want in msg
        print(f'{"ok  " if ok else "FAIL"} error/{name}' + ('' if ok else f'\n     {msg}'))
        if ok:
            passed += 1
        else:
            failed.append('error/' + name)

    for src in sorted(glob.glob(os.path.join(HERE, 'asm', '*.asm'))):
        name = os.path.splitext(os.path.basename(src))[0]
        if args.pattern not in name:
            continue
        base = os.path.splitext(src)[0]
        try:
            a = beagasm.assemble_file(src)
        except beagasm.AsmError as e:
            failed.append('asm/' + name)
            print(f'FAIL asm/{name}: {e}')
            continue
        if os.path.exists(base + '.expected'):
            out, m = run_sim(a.image_words('program'), '')
            ok = out == open(base + '.expected').read()
        else:
            ok = True
        print(f'{"ok  " if ok else "FAIL"} asm/{name}')
        if ok:
            passed += 1
        else:
            failed.append('asm/' + name)

    for d in sorted(glob.glob(os.path.join(HERE, 'link', '*'))):
        name = os.path.basename(d)
        if args.pattern not in name or not os.path.isdir(d):
            continue
        srcs = sorted(glob.glob(os.path.join(d, '*.c'))) + sorted(glob.glob(os.path.join(d, '*.asm')))
        try:
            a, _, _ = beagcc.build(srcs, os.path.join(tmp, name + '.mem'))
        except (cc_lex.CompileError, beagasm.AsmError) as e:
            failed.append('link/' + name)
            print(f'FAIL link/{name}: {e}')
            continue
        out, m = run_sim(a.image_words('program'), '')
        ok = out == open(os.path.join(d, 'expected')).read() and not m.error
        print(f'{"ok  " if ok else "FAIL"} link/{name}' + ('' if ok else f'  got {out!r}'))
        if ok:
            passed += 1
        else:
            failed.append('link/' + name)

    for d in sorted(glob.glob(os.path.join(HERE, 'memory', '*'))):
        name = os.path.basename(d)
        if args.pattern not in name or not os.path.isdir(d):
            continue
        srcs = sorted(glob.glob(os.path.join(d, '*.c'))) + sorted(glob.glob(os.path.join(d, '*.asm')))
        keys = open(os.path.join(d, 'input')).read() if os.path.exists(os.path.join(d, 'input')) else ''
        try:
            memory = MemoryMap.find(near=srcs[0])
            a, _, _ = beagcc.build(srcs, os.path.join(tmp, name + '.mem'), memory=memory)
        except (cc_lex.CompileError, beagasm.AsmError, MemoryMapError) as e:
            failed.append('memory/' + name)
            print(f'FAIL memory/{name}: {e}')
            continue
        out = []

        class W:
            def write(self, s):
                out.append(s)

            def flush(self):
                pass

        m = beagsim.Beag(a.image_words('program'), memory=memory, images=beagsim.bank_images(a),
                         keyboard=keys, out=W(), warn=W())
        m.run(50_000_000)
        got = ''.join(m.output)
        exp_path = os.path.join(d, 'expected')
        ok = os.path.exists(exp_path) and got == open(exp_path).read() and not m.error
        print(f'{"ok  " if ok else "FAIL"} memory/{name}' + ('' if ok else f'  got {got!r}' +
                                                         (f' ({m.stop_reason})' if m.error else '')))
        if ok:
            passed += 1
        else:
            failed.append('memory/' + name)

    for path in sorted(glob.glob(os.path.join(HERE, 'memory_errors', '*.txt'))):
        name = os.path.splitext(os.path.basename(path))[0]
        if args.pattern not in name:
            continue
        want = open(path).readline().split('error:', 1)[1].strip()
        try:
            MemoryMap.load(path)
            msg = None
        except MemoryMapError as e:
            msg = str(e)
        ok = msg is not None and want in msg
        print(f'{"ok  " if ok else "FAIL"} memory_error/{name}' + ('' if ok else f'\n     {msg}'))
        if ok:
            passed += 1
        else:
            failed.append('memory_error/' + name)

    print(f'\n{passed} passed, {len(failed)} failed' + (': ' + ', '.join(failed) if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
