"""Start OpenRD with automatic project/game input selection."""
from pathlib import Path
import runpy
import sys

root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'tools'))
keep_errors='--keep-errors' in sys.argv
if keep_errors:sys.argv.remove('--keep-errors')
try:runpy.run_path(str(root/'tools/play.py'),run_name='__main__')
except SystemExit as exc:
    if keep_errors and exc.code and sys.stdin.isatty():
        try:input('\n按 Enter 关闭 / Press Enter to close: ')
        except (EOFError,KeyboardInterrupt):pass
    raise
