<!--
英語原稿の骨格テンプレート（工程4が複製して埋める）。

規律:
  - 数値は例外なく {{results.json のドットパス}} で書く。手書き数値は禁止。
    書式は {{key:.2f}} / {{key:,}} のように指定できる（render_manuscript.py が処理）。
  - 本テンプレートはデザイン非依存の骨格である。研究デザインに応じて
    報告ガイドライン（観察研究=STROBE / RCT=CONSORT / 予測モデル=TRIPOD）に
    合わせて節を足し引きしてよいが、準拠していない場合は準拠を自称しないこと。
  - <!-- --> のコメントは最終稿では削除する。
-->

# {{meta.title}}

Running head: {{meta.running_head}}

Authors: [著者が確定させる。捏造しない]
Affiliations: [同上]
Corresponding author: [同上]

---

## Abstract

**Background**: [研究の背景と空白を2–3文で]

**Methods**: [データ源・デザイン・対象・曝露/アウトカムの操作的定義・統計手法。標本サイズは {{flow.analysis_n:,}} のようにプレースホルダで]

**Results**: [主要推定値。例: adjusted OR {{m1.or:.2f}} (95% CI {{m1.ci_low:.2f}}–{{m1.ci_high:.2f}})]

**Conclusions**: [観察研究なら因果を含意する語（reduces/prevents/causes）を使わない]

**Keywords**: [3–6語]

---

## Introduction

<!-- 既知のこと → 空白 → 本研究の問い。文献は bibliography.json に実在するものだけを引く -->

## Methods

### Data source and study design

### Study population and eligibility

<!-- 除外連鎖は flow.json と一致させる。例: {{flow.raw_n:,}} → {{flow.analysis_n:,}} -->

### Exposure

### Outcomes

### Covariates

### Statistical analysis

<!-- 実装と一致させること。使っていない手法を書かない（check B が突合する）。
     欠測・センチネル処理は variable_codebook.json の treat_as_missing 宣言と一致させる -->

### Ethical considerations

<!-- 事実確認できた場合のみ記述する。未確認の定型句を書き加えない -->

## Results

### Participant characteristics

**Table 1. Baseline characteristics**

| Characteristic | Overall | Group A | Group B |
|---|---|---|---|
| N | {{desc.all.n:,}} | | |

### Main analysis

<!-- Results には解釈を混ぜない。意義づけ・因果解釈・先行研究との比較は Discussion へ -->

### Sensitivity analyses

## Discussion

### Principal findings

### Comparison with previous studies

### Possible mechanisms

### Limitations

<!-- 非確率標本・便宜標本・単施設なら、一般化可能性と選択バイアスに必ず言及する
     （check G が言及の有無を機械的に確認する）。
     標本内の割合を母集団の値として述べない -->

### Future directions

## Conclusions

## Declarations

<!-- 資金源・COI・著者貢献・倫理承認番号・データ利用許諾は著者が確定させる。
     捏造は虚偽記載になるため、確定するまで空欄のまま残す -->

## References

<!-- bibliography.json に登録し、DOI/PMID を付す。check M が実在を照会する。
     識別子の無い機関文書は FAIL として surface されるので、手動確認の記録を残す -->
