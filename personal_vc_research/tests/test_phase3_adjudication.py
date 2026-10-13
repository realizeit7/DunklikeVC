"""Phase-3 entity matching, holdings parsing and adjudication rules (SYNTHETIC rows only)."""
import pandas as pd

from personal_vc_research.adjudicate import decide_strict, footnote_text, series_status
from personal_vc_research.entity_match import match, norm
from personal_vc_research.republic_holdings import MARK, ROW, SUP, SUP_TAIL


def _off(**kw):
    base = {"offering_id": "O1", "issuer_legal_name_at_offering": "Acme Widgets, Inc.", "issuer_current_edgar_name": "",
            "issuer_former_names": "", "initial_filing_date": "2019-03-01", "completion_report_date": "2019-06-15",
            "deadline_in_effect_at_decision": "", "amount_reported_at_close_usd": "100000"}
    base.update(kw)
    return pd.DataFrame([base])


def _frame(site="https://www.acmeapp.com"):
    return pd.DataFrame([{"offering_id": "O1", "issuer_aliases": "", "issuer_website": site}])


def _h(label, month, cap="100000.00", as_of="2023-12-31", marks="", fn=""):
    return {"accession": "A" + as_of[:4], "page": 1, "raw_line": f"{label} {month} {cap}", "listed_entity_label": label,
            "issuance_month": month, "capital_raised_usd": cap, "holdings_as_of": as_of, "marks": marks,
            "footnote_no": fn}


def test_norm_drops_suffixes_and_case():
    assert norm("Acme Widgets, Inc.") == norm("ACME WIDGETS") == "acmewidgets"


def test_exact_requires_issuance_month_in_window():
    m = match(_off(), _frame(), pd.DataFrame([_h("Acme Widgets", "2019-05")]))
    assert m["match_class"].tolist() == ["exact"] and m["association_level"].iloc[0] == "offering"
    late = match(_off(), _frame(), pd.DataFrame([_h("Acme Widgets", "2021-02")]))  # later round of same issuer
    assert late["match_class"].iloc[0] == "ambiguous" and late["association_level"].iloc[0] != "offering"


def test_brand_alias_needs_website_stem_and_consistent_amount():
    ok = match(_off(), _frame(), pd.DataFrame([_h("AcmeApp", "2019-05", cap="95000")]))
    assert ok["match_class"].iloc[0] == "corroborated_alias"
    bad_amt = match(_off(), _frame(), pd.DataFrame([_h("AcmeApp", "2019-05", cap="300000")]))
    assert bad_amt["match_class"].iloc[0] == "ambiguous"


def test_prefix_only_is_never_offering_level():
    m = match(_off(), _frame(site=""), pd.DataFrame([_h("Acmewear", "2019-05")]))
    assert m["match_class"].iloc[0] == "ambiguous" and m["association_level"].iloc[0] == "issuer_or_none"


def test_no_candidate_is_unmatched():
    m = match(_off(), _frame(), pd.DataFrame([_h("Zeta", "2019-05")]))
    assert m["match_class"].iloc[0] == "unmatched"


def test_row_parser_reads_superscript_note_and_marks():
    for line, label, marks, fn in [("Ring9⁶ 11/3/2018 $92,557 2.00% $1,851", "Ring9", "", "6"),
                                   ("Trust & Co¹⁰ 5/1/2019 $225,212 2.00% $4,504", "Trust & Co", "", "10"),
                                   ("Foo Bar* 2020-12 $714,053.00 2.00% $14,281.06", "Foo Bar", "*", ""),
                                   ("Baz (14) 2018-12 $92,557.00 2.00% $1,851.00", "Baz", "", "14")]:
        name = ROW.match(line).group("name").strip()
        sup = SUP_TAIL.search(name)
        fs = sup.group("sup").translate(SUP) if sup else ""
        name = name[:sup.start()].rstrip() if sup else name
        mm = MARK.match(name)
        assert (mm.group("base").strip(), (mm.group("marks") or "") + (mm.group("marks2") or ""), mm.group("fn") or fs) == \
            (label, marks, fn)


def test_footnote_text_both_layouts():
    leg = pd.DataFrame([
        {"holdings_as_of": "2022-12-31", "legend_text_verbatim":
            "Notes\n6. Issuer conducted a tender offer for outstanding Crowd SAFEs at 100 cents on the dollar, which "
            "Republic\nelected to participate in.\n7. Issuer elected to repurchase at 5 cents.\n(1) The dollar amount of securities"},
        {"holdings_as_of": "2023-12-31", "legend_text_verbatim":
            "The securities were liquidated, resulting in an approximate cash payout of 0 cents on the dollar to be\n(6)\n"
            "contributed to the pool.\nThe securities were liquidated, resulting in an approximate cash payout of 100 cents "
            "on the dollar to be\n(14) contributed to the pool.\n57"}])
    assert footnote_text(leg, "2022-12-31", "6").startswith("Issuer conducted a tender offer") and "5 cents" not in \
        footnote_text(leg, "2022-12-31", "6")
    t = footnote_text(leg, "2023-12-31", "14")
    assert "100 cents" in t and "payout of 0 cents" not in t and not t.endswith("57")
    assert footnote_text(leg, "2023-12-31", "") == ""


def _claims(rows):
    return pd.DataFrame([{"series_id": "S", "holdings_as_of": a, "mark": m, "footnote_no": f} for a, m, f in rows])


def test_star_first_report_window_and_instability():
    s = series_status(_claims([("2022-12-31", "", ""), ("2023-12-31", "", ""), ("2024-12-31", "*", ""),
                               ("2025-12-31", "*", "")]))[0]
    assert s["star_first_report_window"] == "(2023-12-31, 2024-12-31]" and not s["mark_disappeared"]
    first_listed_marked = series_status(_claims([("2023-12-31", "*", "")]))[0]
    assert first_listed_marked["star_first_report_window"] == "(none listed, 2023-12-31]"
    gone = series_status(_claims([("2022-12-31", "+", ""), ("2023-12-31", "", "")]))[0]
    assert gone["mark_disappeared"] and gone["plus_years"] == "2022"


def _dec(**kw):
    base = dict(withdrawn=False, listed=False, registry_dissolved=False, ctr_b5=False, indep_closure=False, conflicts=[],
                insolvency=False, star_offering=False, last_ops="", n_ctr=0)
    base.update(kw)
    return decide_strict(**base)


def test_platform_mark_dead_site_or_ctr_never_definitive():
    assert _dec(star_offering=True, n_ctr=1) == ("unresolved", "platform adverse claim only")
    assert _dec(n_ctr=1)[0] == "unresolved"
    assert _dec(insolvency=True)[1].startswith("insolvency proceeding")


def test_definitive_labels_need_documented_evidence_in_order():
    assert _dec(withdrawn=True, listed=True)[0] == "offering_withdrawn"
    assert _dec(listed=True, conflicts=["x"])[0] == "listed_public"  # listing rests on issuer filings, not the mark
    assert _dec(ctr_b5=True)[0] == "dissolved_or_liquidated_documented"
    assert _dec(indep_closure=True)[0] == "operational_closure_documented"
    assert _dec(conflicts=["x"], star_offering=True) == ("unresolved", "conflicting sources")
    assert _dec(last_ops="2025-01-01")[1].startswith("recent operating evidence")
