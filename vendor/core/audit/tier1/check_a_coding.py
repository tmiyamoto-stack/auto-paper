from __future__ import annotations

from .codebook import DerivedVariable
from .data_dictionary import AmbiguousQuestionCode, load_choices, non_response_ordinals
from .findings import Finding, Status, Severity


def check_a(variables: list[DerivedVariable], dict_csv_path: str) -> list[Finding]:
    findings: list[Finding] = []
    for v in variables:
        if not v.numeric_map:
            continue
        try:
            choices = load_choices(dict_csv_path, v.survey, v.source_question_code, v.year)
        except AmbiguousQuestionCode as exc:
            # 波をまたいで設問コードが再利用されている。混ぜて照合すると偽陽性/偽陰性の
            # 双方を生むため、サイレントに続行せず監査不能として surface する。
            findings.append(
                Finding("A", Status.INCOMPLETE, Severity.CRITICAL,
                        f"設問コードが波をまたいで再利用され照合波を確定できない: {v.name}",
                        str(exc), variable=v.name,
                        rule_id="t1.coding.survey_labels", taxonomy_id="A")
            )
            continue
        if not choices:
            findings.append(
                Finding("A", Status.INCOMPLETE, Severity.CRITICAL,
                        f"一次ソース辞書に設問が見つからず監査不能: {v.name}",
                        f"survey={v.survey} source_question_code={v.source_question_code}",
                        variable=v.name)
            )
            continue
        label_by_ord = {c.ordinal: c.label for c in choices}
        nr = non_response_ordinals(choices)
        declared = set(v.treat_as_missing)
        offenders = []
        for ordi, val in v.numeric_map.items():
            if ordi in nr and ordi not in declared and val is not None:
                offenders.append(("非回答コード混入", ordi, label_by_ord.get(ordi, "?"), val))
            elif ordi in declared and val is not None:
                offenders.append(("欠損宣言と矛盾", ordi, label_by_ord.get(ordi, "?"), val))

        # Fix E: 非回答コードが treat_as_missing にも numeric_map[->None] にも現れない
        # 「未宣言・未処理の passthrough」を検出する。実数値割当（offenders=FAIL）でも
        # 明示 None でもないため、非回答コードが解析へ素通りしている疑いがある。
        # これは check_a_generic の passthrough 検出（fail-closed）をミラーする。
        unhandled = sorted(
            o for o in nr
            if o not in declared and not (o in v.numeric_map and v.numeric_map[o] is None)
            and not (o in v.numeric_map and v.numeric_map[o] is not None)
        )

        if offenders:
            ev = "; ".join(
                f"[{kind}] {v.source_question_code} opt{o}='{lab}' に {val} を割当"
                for kind, o, lab, val in offenders
            )
            findings.append(
                Finding("A", Status.FAIL, Severity.CRITICAL,
                        f"非回答コードを実数値として扱っている: {v.name}", ev, variable=v.name)
            )
        elif unhandled:
            ev = "; ".join(
                f"{v.source_question_code} opt{o}='{label_by_ord.get(o, '?')}' が"
                f"treat_as_missing/numeric_map(None)いずれにも無い"
                for o in unhandled
            )
            findings.append(
                Finding("A", Status.INCOMPLETE, Severity.CRITICAL,
                        f"非回答コードが未宣言・未処理でpassthroughの疑い: {v.name}",
                        ev, variable=v.name)
            )
        else:
            findings.append(
                Finding("A", Status.PASS, Severity.CRITICAL,
                        f"非回答コード処理は妥当: {v.name}",
                        f"{v.source_question_code} 非回答={sorted(nr)}", variable=v.name)
            )
    return findings
