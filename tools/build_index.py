"""決定記録（decisions/dr-*.md）の frontmatter から、decisions/index.csv を作り直す。

使い方:
  python3 tools/build_index.py                       # project/ の index.csv を作り直す
  python3 tools/build_index.py --root examples/sample-project
  python3 tools/build_index.py --check               # 書かずに、コミット済みの index.csv と一致するかだけ確かめる

frontmatter の中身の検証は tools/validate.py が行う。ここでは、読めないファイルだけを止める。
"""
import argparse
import pathlib
import sys

from common import DECISION_COLUMNS, DEFAULT_ROOT, csv_text, decision_row, load_decision_files


def build(root):
    rows, errors = [], []
    for name, fm in load_decision_files(root):
        if fm is None:
            errors.append(f"{name}: frontmatter がない、または閉じていない")
            continue
        rows.append(decision_row(fm, name))
    return csv_text(DECISION_COLUMNS + ["file"], rows), len(rows), errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    text, n, errors = build(root)
    if errors:
        print("index.csv を作れない。", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        return 1
    out = root / "decisions" / "index.csv"
    if args.check:
        current = out.read_text(encoding="utf-8-sig").replace("\r\n", "\n") if out.exists() else None
        if current != text.lstrip("﻿").replace("\r\n", "\n"):
            print(f"{out}: 決定記録と一致しない。python3 tools/build_index.py --root {args.root} で作り直す",
                  file=sys.stderr)
            return 1
        print(f"OK: {out}（{n}件）は決定記録と一致する")
        return 0
    out.write_text(text, encoding="utf-8", newline="")
    print(f"{n}件 -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
