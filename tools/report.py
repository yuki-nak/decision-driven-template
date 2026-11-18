"""状況レポートを作る。入力 → 導出 → 判断の欄を合わせる → 検査 → report.json と report.html。

4つの層に分け、LLMには判断の欄（judgments.json）だけを任せる。
  1 入力（正本）  decisions/index.csv、tasks.csv、wbs.csv、plan.json   人間とAIが更新する
  2 導出          このスクリプト（LLMを使わない。同じ入力なら同じ出力）
  3 判断の欄      judgments.json                                       LLMが提案し、人間が確認する
  4 表示          このスクリプトの固定のテンプレート                    LLMには書かせない

使い方:
  python3 tools/report.py                            # project/report/ に書く
  python3 tools/report.py --root examples/sample-project
  python3 tools/report.py --check                    # 書かずに、コミット済みのレポートと一致するかを確かめる
  python3 tools/report.py --derive                   # 導出値だけを表示する（判断の欄を書くLLMに渡す）
  python3 tools/report.py --print-inputs             # 判断の欄の based_on に書く入力の識別子

検査（通らなければ書かない。終了コード1）:
  判断の欄の形（評価の値、文字数）、文章中の数字が導出値か計画の値にあること、
  文章中の DR-NNNN・T-NNNN が存在すること。
  （警告）判断の欄の based_on が現在の入力と違う：入力が更新されたので、再評価が要る。
"""
import argparse
import html
import json
import pathlib
import re
import sys

from common import (DECISION_COLUMNS, DEFAULT_ROOT, InputError, TASK_COLUMNS, TASK_STATUS, WBS_COLUMNS,
                    file_id, read_csv, read_json, wbs_key)

SCHEMA_VERSION = "1.0.0"
INPUTS = {
    "decisions_index": "decisions/index.csv",
    "tasks": "tasks.csv",
    "wbs": "wbs.csv",
    "plan": "plan.json",
}
RATINGS = ("ok", "caution", "bad")
JUDGMENT_FIELDS = {"summary": 400, "quality": 200, "delivery": 200, "cost": 200}
RISK_MAX = 120


# ---------- 2 導出 ----------

def pct(n, d):
    return None if d == 0 else int(n * 100 / d + 0.5)


def input_ids(root):
    return {k: file_id(root / v) for k, v in INPUTS.items()}


def derive(root):
    plan = read_json(root / "plan.json")
    as_of = plan.get("as_of", "")
    decisions = read_csv(root / INPUTS["decisions_index"], DECISION_COLUMNS)
    tasks = read_csv(root / INPUTS["tasks"], TASK_COLUMNS)
    wbs_rows = sorted(read_csv(root / INPUTS["wbs"], WBS_COLUMNS), key=lambda r: wbs_key(r["wbs"]))
    by_id = {d["id"]: d for d in decisions}

    count = {s: sum(1 for d in decisions if d["status"] == s) for s in ("decided", "open", "superseded")}
    open_list = [{"id": d["id"], "title": d["title"], "wbs": d["wbs"], "due": d["due"],
                  "overdue": bool(d["due"] and as_of and d["due"] < as_of)}
                 for d in decisions if d["status"] == "open"]
    rec = [d for d in decisions if d["status"] in ("decided", "superseded")
           and d["ai_recommended"] not in ("", "none")]
    followed = sum(1 for d in rec if d["followed_recommendation"] == "true")
    recent = sorted((d for d in decisions if d["status"] == "decided"),
                    key=lambda d: (d["decided_at"], d["id"]), reverse=True)[:10]

    deliverables = []
    for w in wbs_rows:
        qs = [d for d in decisions if d["wbs"] == w["wbs"] and d["status"] != "superseded"]
        decided = sum(1 for d in qs if d["status"] == "decided")
        deliverables.append({"wbs": w["wbs"], "title": w["title"], "status": w["status"],
                             "decided": decided, "total": len(qs), "pct": pct(decided, len(qs))})
    with_q = [x for x in deliverables if x["total"]]

    task_count = {s: sum(1 for t in tasks if t["status"] == s) for s in TASK_STATUS}
    active = [{"id": t["id"], "title": t["title"], "dr": t["dr"], "status": t["status"],
               "owner": t["owner"], "due": t["due"],
               "overdue": bool(t["due"] and as_of and t["due"] < as_of)}
              for t in tasks if t["status"] in ("todo", "doing")]
    stale = [t["id"] for t in tasks if t["status"] in ("todo", "doing")
             and by_id.get(t["dr"], {}).get("status") == "superseded"]
    recent_done = [{"id": t["id"], "title": t["title"], "dr": t["dr"], "result": t["result"],
             "result_ref": t["result_ref"]} for t in tasks if t["status"] == "done"]

    return {
        "as_of": as_of,
        "project": plan.get("project", ""),
        "decisions": {
            "total": len(decisions), **count,
            "decided_pct": pct(count["decided"], count["decided"] + count["open"]),
            "open_list": open_list,
            "overdue": sum(1 for o in open_list if o["overdue"]),
            "recent": [{"id": d["id"], "title": d["title"], "decided_at": d["decided_at"],
                        "decided_by": d["decided_by"]} for d in recent],
        },
        "ai": {"recommended_decided": len(rec), "followed": followed, "not_followed": len(rec) - followed,
               "followed_pct": pct(followed, len(rec))},
        "deliverables": {"items": deliverables, "with_questions": len(with_q),
                         "complete": sum(1 for x in with_q if x["decided"] == x["total"])},
        "tasks": {"total": len(tasks), **task_count, "active": active, "stale": stale,
                  "overdue": sum(1 for t in active if t["overdue"]), "recent_done": recent_done[-10:]},
        "plan": {"completion": plan.get("completion", {}),
                 "gates": [{**g, "summary": f"gates/{g.get('id')}.md" if (root / "gates" / f"{g.get('id')}.md").exists() else ""}
                           for g in plan.get("gates", [])],
                 "walls": plan.get("walls", {}), "capacity": plan.get("capacity", {})},
    }


# ---------- 3 判断の欄の検査 ----------

def judgment_texts(j):
    for key in JUDGMENT_FIELDS:
        if isinstance(j.get(key), dict):
            yield key, j[key].get("text", "")
    for i, item in enumerate((j.get("risks") or {}).get("items", [])):
        yield f"risks.items[{i}]", item


def numbers_in(obj, acc):
    if isinstance(obj, bool) or obj is None:
        return acc
    if isinstance(obj, (int, float)):
        acc.add(str(int(obj)) if float(obj).is_integer() else str(obj))
    elif isinstance(obj, str):
        for m in re.findall(r"\d+(?:\.\d+)?", ID_RE.sub("", obj)):
            acc.add(str(int(float(m))) if float(m).is_integer() else m)
    elif isinstance(obj, dict):
        for v in obj.values():
            numbers_in(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            numbers_in(v, acc)
    return acc


ID_RE = re.compile(r"\b(?:DR|T)-\d{4}\b")


def phrase_rules(derived):
    """決まった言い回しと、そこに入るべき導出値。判断の欄はこの言い回しで件数を書く。"""
    dec, tk = derived["decisions"], derived["tasks"]
    return [
        (r"(\d+)件のうち(\d+)件が確定", (dec["decided"] + dec["open"], dec["decided"])),
        (r"未決の問いが(\d+)件", (dec["open"],)),
        (r"期限切れの問いが(\d+)件", (dec["overdue"],)),
        (r"残りのタスクが(\d+)件", (tk["todo"] + tk["doing"],)),
        (r"期限切れのタスクが(\d+)件", (tk["overdue"],)),
    ]


def check_judgments(j, derived, current_ids, known_ids):
    errors, warnings = [], []
    if not isinstance(j, dict):
        return ["judgments.json: オブジェクトでない"], []
    for key, limit in JUDGMENT_FIELDS.items():
        v = j.get(key)
        if v is None:
            continue
        if v.get("rating") not in RATINGS:
            errors.append(f"{key}.rating は {' / '.join(RATINGS)} のいずれか（{v.get('rating')!r}）")
        if len(v.get("text", "")) > limit:
            errors.append(f"{key}.text が{limit}字を超えている")
    for i, item in enumerate((j.get("risks") or {}).get("items", [])):
        if len(item) > RISK_MAX:
            errors.append(f"risks.items[{i}] が{RISK_MAX}字を超えている")

    allowed = numbers_in(derived, set())
    ids = set(known_ids)
    for where, text in judgment_texts(j):
        for ref in re.findall(r"\b(?:DR|T)-\d{4}\b", text):
            if ref not in ids:
                errors.append(f"{where}: {ref} が存在しない")
        plain = text.replace("**", "")
        for pattern, expected in phrase_rules(derived):
            for m in re.finditer(pattern, plain):
                got = tuple(int(g) for g in m.groups())
                if got != expected:
                    want = "、".join(str(x) for x in expected)
                    errors.append(f"{where}: 「{m.group(0)}」の数字は導出値（{want}）と違う")
        for pattern, _ in phrase_rules(derived):  # 言い回しで照合した数字は、下の検査に回さない
            plain = re.sub(pattern, "", plain)
        cleaned = re.sub(r"\b[A-Z]{1,3}\d+\b", "", ID_RE.sub("", plain))
        for m in re.findall(r"\d+(?:\.\d+)?", cleaned):
            n = str(int(float(m))) if float(m).is_integer() else m
            if n not in allowed:
                errors.append(f"{where}: 数字 {m} が導出値・計画の値にない（数字は導出値を使い、計算し直さない）")

    for key, meta in _metas(j):
        based = meta.get("based_on") or {}
        changed = [k for k, v in current_ids.items() if based.get(k) != v]
        if changed:
            warnings.append(f"{key}: 判断のもとにした入力が更新されている（{', '.join(changed)}）。再評価が要る")
    return errors, warnings


def _metas(j):
    for key in list(JUDGMENT_FIELDS) + ["risks"]:
        v = j.get(key)
        if isinstance(v, dict) and isinstance(v.get("meta"), dict):
            yield key, v["meta"]


# ---------- 4 表示 ----------

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1b;--muted:#6b6b66;--line:#e2e1dc;--accent:#2f5f8a;
--ok:#2e7d4f;--caution:#a86b00;--bad:#b3261e;--bar:#dfe8f1}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--card:#20201e;--fg:#ecebe6;
--muted:#a3a29b;--line:#3a3935;--accent:#8db8de;--ok:#6cc58f;--caution:#e0a63a;--bad:#f08178;--bar:#2c3a48}}
:root[data-theme="dark"]{--bg:#161615;--card:#20201e;--fg:#ecebe6;--muted:#a3a29b;--line:#3a3935;
--accent:#8db8de;--ok:#6cc58f;--caution:#e0a63a;--bad:#f08178;--bar:#2c3a48}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.7 system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px 48px}h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:0 0 12px}.muted{color:var(--muted);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:16px 0;overflow-x:auto}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile b{display:block;font-size:24px;font-variant-numeric:tabular-nums}.tile span{color:var(--muted);font-size:13px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:13px}td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.id{font-family:ui-monospace,Menlo,monospace;font-size:13px;white-space:nowrap}
.badge{display:inline-block;padding:0 8px;border-radius:999px;font-size:12px;border:1px solid currentColor;white-space:nowrap}
.ok{color:var(--ok)}.caution{color:var(--caution)}.bad{color:var(--bad)}
.bar{background:var(--bar);border-radius:4px;height:8px;min-width:80px}.bar i{display:block;height:8px;border-radius:4px;background:var(--accent)}
.meta{color:var(--muted);font-size:12px;margin-top:6px}
"""

RATING_LABEL = {"ok": "良好", "caution": "注意", "bad": "問題"}
STATUS_LABEL = {"todo": "未着手", "doing": "作業中", "done": "完了", "dropped": "中止",
                "confirmed": "確定", "partial": "一部決定", "deferred": "後回し"}


def esc(s):
    return html.escape(str(s if s is not None else ""))


def rich(s):
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(s))


def meta_html(meta, current_ids):
    if not meta:
        return ""
    parts = [f"評価：{esc(meta.get('assessed_by', ''))}（{esc(meta.get('assessed_at', ''))}）"]
    if meta.get("confirmed_by"):
        parts.append(f"確認：{esc(meta['confirmed_by'])}（{esc(meta.get('confirmed_at', ''))}）")
    else:
        parts.append('<span class="caution">未確認</span>')
    if (meta.get("based_on") or {}) != current_ids:
        parts.append('<span class="caution">入力が更新済み（再評価が要る）</span>')
    return f'<div class="meta">{" ・ ".join(parts)}</div>'


def judgment_block(v, current_ids):
    if not v:
        return '<p class="muted">判断の欄はまだない。</p>'
    r = v.get("rating", "")
    return (f'<p><span class="badge {esc(r)}">{esc(RATING_LABEL.get(r, r))}</span> {rich(v.get("text", ""))}</p>'
            + meta_html(v.get("meta"), current_ids))


def bar(p):
    return "" if p is None else f'<div class="bar"><i style="width:{p}%"></i></div>'


def render(report):
    d, j, cur = report["derived"], report["judgments"], report["inputs"]
    dec, ai, dl, tk, plan = d["decisions"], d["ai"], d["deliverables"], d["tasks"], d["plan"]
    title = d["project"] or "プロジェクト"
    out = [f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>{esc(title)} 状況レポート</title><style>{CSS}</style></head><body><main>',
           f'<h1>{esc(title)} 状況レポート</h1><div class="muted">{esc(d["as_of"])} 時点 ・ '
           f'完成 {esc(plan["completion"].get("date", "未定"))}（{esc(plan["completion"].get("scope", ""))}）</div>']

    out.append(f'<div class="card"><h2>要約</h2>{judgment_block(j.get("summary"), cur)}</div>')

    def tile(value, label):
        return f'<div class="tile"><b>{esc(value)}</b><span>{esc(label)}</span></div>'
    out.append('<div class="tiles">'
               + tile(f'{dec["decided"]} / {dec["decided"] + dec["open"]}', "確定した決定 / 決定（覆されたものを除く）")
               + tile(dec["open"], f'未決の問い（期限切れ {dec["overdue"]}）')
               + tile(f'{dl["complete"]} / {dl["with_questions"]}', "問いがすべて確定した成果物")
               + tile(f'{tk["todo"] + tk["doing"]}', f'残りのタスク（完了 {tk["done"]}）')
               + tile("—" if ai["followed_pct"] is None else f'{ai["followed_pct"]}%',
                      f'AIの推奨の追認（{ai["followed"]} / {ai["recommended_decided"]}）')
               + '</div>')

    if plan["gates"]:
        rows = "".join(f'<tr><td class="id">{esc(g.get("id"))}</td><td>{esc(g.get("name"))}</td>'
                       f'<td class="num">{esc(g.get("date"))}</td><td>{esc(g.get("condition"))}</td>'
                       f'<td>{esc(g.get("status", ""))}</td><td>{esc(g.get("summary") or "—")}</td></tr>' for g in plan["gates"])
        out.append(f'<div class="card"><h2>ゲート</h2><table><tr><th>ID</th><th>名前</th><th>日付</th>'
                   f'<th>通過の条件</th><th>状態</th><th>まとめ</th></tr>{rows}</table></div>')

    walls = plan["walls"]
    qcd = "".join(f'<tr><th style="width:5em">{label}</th><td><div class="muted">壁：{esc(walls.get(key, "未定"))}</div>'
                  f'{judgment_block(j.get(key), cur)}</td></tr>'
                  for key, label in (("quality", "品質"), ("delivery", "納期"), ("cost", "費用")))
    out.append(f'<div class="card"><h2>QCD（壁と評価）</h2><table>{qcd}</table></div>')

    rows = "".join(f'<tr><td class="id">{esc(x["wbs"])}</td><td>{esc(x["title"])}</td>'
                   f'<td>{esc(STATUS_LABEL.get(x["status"], x["status"]))}</td>'
                   f'<td class="num">{x["decided"]} / {x["total"]}</td><td>{bar(x["pct"])}</td></tr>'
                   for x in dl["items"])
    out.append(f'<div class="card"><h2>成果物と決定の進み具合</h2><p class="muted">分母は、その成果物について起票した問い'
               f'（覆されたものを除く）。問いのない成果物は計算しない。</p><table><tr><th>WBS</th><th>成果物</th>'
               f'<th>状態</th><th>確定 / 問い</th><th></th></tr>{rows}</table></div>')

    rows = "".join(f'<tr><td class="id">{esc(o["id"])}</td><td>{esc(o["title"])}</td><td class="id">{esc(o["wbs"])}</td>'
                   f'<td class="num{" bad" if o["overdue"] else ""}">{esc(o["due"] or "—")}</td></tr>'
                   for o in dec["open_list"]) or '<tr><td colspan="4" class="muted">未決の問いはない。</td></tr>'
    out.append(f'<div class="card"><h2>未決の問い</h2><table><tr><th>ID</th><th>問い</th><th>WBS</th>'
               f'<th>期限</th></tr>{rows}</table></div>')

    stale = set(tk["stale"])
    rows = "".join(f'<tr><td class="id">{esc(t["id"])}</td><td>{esc(t["title"])}'
                   f'{"<br><span class=bad>元の決定が覆された。中止か付け替えが要る</span>" if t["id"] in stale else ""}</td>'
                   f'<td class="id">{esc(t["dr"])}</td><td>{esc(STATUS_LABEL.get(t["status"], t["status"]))}</td>'
                   f'<td>{esc(t["owner"])}</td><td class="num{" bad" if t["overdue"] else ""}">{esc(t["due"] or "—")}</td></tr>'
                   for t in tk["active"]) or '<tr><td colspan="6" class="muted">残りのタスクはない。</td></tr>'
    out.append(f'<div class="card"><h2>決定から派生したタスク</h2><table><tr><th>ID</th><th>タスク</th><th>元の決定</th>'
               f'<th>状態</th><th>担当</th><th>期限</th></tr>{rows}</table></div>')

    if tk["recent_done"]:
        rows = "".join(f'<tr><td class="id">{esc(t["id"])}</td><td>{esc(t["title"])}</td><td class="id">{esc(t["dr"])}</td>'
                       f'<td>{esc(t["result"])}<div class="meta">{esc(t["result_ref"])}</div></td></tr>'
                       for t in reversed(tk["recent_done"]))
        out.append(f'<div class="card"><h2>実行結果（最近の完了）</h2><table><tr><th>ID</th><th>タスク</th>'
                   f'<th>元の決定</th><th>結果</th></tr>{rows}</table></div>')

    rows = "".join(f'<tr><td class="id">{esc(r["id"])}</td><td>{esc(r["title"])}</td>'
                   f'<td class="num">{esc(r["decided_at"])}</td><td>{esc(r["decided_by"])}</td></tr>'
                   for r in dec["recent"]) or '<tr><td colspan="4" class="muted">確定した決定はまだない。</td></tr>'
    out.append(f'<div class="card"><h2>最近の決定</h2><table><tr><th>ID</th><th>結論</th><th>日付</th>'
               f'<th>決定した人</th></tr>{rows}</table></div>')

    risks = j.get("risks") or {}
    if risks.get("items"):
        items = "".join(f"<li>{rich(x)}</li>" for x in risks["items"])
        out.append(f'<div class="card"><h2>リスク</h2><ul>{items}</ul>{meta_html(risks.get("meta"), cur)}</div>')

    ids = " ・ ".join(f"{esc(k)} {esc(v)}" for k, v in cur.items())
    out.append(f'<p class="muted">数字は入力から導出した値（LLMを使わない）。判断の欄はLLMの提案で、確認するのは人間。'
               f'<br>入力：{ids}</p></main></body></html>\n')
    return "\n".join(out)


# ---------- 実行 ----------

def build(root):
    derived = derive(root)
    jpath = root / "judgments.json"
    judgments = read_json(jpath) if jpath.exists() else {}
    current = input_ids(root)
    known = {r["id"] for r in read_csv(root / INPUTS["decisions_index"], DECISION_COLUMNS)}
    known |= {r["id"] for r in read_csv(root / INPUTS["tasks"], TASK_COLUMNS)}
    errors, warnings = check_judgments(judgments, derived, current, known)
    report = {"schema_version": SCHEMA_VERSION, "as_of": derived["as_of"], "inputs": current,
              "derived": derived, "judgments": judgments}
    return report, errors, warnings


def dumps(report):
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true")
    g.add_argument("--derive", action="store_true")
    g.add_argument("--print-inputs", action="store_true")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.print_inputs:
            print(json.dumps(input_ids(root), ensure_ascii=False, indent=2))
            return 0
        if args.derive:
            print(json.dumps(derive(root), ensure_ascii=False, indent=2))
            return 0
        report, errors, warnings = build(root)
    except InputError as e:
        print("エラー: " + str(e), file=sys.stderr)
        return 1
    for w in warnings:
        print("警告: " + w, file=sys.stderr)
    for e in errors:
        print("エラー: " + e, file=sys.stderr)
    if errors:
        print("検査に通らなかったので、レポートは書かない。", file=sys.stderr)
        return 1
    out_dir = root / "report"
    files = {"report.json": dumps(report), "report.html": render(report)}
    if args.check:
        bad = [n for n, text in files.items()
               if not (out_dir / n).exists() or (out_dir / n).read_text(encoding="utf-8") != text]
        if bad:
            print(f"{out_dir}: {', '.join(bad)} が入力と一致しない。"
                  f"python3 tools/report.py --root {args.root} で作り直す", file=sys.stderr)
            return 1
        print(f"OK: {out_dir} のレポートは入力と一致する")
        return 0
    out_dir.mkdir(exist_ok=True)
    for n, text in files.items():
        (out_dir / n).write_text(text, encoding="utf-8")
    print(f"レポートを書いた: {out_dir}/report.json、report.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
