"""道具に共通の読み書き。標準ライブラリだけを使う。

プロジェクトのディレクトリ（既定は project/）は、次のファイルを持つ。

  decisions/dr-NNNN.md   決定記録（1件1ファイル。正本）
  decisions/index.csv    決定記録の一覧（生成物。tools/build_index.py）
  tasks.csv              決定から派生したタスクと、その実行結果（正本）。期限は問い（決定記録の due）に置く
  wbs.csv                成果物WBS（正本）。決定記録の affects は、この番号で書く
  plan.json              期限、ゲート、壁（QCD）（正本）
  gates/<ゲートID>.md     ゲートのまとめ（下書きは tools/gate.py）
  judgments.json         レポートの判断の欄（LLMが提案し、人間が確認する）
  report/report.json     レポートのデータ（生成物。tools/report.py）
  report/report.html     レポートの表示（生成物。tools/report.py）
"""
import csv
import hashlib
import io
import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_ROOT = REPO / "project"

DECISION_COLUMNS = [
    "id", "title", "wbs", "category", "status", "owner", "due", "decided_at",
    "decided_by", "recorded_by", "evidence", "supersedes", "affects",
    "ai_recommended", "followed_recommendation", "dialogue_before", "verify_at",
]
TASK_COLUMNS = ["id", "title", "dr", "status", "result", "result_ref", "ref"]
WBS_COLUMNS = ["wbs", "title", "status", "questions", "file"]

DECISION_STATUS = ("open", "decided", "superseded")
CATEGORY = ("management", "design", "evaluation")
TASK_STATUS = ("todo", "doing", "done", "dropped")
WBS_STATUS = ("confirmed", "partial", "todo", "deferred")
GATE_STATUS = ("未", "通過", "範囲を絞って通過", "通過しない")

# 値の末尾の「  # 注記」を取り除く項目（テンプレートの注記）。題などの文章はそのまま残す
_COMMENT_OK = set(DECISION_COLUMNS) - {"title"}


class InputError(Exception):
    """入力が読めない、または形が違う。"""


def frontmatter(path):
    """決定記録の先頭の --- で囲まれた部分を、辞書で返す。なければ None。"""
    lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return None
    data = {}
    for line in lines[1:]:
        if line == "---":
            return data
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in _COMMENT_OK:
            # 「値  # 注記」の注記と、値が空で「  # 注記」だけのものを取り除く
            value = "" if re.match(r"\s*#", value) else re.split(r"\s{2,}#", value)[0]
        data[key] = value.strip().strip('"')
    return None  # 閉じの --- がない


def list_value(value):
    """[A, B] や "A B" を ["A", "B"] にする。"""
    return [v for v in re.split(r"[\s,]+", value.strip().strip("[]")) if v]


def load_decision_files(root):
    """(ファイル名, frontmatter) の一覧を、ファイル名の順に返す。"""
    return [(p.name, frontmatter(p)) for p in sorted((root / "decisions").glob("dr-*.md"))]


def decision_row(fm, filename):
    row = {c: fm.get(c, "") for c in DECISION_COLUMNS}
    row["affects"] = " ".join(list_value(row["affects"]))
    row["file"] = filename
    return row


def csv_text(columns, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return "﻿" + buf.getvalue()  # BOM付き。Excelでそのまま開ける


def read_csv(path, columns):
    path = pathlib.Path(path)
    if not path.exists():
        raise InputError(f"{path}: ファイルがない")
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise InputError(f"{path}: 列が足りない（{', '.join(missing)}）")
        rows = []
        for n, r in enumerate(reader, start=2):
            if None in r:
                raise InputError(f"{path}: {n}行目の列が多い（見出しは {len(reader.fieldnames)} 列）")
            rows.append({k: (v or "").strip() for k, v in r.items()})
        return rows


def read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InputError(f"{path}: 読めない（{e}）")


def file_id(path):
    """入力の識別子（sha256の先頭12桁）。改行コードの違いは無視する。"""
    data = pathlib.Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()[:12]


def wbs_key(w):
    return [int(p) if p.isdigit() else p for p in w.split(".")]
