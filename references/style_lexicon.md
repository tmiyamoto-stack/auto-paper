# 文体辞書の出典と取り込み範囲（check S / t1.style.ai_phrases）

## 出典

英語パターンは **humanizer_academic**（K. Matsui, MIT License）
https://github.com/matsuikentaro1/humanizer_academic
の 34 パターンから、**語彙・記号レベルで決定的に照合できるものだけ**を抜き出して
`audit/tier1/check_s_style.py` にスナップショットした。

- スナップショット取得日: 2026-07-22
- 実行時に GitHub を参照しない。決定性テスト（DESIGN §7-3「同一入力2回走で結果一致」）が
  ネットワーク依存で壊れるため。辞書更新は明示的なコミットで行う。

## 取り込んだもの / 取り込まなかったもの

| humanizer のパターン | 本スキルでの扱い |
|---|---|
| 7 AI常用語彙 | **一部のみ**取り込み。`comprehensive` / `key` / `valuable` / `crucial` 等、学術文で正当用法が多い語は**意図的に除外**（偽陽性抑制。DESIGN §7-2 の precision 要件） |
| 8 コピュラ回避、9 否定並列、16 冗長定型句、19/21/24/25 語選択 | 取り込み（語彙レベルで決定的） |
| 13 em dash、15 curly quotes | **件数報告のみ**。humanizer は em dash ゼロ許容だが、`The primary endpoint—death from any cause—was adjudicated.` のような正当な学術用法が必ずヒットするため FAIL にしない |
| 10 Rule of Three、11 同義語循環、31 段落結束、34 文リズム | **取り込まない**。文脈・談話構造の判断であり決定的照合が成立しない。Tier2（`judgment_checklists/style.md`）の管轄 |
| 1-6 内容パターン（誇張・宣伝的表現） | 一部は既存 `check_o_overstatement`（因果含意語）と重複するため、check S では扱わない |
| Pass 1/2 の書き換え手順 | 監査層には**取り込まない**。監査エージェントは原稿を編集できない（SKILL.md §1）。書き換え規則は工程4（執筆）と revision エージェントの管轄 |

## 日本語パターンについて（重要な事実訂正）

humanizer_academic は**英語医学論文向けであり、公開 SKILL.md に日本語規則は存在しない**。
`check_s_style._JA_PATTERNS` は本スキル独自の追加であり、humanizer 由来ではない。

**「humanizer は日英対応」と記載してはならない。**

## このチェックが主張しないこと

1. **AI 生成の検出ではない。** 辞書ヒットは AI 生成の証拠ではなく、これらの語句は
   非ネイティブ研究者の常用表現と大きく重なる。文体の帰属判定は機械的に証明不能。
2. **AI 検出器の回避が目的ではない。** 目的は学術散文としての自然さ・簡潔さである。
   検出回避を目的化すると、AI 利用の開示を求めるジャーナル方針と正面衝突する。
   本スキルの監査層の看板は品質であって偽装ではない。
3. **投稿可否ゲートではない。** severity は MINOR、mode は surfacing であり
   `critical_fail` をトリップしない。

## ライセンス

humanizer_academic は MIT License。派生辞書の再配布にあたり、本ファイルが著作権表示と
出典表示を担う。
