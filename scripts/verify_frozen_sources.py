"""Check that the shipped EXE contains the current audio pipeline, not stale cache.

Run with the packaging venv: python scripts/verify_frozen_sources.py [path/to/exe]
"""
import sys
import types
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader


def signature(code):
    return (
        code.co_code,
        tuple(signature(c) if isinstance(c, types.CodeType) else c for c in code.co_consts),
        code.co_names,
        code.co_varnames,
        code.co_freevars,
        code.co_cellvars,
        code.co_flags,
        code.co_exceptiontable,
    )


def main():
    root = Path(__file__).resolve().parents[1]
    exe = Path(sys.argv[1]) if len(sys.argv) > 1 else root / 'dist/Yo-Voice/Yo-Voice.exe'
    archive = CArchiveReader(str(exe)).open_embedded_archive('PYZ.pyz')
    for name in ('vad', 'asr', 'speaker', 'audio', 'capture', 'app', 'settings_win'):
        bundled = archive.extract('yo.' + name)
        source = (root / 'yo' / (name + '.py')).read_text(encoding='utf-8')
        current = compile(source, bundled.co_filename, 'exec', dont_inherit=True)
        if signature(bundled) != signature(current):
            raise RuntimeError('Stale bundled module: yo.' + name)
        print('Verified bundled source: yo.' + name)


if __name__ == '__main__':
    main()
