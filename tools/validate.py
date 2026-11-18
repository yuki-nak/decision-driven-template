"""決定記録、タスク、成果物WBS、文書IDが、互いに矛盾なくつながっているかを確かめる。

使い方:
  python3 tools/validate.py                          # project/ を確かめる
  python3 tools/validate.py --root examples/sample-project
  python3 tools/validate.py --strict                 # 警告もエラーとして扱う

エラーがあれば終了コード1。警告は表示するだけ（--strict のときは1）。

確かめること:
  決定記録   必須項目、IDの形式とファイル名、重複、status・category の値、
             decided のとき decided_at・decided_by・recorded_by があること、
             記録した人が決定した人と違うときは evidence（承認の根拠）があること、
             AIの推奨があるとき followed_recommendation があること、
             supersedes の参照先が存在し、superseded になっていること、
             wbs が wbs.csv に、affects が documents.csv にあること
  タスク     IDの形式と重複、status の値、dr が決定記録にあること、
             done のとき result と result_ref、dropped のとき result（理由）があること、
             （警告）覆された決定（superseded）に、終わっていないタスクが残っていること
  WBS        番号の重複、status の値、doc_id が documents.csv にあること
  文書ID     IDの重複、state の値、active のファイルが存在すること
  ゲート     IDの重複、status の値、status が「未」でなければ、gates/<ID>.md があり、
             「判断の決定記録：DR-NNNN」の行が、確定した決定記録を指すこと
"""
import argparse
import pathlib
import re
import sys

from common import (CATEGORY, DECISION_STATUS, DEFAULT_ROOT, DOCUMENT_COLUMNS, DOCUMENT_STATE, GATE_STATUS, InputError,
                    TASK_COLUMNS, TASK_STATUS, WBS_COLUMNS, WBS_STATUS, list_value, load_decision_files,
                    read_csv, read_json)

REQUIRED = ("id", "title", "wbs", "category", "status", "owner")


def validate(root):
    errors, warnings = [], []
    try:
        wbs_rows = read_csv(root / "wbs.csv", WBS_COLUMNS)
        doc_rows = read_csv(root / "documents.csv", DOCUMENT_COLUMNS)
        task_rows = read_csv(root / "tasks.csv", TASK_COLUMNS)
        plan = read_json(root / "plan.json")
    except InputError as e:
        return [str(e)], []

    # 文書ID
    docs = {}
    for r in doc_rows:
        if r["id"] in docs:
            errors.append(f"documents.csv: id {r['id']} が重複している")
        docs[r["id"]] = r
        if r["state"] not in DOCUMENT_STATE:
            errors.append(f"documents.csv: {r['id']} の state が違う（{r['state']!r}）")
        if r["state"] == "active" and r["file"] and not (root / r["file"]).exists():
            errors.append(f"documents.csv: {r['id']} のファイル {r['file']} がない")

    # WBS
    wbs = {}
    for r in wbs_rows:
        if r["wbs"] in wbs:
            errors.append(f"wbs.csv: {r['wbs']} が重複している")
        wbs[r["wbs"]] = r
        if r["status"] not in WBS_STATUS:
            errors.append(f"wbs.csv: {r['wbs']} の status が違う（{r['status']!r}）")
        if r["doc_id"] and r["doc_id"] not in docs:
            errors.append(f"wbs.csv: {r['wbs']} の doc_id {r['doc_id']} が documents.csv にない")

    # 決定記録
    decisions = {}
    for name, fm in load_decision_files(root):
        if fm is None:
            errors.append(f"{name}: frontmatter がない、または閉じていない")
            continue
        e = lambda msg: errors.append(f"{name}: {msg}")
        for key in REQUIRED:
            if not fm.get(key):
                e(f"必須項目 {key} がない")
        rid = fm.get("id", "")
        if not re.fullmatch(r"DR-\d{4}", rid):
            e(f"id の形式が違う（{rid!r}。DR-0001 の形）")
        elif name != f"dr-{rid[3:]}.md":
            e(f"id（{rid}）とファイル名が合わない")
        if rid in decisions:
            e(f"id {rid} が重複している")
        decisions[rid] = fm
        status = fm.get("status")
        if status not in DECISION_STATUS:
            e(f"status が違う（{status!r}）")
        if fm.get("category") not in CATEGORY:
            e(f"category が違う（{fm.get('category')!r}）")
        if status in ("decided", "superseded"):
            for key in ("decided_at", "decided_by", "recorded_by"):
                if not fm.get(key):
                    e(f"{status} なのに {key} がない")
            if fm.get("decided_by") and fm.get("recorded_by") and fm["decided_by"] != fm["recorded_by"] \
                    and not fm.get("evidence"):
                e("記録した人が決定した人と違うのに、evidence（承認の根拠）がない")
            if fm.get("ai_recommended", "none") not in ("", "none") \
                    and fm.get("followed_recommendation") not in ("true", "false"):
                e("AIの推奨があるのに followed_recommendation（true / false）がない")
        if fm.get("wbs") and fm["wbs"] not in wbs:
            e(f"wbs {fm['wbs']} が wbs.csv にない")
        for ref in list_value(fm.get("affects", "")):
            if ref not in docs:
                e(f"affects の {ref} が documents.csv にない")

    for rid, fm in decisions.items():
        sup = fm.get("supersedes", "")
        if not sup:
            continue
        if sup not in decisions:
            errors.append(f"{rid}: supersedes の参照先 {sup} がない")
        elif fm.get("status") == "decided" and decisions[sup].get("status") != "superseded":
            errors.append(f"{rid}: {sup} を覆したのに、{sup} の status が superseded になっていない")
    superseded_by = {fm.get("supersedes") for fm in decisions.values() if fm.get("status") == "decided"}
    for rid, fm in decisions.items():
        if fm.get("status") == "superseded" and rid not in superseded_by:
            errors.append(f"{rid}: superseded なのに、覆した決定記録（supersedes: {rid}）がない")

    # タスク
    seen = set()
    for r in task_rows:
        tid = r["id"]
        if not re.fullmatch(r"T-\d{4}", tid):
            errors.append(f"tasks.csv: id の形式が違う（{tid!r}。T-0001 の形）")
        if tid in seen:
            errors.append(f"tasks.csv: id {tid} が重複している")
        seen.add(tid)
        if r["status"] not in TASK_STATUS:
            errors.append(f"tasks.csv: {tid} の status が違う（{r['status']!r}）")
        if not r["dr"]:
            errors.append(f"tasks.csv: {tid} に dr（元になった決定記録）がない")
        elif r["dr"] not in decisions:
            errors.append(f"tasks.csv: {tid} の dr {r['dr']} が決定記録にない")
        elif decisions[r["dr"]].get("status") == "superseded" and r["status"] in ("todo", "doing"):
            warnings.append(f"tasks.csv: {tid} の元の決定 {r['dr']} は覆された（superseded）。"
                            "タスクを dropped にするか、新しい決定に付け替える")
        if r["status"] == "done" and not (r["result"] and r["result_ref"]):
            errors.append(f"tasks.csv: {tid} は done なのに、result（結果）か result_ref（結果の場所）がない")
        if r["status"] == "dropped" and not r["result"]:
            errors.append(f"tasks.csv: {tid} は dropped なのに、result（やめた理由）がない")

    # ゲート
    gate_ids = set()
    for g in plan.get("gates", []):
        gid, status = g.get("id", ""), g.get("status", "未")
        if gid in gate_ids:
            errors.append(f"plan.json: ゲート {gid} が重複している")
        gate_ids.add(gid)
        if status not in GATE_STATUS:
            errors.append(f"plan.json: ゲート {gid} の status が違う（{status!r}。{' / '.join(GATE_STATUS)}）")
        if status == "未":
            continue
        summary = root / "gates" / f"{gid}.md"
        if not summary.exists():
            errors.append(f"plan.json: ゲート {gid} は「{status}」なのに、まとめ gates/{gid}.md がない"
                          f"（python3 tools/gate.py --gate {gid} で下書きを作る）")
            continue
        m = re.search(r"^- 判断の決定記録：(DR-\d{4})\s*$", summary.read_text(encoding="utf-8"), re.M)
        if not m:
            errors.append(f"gates/{gid}.md: 「- 判断の決定記録：DR-NNNN」の行がない")
        elif decisions.get(m.group(1), {}).get("status") != "decided":
            errors.append(f"gates/{gid}.md: 判断の決定記録 {m.group(1)} が、確定した決定記録にない")
    for fm in decisions.values():
        v = fm.get("verify_at", "")
        if v and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) and v not in gate_ids:
            errors.append(f"{fm.get('id')}: verify_at の {v} が、日付でも plan.json のゲートでもない")

    return errors, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    errors, warnings = validate(args.root.resolve())
    for w in warnings:
        print("警告: " + w, file=sys.stderr)
    for e in errors:
        print("エラー: " + e, file=sys.stderr)
    if errors or (args.strict and warnings):
        print("検証に失敗した。", file=sys.stderr)
        return 1
    print(f"OK: {args.root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
