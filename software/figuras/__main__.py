"""Lista los scripts de figuras con su primera línea de descripción.

    python software/figuras            (o: cd software && python -m figuras)
"""

import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent

for p in sorted(HERE.glob("*.py")):
    if p.name.startswith("_"):
        continue
    doc = ast.get_docstring(ast.parse(p.read_text(encoding="utf-8"))) or ""
    print(f"{p.name:24s} {doc.splitlines()[0] if doc else ''}")
print(f"\nCorrer: python software/figuras/<script>.py --help   (desde la raíz del repositorio)")
