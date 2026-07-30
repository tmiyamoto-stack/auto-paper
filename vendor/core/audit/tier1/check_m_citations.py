from __future__ import annotations

from .findings import Finding, Status, Severity


def _norm(s) -> str:
    """casefold + strip + 連続空白の畳み込み。"""
    if s is None:
        return ""
    return " ".join(str(s).casefold().split())


def _first_author_surname(authors) -> str | None:
    """authors（list または str）→ 第一著者の姓（正規化済）。None は None。"""
    if authors is None:
        return None
    if isinstance(authors, str):
        first = authors.split(",")[0]
    elif isinstance(authors, (list, tuple)):
        if not authors:
            return None
        first = authors[0]
    else:
        first = authors
    tokens = _norm(first).split()
    return tokens[0] if tokens else None


def check_m_metadata(bibliography: list[dict], metadata_fetcher) -> list[Finding]:
    """引用メタデータ一致照合（check_m の存在確認を拡張）。

    各 bib エントリの claimed `title`/`authors`/`year` を、識別子（DOI/PMID）から
    引いた正規メタデータと照合する。DOI は実在するが title/authors/year が claim と
    食い違う＝誤引用/取り違えを CRITICAL FAIL で捕捉する（DESIGN §9）。既存 `check_m`
    は存在確認として残し、本関数は同一 check_id="M" で追加する（決定的・sorted）。

    規則（各エントリ）:
    - 識別子なし → FAIL/CRITICAL（存在確認は check_m だが no-id はここでも FAIL）。
    - fetcher が例外 → INCOMPLETE/CRITICAL（照合不能）。
    - fetcher が None を返す → FAIL/CRITICAL（存在しない）。
    - メタデータ取得 → 正規化（casefold/strip/空白畳み込み、authors は第一著者姓、
      year は厳密一致）して claim と比較。claim にある title/第一著者/year のいずれかが
      不一致 → FAIL/CRITICAL。claim フィールドが全て一致（または claim 側が欠く）→ PASS。
    """
    findings: list[Finding] = []
    for ref in sorted(bibliography, key=lambda r: str(r.get("id", "?"))):
        rid = ref.get("id", "?")
        doi = ref.get("doi")
        pmid = ref.get("pmid")
        if not doi and not pmid:
            findings.append(Finding("M", Status.FAIL, Severity.CRITICAL,
                f"引用に識別子(DOI/PMID)が無くメタデータ照合不能: {rid}",
                f"ref '{rid}'", variable=rid))
            continue
        try:
            meta = metadata_fetcher(doi, pmid)
        except Exception as e:  # noqa: BLE001 - verification unavailable
            findings.append(Finding("M", Status.INCOMPLETE, Severity.CRITICAL,
                f"引用メタデータ照合が不能: {rid}", f"fetcher error: {e}", variable=rid))
            continue
        if meta is None:
            findings.append(Finding("M", Status.FAIL, Severity.CRITICAL,
                f"引用が実在しない(幻覚の疑い): {rid}", f"doi={doi} pmid={pmid}", variable=rid))
            continue

        mismatches: list[str] = []
        claimed_title = ref.get("title")
        if claimed_title is not None and _norm(claimed_title) != _norm(meta.get("title")):
            mismatches.append(f"title claim='{claimed_title}' canon='{meta.get('title')}'")
        claimed_surname = _first_author_surname(ref.get("authors"))
        if claimed_surname is not None and claimed_surname != _first_author_surname(meta.get("authors")):
            mismatches.append(f"first_author claim='{claimed_surname}' canon='{_first_author_surname(meta.get('authors'))}'")
        claimed_year = ref.get("year")
        if claimed_year is not None and meta.get("year") is not None and str(claimed_year).strip() != str(meta.get("year")).strip():
            mismatches.append(f"year claim='{claimed_year}' canon='{meta.get('year')}'")

        if mismatches:
            findings.append(Finding("M", Status.FAIL, Severity.CRITICAL,
                f"引用メタデータ不一致: DOI実在するが title/authors/year がclaimと不一致=誤引用/取り違えの疑い: {rid}",
                "; ".join(mismatches), variable=rid))
        else:
            findings.append(Finding("M", Status.PASS, Severity.CRITICAL,
                f"引用メタデータ一致: {rid}", f"doi={doi} pmid={pmid}", variable=rid))
    return findings


def check_m(bibliography: list[dict], fetcher) -> list[Finding]:
    findings: list[Finding] = []
    for ref in bibliography:
        rid = ref.get("id", "?")
        doi = ref.get("doi")
        pmid = ref.get("pmid")
        if not doi and not pmid:
            findings.append(Finding("M", Status.FAIL, Severity.CRITICAL,
                f"引用に識別子(DOI/PMID)が無く実在検証不能: {rid}", f"ref '{rid}'", variable=rid))
            continue
        try:
            exists = fetcher(doi, pmid)
        except Exception as e:  # noqa: BLE001 - verification unavailable
            findings.append(Finding("M", Status.INCOMPLETE, Severity.CRITICAL,
                f"引用実在検証が不能: {rid}", f"fetcher error: {e}", variable=rid))
            continue
        if exists:
            findings.append(Finding("M", Status.PASS, Severity.CRITICAL,
                f"引用は実在: {rid}", f"doi={doi} pmid={pmid}", variable=rid))
        else:
            findings.append(Finding("M", Status.FAIL, Severity.CRITICAL,
                f"引用が実在しない(幻覚の疑い): {rid}", f"doi={doi} pmid={pmid}", variable=rid))
    return findings
