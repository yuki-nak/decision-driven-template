---
id: DR-0000
title: 問いを一文で（決定後は結論を一文で）
wbs: "0.0"
category: design          # management / design / evaluation
status: open              # open / decided / superseded
owner: オーナー            # 決める人の役割
due:                      # 決める期限（YYYY-MM-DD）
decided_at:               # 決めた日（YYYY-MM-DD）
decided_by:               # 決めた人の役割。人間だけが決める
recorded_by:              # 記録した人の役割、またはAIエージェントの名前
evidence:                 # 承認の根拠の場所（対話の日付、PR、議事録）。記録した人と決めた人が違うときは必須
supersedes:               # この記録が覆す前の記録のID
affects: []               # 影響する文書のID（D01 など。documents.csv）
ai_recommended: none      # AIが推奨した選択肢（A、B など）。なければ none
followed_recommendation:  # 決定のときに書く。推奨どおりなら true
dialogue_before:          # 決める前に、AIとの対話で疑問を確かめたか（true / false）
verify_at:                # 決定の結果を確かめる時期（日付、またはゲートのID）。任意
---

# DR-0000 タイトル

## 背景

なぜこの問いが生じたか。

## 選択肢

- A：
- B：

## 決定と理由

決まったら、選んだ選択肢と理由を書く。決まるまでは「未定。」と書き、現状の案があればそれも書く。

## 期待（任意）

決定の時点で、何が起きることを期待しているか。`verify_at` の時期に、期待どおりだったかを確かめる。
