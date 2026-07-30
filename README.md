# auto-paper

任意ドメインの表形式データ（CSV/TSV/Excel 由来）から、研究課題をもとに**監査ゲート付き**で論文/レポートのドラフトを生成する Claude Code スキル。臨床・疫学に限らず、業務・経済・教育・運用ログにも適用できる。

7工程・4人間ゲート（G0/G1/G1.5/G2）・3層監査（決定的アサーション → LLM 独立監査 → cross-model 外部議論）で、次のような**機械的欠陥**を構造的に検出する。

- 非回答/センチネルコードの実数値混入（例: 満足度 99＝無回答を「99点」として平均に算入）
- Methods 記載と実装コードの乖離
- 幻覚引用（DOI の実在確認）
- N・除外フローの不整合
- 値域外れ値・単位混在・打ち切り値の未処理

---

## clone するだけで動く（監査コアを同梱）

```bash
git clone https://github.com/tmiyamoto-stack/auto-paper.git ~/.claude/skills/auto-paper
cd ~/.claude/skills/auto-paper
python3 -m pytest                    # 外部依存なし（Python 標準ライブラリのみ）
```

監査コア（`audit/` の19の決定的チェックと `pipeline/` のスキーマ・プロファイラ、
51ファイル・約4,900行）は `vendor/core/` に**同梱**してある。stdlib のみで
外部依存が無いため、pip install も別リポジトリも不要。

### 同梱物は「原本の写し」であって編集対象ではない

コアの原本は別スキルが保持しており、`vendor/core/` はその同梱コピーである。
コピーは放置すると原本から静かに遅れるため、次の2点で原本を唯一の真実に保つ:

- **解決順序で原本が同梱物より優先される。** 手元に原本（隣接スキル）があれば
  そちらが使われるので、コアを直せば即座に反映される。
- **`vendor/PROVENANCE.json`** が原本のコミットと全ファイルの sha256 を記録し、
  改竄・欠落・ドリフトを検出する。

```bash
python3 sync_core.py --check                      # 同梱物の完全性を検証
python3 sync_core.py --check --source <原本>      # 原本とのドリフトも検証
python3 sync_core.py --source <原本>              # 同梱を更新
```

`vendor/core/` を直接編集しないこと（次回同期で失われ、PROVENANCE と食い違う）。

### コアの解決順序

1. 明示指定（`--core`）
2. 環境変数 `AUTO_PAPER_CORE`
3. `config.yaml` の `core_skill_path`
4. 兄弟ディレクトリの構造探索（ディレクトリ名ではなく `audit/tier1/runner.py` 等の有無で判定）
5. **同梱コア `vendor/core/`**

1 と 2 は利用者の明示指定なので、不正なら別のコアへ黙ってフォールバックせず失敗する
（取り違えに気づけなくなるため）。候補が複数見つかった場合も自動選択せず
`CoreAmbiguous` で失敗する。

---

## 使い方

```bash
# 工程5（監査）の実走
python3 run_audit.py --run-dir <成果物ディレクトリ> --domain general
python3 run_audit.py --run-dir <run> --domain clinical --data-csv data.csv --json findings.json
```

### 終了コード

| コード | 意味 |
|---|---|
| `0` | 全チェックが走り、FAIL も INCOMPLETE も無い |
| `1` | FAIL または INCOMPLETE あり（未実行チェックを含む＝人間の確認が必要） |
| `2` | **監査を実行できなかった**（コア未解決・入力欠落・ドメイン未宣言・成果物の形式不正） |

`2` を `1` と区別するのが重要である。監査が動かなかったことを「不合格」と同じ扱いにすると、設定ミスを検出結果と読み違える。想定外の例外も `2` に正規化される。

### 供給しなかったチェックは「未実行」として必ず表面化する

コアは optional 入力が未供給のチェックを意図的スキップとして扱い、finding を出さない。素朴に呼ぶと「19チェック中2つしか走っていないのに `PASS=2 FAIL=0 INCOMPLETE=0` で exit 0」になる。

そこで本ドライバは `config.yaml` の `profiles.default.checks` を**実際に読み**、finding も coverage proof も出なかったチェックを「入力未供給で未実行」として INCOMPLETE 報告する。入力を揃えない限り exit 0 に到達しない。

---

## 他の人に渡すときのプロンプト

そのままコピーして使える。セットアップは clone 1行だけで、別途の準備は要らない。

```bash
git clone https://github.com/tmiyamoto-stack/auto-paper.git ~/.claude/skills/auto-paper
```

### A. 監査だけ回す（最頻用）

```
auto-paper スキルで解析成果物を監査してください。

  cd ~/.claude/skills/auto-paper
  python3 run_audit.py --run-dir <成果物ディレクトリ> --domain general --data-csv <CSV> --json findings.json

- domain は clinical / survey / general から必ず明示（省略すると exit 2 で止まる）
- 終了コードを区別して報告: 0=指摘なし / 1=FAIL・INCOMPLETE あり / 2=監査を実行できなかった
- 「未実行チェック（入力未供給）」は合格ではなく「そのチェックが走っていない」という意味。
  何を用意すれば走るかを出力から拾って一覧にしてください。
```

### B. データから一式作る（RQ → ドラフト）

```
auto-paper スキルで、下記データから論文/レポートのドラフトを作ってください。

- データ: <CSVパス>
- リサーチクエスチョン: <問い>
- ドメイン: clinical / survey / general

~/.claude/skills/auto-paper/agents/ の工程プロンプトに従って進めてください。

  工程1 設計 → 00_spec/sap.md と sap_ranges.json
        値域(impossible_ranges/plausible_ranges)と単位を必ず宣言すること。
        宣言しないと check D/U が走らず「未実行」で残ります。
  ★G0 私の承認を取る（承認なしに工程2へ進まない）
  工程2 変数 → data_profile.json と variable_codebook.json
        センチネル候補は必ず treat_as_missing に宣言し、実数値を割り当てない。
        可能なら user_dictionary.json も書く（検出が INCOMPLETE→確定FAIL に格上げされる）
  ★G1 私の承認を取る
  工程3 分析 → results.json / flow.json / methods_claims.json / code_filters.json
  工程4 執筆 → 数値は全てプレースホルダ（手書き数値は禁止）
  工程5 監査 → run_audit.py を実走し、終了コードごと報告

G0 と G1 は人間の承認ゲートです。そこで必ず止まってください。
```

### C. Tier2/3（Sol・Fable による外部監査）まで回す

```
Tier1 の結果を受けて、agents/05_audit.md に従い Tier2/3 監査を実施してください。

- クリティカル項目の一次監査は Codex(Sol)。第二票は Gemini。
- Fable は Claude 系列なので、成果物が Claude 製である限りクリティカル一次監査から
  除外し、Sol と第二票が割れたときの第三票(tiebreak)としてのみ使うこと。
- 監査者には生成経緯を渡さず、findings と一次証拠のみを渡す（盲検）。
- 判定は references/judgment_checklists/*.md のルーブリックに従い、
  各観点を PASS/REVISE/INCOMPLETE で構造化して返させる。
- Tier1 の「未実行チェック」一覧を Tier2 判定者へ明示的に引き渡す。
- クリティカルに FAIL か INCOMPLETE が一票でもあれば ESCALATE_HUMAN。統括は覆さない。
```

### 相手に必ず伝えること

- **exit 1 が通常。** 入力を揃えるまで未実行チェックが INCOMPLETE で残るため。exit 0 は「全チェックが走って指摘ゼロ」。
- **exit 2 は不合格ではなく「監査が動かなかった」。** 混同すると設定ミスを検出結果と読み違える。
- **Tier2/3 は自動では走らない。** `run_audit.py` が回すのは Tier1 のみで、Sol/Fable の起動は統括（Claude）が手順書に従って行う。
- **英語原稿は出ない。** 翻訳・英文校正は工程外。
- **check A には偽陰性リスクがある。** 一次ソースが自動プロファイル（ヒューリスティック）なので、取りこぼしの最終防波堤は G1 の人間確認。「機械保証済み」と読ませない。
- **数値の再現保証は未実装。** 保証は「原稿の数値が `results.json` と一致すること」まで。

---

## ドメインの扱い

`domain` は `clinical` / `survey` / `general` を run ごとに**必ず宣言**する（既定値なし。暗黙に `general` へ倒すと「値域を照合しなかった」ことに気づけないため）。

**ドメインはチェック集合を選ばない。参照データ（値域・単位の基準）のパックを選ぶだけである。**

値域外れ値・単位混在・打ち切り・不死時間バイアスはいずれも臨床固有の概念ではない:

- 「ありえない値」は業務データにも普通にある（負の売上、在庫 -1、負の所要時間）
- 単位混在はむしろ経済データの方が深刻（円/千円/百万円、名目/実質）
- 打ち切りは所得のトップコーディングで日常的に起きる
- 不死時間バイアスは縦断データならドメインを問わず成立する

臨床固有なのはチェックの**ロジック**ではなく**参照データ**だけ。したがって19チェックは全ドメイン共通で走る。

優先順位: **研究ごとの SAP 宣言 ＞ ドメインパック既定値**。

---

## テスト

```bash
python3 -m pytest        # 46 tests
```

非臨床フィクスチャ `tests/fixtures/retail.csv`（小売の売上パネル、臨床用語ゼロ）に、満足度 99（非回答コード）と売上 -1（ありえない値）を仕込んであり、両方が CRITICAL で捕まることを固定している。

ドライバ（`run_audit.py`）の統合テストを14本含む。初版はここにテストが1本も無く、外部レビューで critical 欠陥4件が見つかった経緯があるため、終了コード契約・未実行チェックの報告・profile-only モードを明示的に固定している。

---

## 保証範囲外（正直な開示）

- **英語原稿を生成しない。** 執筆エージェントは日本語で、翻訳・英文校正工程は存在しない。
- **数値の再現アサーションは未実装。** 保証しているのは「原稿の数値が `results.json` と一致すること」まで。`results.json` 自体が生データから再現するかは保証しない。
- **precision は実証されていない。** 新規チェックを足すほど偽陽性が積み上がる構造であり、「達成済み」と述べてはならない。
- **check A は偽陰性リスクが高い。** 一次ソースが自動データプロファイル（ヒューリスティック）＋任意ユーザー辞書であり、確定した ground truth に照合しているわけではない。取りこぼしの最終防波堤は G1 の人間確認である。
