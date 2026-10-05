"""Fase 0: perfila las muestras de data/samples/ y escribe data/samples/PROFILE.md.

Para cada ruta de campo del JSON (listas aplanadas como `[]`) reporta en cuántos
registros aparece y qué fracción viene nula o vacía. Para el CSV masivo, lo mismo
por columna.

Uso: uv run python scripts/phase0_profile.py
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"
EMPTY = (None, "", [], {})


def walk(node: object, path: str, seen: Counter, empty: Counter, examples: dict) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            walk(value, f"{path}.{key}" if path else key, seen, empty, examples)
    elif isinstance(node, list) and node and isinstance(node[0], dict):
        for item in node:
            walk(item, f"{path}[]", seen, empty, examples)
    else:
        seen[path] += 1
        if node in EMPTY or (isinstance(node, str) and node.strip() == ""):
            empty[path] += 1
        else:
            examples.setdefault(path, str(node)[:60])


def profile_json(pattern: str, record_key: str) -> list[str]:
    seen, empty, examples = Counter(), Counter(), {}
    n = 0
    for f in sorted(SAMPLES.glob(pattern)):
        for rec in json.loads(f.read_text()).get(record_key, []):
            n += 1
            walk(rec, "", seen, empty, examples)
    lines = [f"\n## {pattern} ({n} registros)\n", "| campo | presente | % vacío | ejemplo |", "|---|---|---|---|"]
    for path in sorted(seen):
        pct = 100 * empty[path] / seen[path]
        ex = examples.get(path, "").replace("|", "/")
        lines.append(f"| `{path}` | {seen[path]} | {pct:.0f}% | {ex} |")
    return lines


def profile_bulk() -> list[str]:
    lines: list[str] = []
    for zf in sorted((SAMPLES / "bulk").glob("*.zip")):
        with zipfile.ZipFile(zf) as z:
            for name in z.namelist():
                with z.open(name) as raw:
                    text = io.TextIOWrapper(raw, encoding="latin-1", newline="")
                    sample = text.read(20000)
                    delim = ";" if sample.count(";") > sample.count(",") else ","
                    text = io.TextIOWrapper(z.open(name), encoding="latin-1", newline="")
                    reader = csv.DictReader(text, delimiter=delim)
                    n, empty = 0, Counter()
                    codes = set()
                    for row in reader:
                        n += 1
                        codes.add(row.get("CodigoExterno"))
                        for col, val in row.items():
                            if val is None or val.strip() in ("", "NA", "NULL"):
                                empty[col] += 1
                    lines += [
                        f"\n## bulk {zf.name}/{name}: {n} filas, {len(codes)} CodigoExterno distintos, sep '{delim}'\n",
                        "| columna | % vacío |",
                        "|---|---|",
                    ]
                    lines += [f"| `{c}` | {100 * empty[c] / max(n, 1):.0f}% |" for c in reader.fieldnames or []]
    return lines


def main() -> None:
    out = ["# Perfil de muestras (Fase 0)"]
    out += profile_json("listing_*.json", "Listado")
    out += profile_json("detail_*.json", "Listado")
    out += profile_bulk()
    (SAMPLES / "PROFILE.md").write_text("\n".join(out) + "\n")
    print(f"escrito {SAMPLES / 'PROFILE.md'}")


if __name__ == "__main__":
    main()
