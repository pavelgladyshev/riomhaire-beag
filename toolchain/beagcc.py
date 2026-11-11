#!/usr/bin/env python3
"""beagcc - C compiler for the BEAG teaching computer (COMP20020, UCD).

Usage:
    python3 beagcc.py hello.c                 # hello.mem (ROM image), hello.asm, hello.lst, hello.map
    python3 beagcc.py hello.c -S              # only hello.asm
    python3 beagcc.py hello.c --run           # compile and run in the simulator (beagsim)
    python3 beagcc.py calc.c --run -i '12+30\\n'
    python3 beagcc.py main.c util.c -o prog.mem
    python3 beagcc.py main.c fast.asm         # C and assembly files linked into one program
    python3 beagcc.py prog.c --memory my.txt  # for a computer with its own memory map

The memory map (ROM, RAM and devices) is read from beag_memory.txt next to the first source, or
from --memory FILE; without one it is that of the course's BEAG (see beag_memory.py).

Files made next to the ROM image:
    .asm   the compiled C (C source lines are comments in it)
    .lst   the listing of the whole program: every file, absolute addresses, machine code
    .map   the memory map: where each file, function and variable is in the ROM and the RAM

Load the .mem file into the Program_ROM of beag_harvard.circ (right click, Load Image...)
or run it from the command line:
    java -jar logisim-evolution-5.0.0-all.jar -t tty --load hello.mem Program_ROM -- beag_harvard.circ

The C language here: char, short, int and pointers are all 16 bits (one BEAG word, so
sizeof(char) == 1 and a char holds 16 bits); unsigned versions of them; arrays, structs, unions,
enums, typedefs, function pointers, recursion, switch, goto. Not supported: long, float, double,
bit-fields, passing or returning structs by value (use pointers). The library has putchar,
getchar, puts, printf, sprintf, string.h, ctype.h, abs/atoi/rand/malloc/free, and beag.h for the
display and keyboard.

Assembly files: their labels are their own unless declared '.globl name'; a label of another
file (or a C function or variable, whose label is its name with _ in front) is used after
'.extern name'. A function called from C gets its first argument in r1 and the others on the
stack ([sp] = the second), returns its result in r1 to the address in r7 (jalr r0,r7,r0), and
must keep r3, r4, r5 and r6 (sp) as they were.
"""

import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cc_lex  # noqa: E402
from cc_lex import CompileError, Preprocessor, Token  # noqa: E402
from cc_parse import Parser, Program  # noqa: E402
from cc_gen import Generator  # noqa: E402
import beagasm  # noqa: E402
from beag_memory import MemoryMap, MemoryMapError  # noqa: E402

INCLUDE_DIR = os.path.join(HERE, 'include')
LIB_DIR = os.path.join(HERE, 'lib')
ASM_EXTENSIONS = ('.asm', '.s')


def compile_program(paths, include_dirs=(), defines=(), stdlib=True, external=None, imports=(),
                    separate_tail=False, memory=None, logic_ops=True):
    """Compile C files (with the library) into BEAG assembly text; returns (text, Generator)."""
    cc_lex.WARNINGS.clear()
    memory = memory or MemoryMap.default()
    defines = memory.defines() + list(defines)
    prog = Program()
    units = [(p, False) for p in paths]
    if stdlib:
        units += [(p, True) for p in sorted(glob.glob(os.path.join(LIB_DIR, '*.c')))]
    for k, (path, is_lib) in enumerate(units, 1):
        pp = Preprocessor(list(include_dirs) + [INCLUDE_DIR], defines)
        toks = pp.process_file(path)
        last = toks[-1] if toks else None
        toks.append(Token('eof', None, '', path, last.line + 1 if last else 1, 1, True))
        p = Parser(toks, prog, k)
        p.weak = is_lib
        p.parse()
    header = '; BEAG assembly compiled by beagcc from ' + ', '.join(os.path.basename(p) for p in paths)
    g = Generator(prog, memory, logic_ops)
    text = g.generate(header, external=external, imports=imports, separate_tail=separate_tail)
    return text, g


def compile_files(paths, include_dirs=(), defines=(), stdlib=True, memory=None, logic_ops=True):
    """Compile C files (together with the library) into BEAG assembly text."""
    return compile_program(paths, include_dirs, defines, stdlib, memory=memory, logic_ops=logic_ops)[0]


def build(sources, out, include_dirs=(), defines=(), stdlib=True, only_asm=False, memory=None,
          logic_ops=True):
    """Compile the C files, link them with the assembly files; returns the Assembler (or None
    with only_asm) and the texts for the map."""
    memory = memory or MemoryMap.default()
    c_srcs = [s for s in sources if s.lower().endswith('.c')]
    asm_srcs = [s for s in sources if s.lower().endswith(ASM_EXTENSIONS)]
    other = [s for s in sources if s not in c_srcs and s not in asm_srcs]
    if other:
        raise CompileError(f'{other[0]}: give C files (.c) and assembly files (.asm or .s)')
    stem = os.path.splitext(out)[0]
    exports, imports = beagasm.link_names(asm_srcs, memory) if asm_srcs else ({}, set())
    modules = []
    origins, describe = {}, {}
    if c_srcs:
        text, g = compile_program(c_srcs, include_dirs, defines, stdlib, external=exports, imports=imports,
                                  separate_tail=bool(asm_srcs), memory=memory, logic_ops=logic_ops)
        with open(stem + '.asm', 'w') as f:
            f.write(text)
        if only_asm:
            return None, origins, describe
        modules.append((text, stem + '.asm'))
        origins = g.origins
        describe[stem + '.asm'] = (f'{os.path.basename(stem)}.asm: compiled from '
                                   f'{", ".join(os.path.basename(s) for s in c_srcs)}'
                                   + (' and the C library' if stdlib else ''))
    elif only_asm:
        return None, origins, describe
    for s in asm_srcs:
        try:
            with open(s, encoding='utf-8') as f:
                modules.append((f.read(), s))
        except OSError as e:
            raise CompileError(f'cannot read {s}: {e.strerror}')
    if c_srcs and asm_srcs:
        modules.append((g.tail_text(), '(end of the variables, made by beagcc)'))
    return beagasm.assemble_modules(modules, memory), origins, describe


def main(argv=None):
    ap = argparse.ArgumentParser(description='C compiler for the BEAG computer (COMP20020).')
    ap.add_argument('sources', nargs='+', help='C files (.c) and assembly files (.asm, .s)')
    ap.add_argument('-o', '--output', help='the ROM image to write (default: first source with .mem)')
    ap.add_argument('-S', action='store_true', help='only compile the C files to assembly (.asm)')
    ap.add_argument('-I', action='append', default=[], dest='include', help='add an include directory')
    ap.add_argument('-D', action='append', default=[], dest='define', help='define a macro (NAME or NAME=VALUE)')
    ap.add_argument('--nostdlib', action='store_true', help='do not link the C library')
    ap.add_argument('--run', action='store_true', help='run the program in the simulator afterwards')
    ap.add_argument('-i', '--input', default='', help=r'keyboard input for --run, e.g. "42\n"')
    ap.add_argument('--vonneumann', '--vn', action='store_true',
                    help='compile for (and with --run, simulate) a von Neumann BEAG: strings, const data and the '
                         'initial values of the variables are kept in the ROM, which lw can read there')
    ap.add_argument('--memory', help='the memory map of the computer (default: beag_memory.txt next to the '
                                     'first source, else the course\'s BEAG)')
    ap.add_argument('--no-andn-xor', action='store_true',
                    help='do not use the andn and xor instructions, which the circuits shown in the videos '
                         '(circuits/as-in-videos) do not have: &, |, ^ and ~ are then done by slower routines')
    ap.add_argument('-l', '--listing', action='store_true', help='(the listing is always written)')
    argv = list(sys.argv[1:] if argv is None else argv)
    for i in range(len(argv) - 1):              # allow -i -15
        if argv[i] in ('-i', '--input'):
            argv[i:i + 2] = ['--input=' + argv[i + 1], '']
    args = ap.parse_args([a for a in argv if a != ''])

    out = args.output or os.path.splitext(args.sources[0])[0] + '.mem'
    stem = os.path.splitext(out)[0]
    try:
        memory = MemoryMap.find(args.memory, near=args.sources[0])
        if args.vonneumann:
            memory = memory.as_vonneumann()
    except MemoryMapError as e:
        print(e, file=sys.stderr)
        return 1
    if memory.file:
        print(f'beagcc: the memory map is {memory.file}', file=sys.stderr)
    try:
        a, origins, describe = build(args.sources, out, args.include, args.define, not args.nostdlib, args.S,
                                     memory, logic_ops=not args.no_andn_xor)
    except CompileError as e:
        for w in cc_lex.WARNINGS:
            print(w, file=sys.stderr)
        print(e, file=sys.stderr)
        return 1
    except beagasm.AsmError as e:
        for w in cc_lex.WARNINGS:
            print(w, file=sys.stderr)
        print(e, file=sys.stderr)
        if e.where is not None and e.where.file.endswith('.asm') and \
                os.path.abspath(e.where.file) == os.path.abspath(stem + '.asm'):
            print('beagcc: the compiled assembly did not assemble (a compiler bug, or an error in asm())',
                  file=sys.stderr)
        return 1
    for w in cc_lex.WARNINGS:
        print(w, file=sys.stderr)
    if a is None:
        return 0
    words = a.image_words('program')
    with open(out, 'w') as f:
        f.write(beagasm.format_logisim(words))
    with open(stem + '.lst', 'w') as f:
        beagasm.write_listing(a, f, out)
    with open(stem + '.map', 'w') as f:
        beagasm.write_map(a, f, out, origins, describe)
    data_end = a.symbols.get('rt_data_end', memory.data.start)
    print(f'beagcc: {out}: {len(words)} words of program (the ROM holds {memory.program.size}), '
          f'{data_end - memory.data.start} words of global data; listing {stem}.lst, map {stem}.map',
          file=sys.stderr)
    for bank in a.banks:
        if bank != 'program' and a.image_words(bank) and bank != 'data':
            img = stem + '.' + bank + '.mem'
            with open(img, 'w') as f:
                f.write(beagasm.format_logisim(a.image_words(bank)))
            print(f'beagcc: {img}: the contents of bank {bank}; load it into that memory', file=sys.stderr)
    if args.run:
        import beagsim
        m = beagsim.Beag(words, vonneumann=True if args.vonneumann else None, memory=memory,
                         keyboard=beagsim.unescape_arg(args.input), images=beagsim.bank_images(a))
        finished = m.run(20_000_000)
        if m.output and m.output[-1] != '\n':
            print()
        if not m.stop_reason.startswith('halted') or not finished:
            print(f'beagsim: {m.stop_reason}', file=sys.stderr)
        print(f'beagsim: {m.steps} instructions', file=sys.stderr)
        return 3 if m.error else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
