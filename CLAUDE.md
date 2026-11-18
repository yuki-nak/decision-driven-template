# Claude Code 用の差分

共通の規約は `AGENTS.md`。ここには、Claude Code に固有のことだけを書く。

@AGENTS.md

## 確認の取り方

- オーナーの判断が要るときは、`AskUserQuestion` で聞く。推奨の選択肢を先頭に置き、ラベルに「(Recommended)」を付ける。
- 回答が得られなかったら（ダイアログが閉じられた、時間切れ）、承認とみなさず、チャットで聞き直す。
- 決定記録には、`recorded_by: Claude`、`evidence` に、その日のセッション記録（`project/sessions/YYYY-MM-DD_題名.md`）を書く。セッション記録には、オーナーの回答を要約して残す。

## サブエージェント

オーナーが、その作業について明示的に指示したときだけ使う。報告はモデルの出力であり、承認ではない。

## Git

- 作業用のブランチで作業し、プッシュする。履歴を書き換えない。
- コミットの前に、`python3 tools/build_index.py`、`python3 tools/validate.py`、`python3 tools/report.py` を実行する。
