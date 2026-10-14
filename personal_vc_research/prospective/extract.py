"""Extraction: Form C XML fields (issuer-reported structured data) and bounded text-regex term candidates.

Nothing here is an analyst interpretation. XML values are 'structured_form_field_issuer_reported'. Regex hits from
document text are 'text_regex_unreviewed' with a page locator and must be checked against the contract.
A field that is absent is recorded with value NULL and a missing_reason — never as 0.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from personal_vc_research.pdftext import text_quality

# (xml tag, fact field, unit, currency, period)
XML_FIELDS = [
    ("nameOfIssuer", "legal_name", "", "", ""),
    ("legalStatusForm", "legal_form", "", "", ""),
    ("jurisdictionOrganization", "jurisdiction", "", "", ""),
    ("dateIncorporation", "date_incorporation", "date", "", ""),
    ("issuerWebsite", "issuer_website", "", "", ""),
    ("companyName", "intermediary_name", "", "", ""),
    ("commissionCik", "intermediary_cik", "", "", ""),
    ("commissionFileNumber", "intermediary_file_number", "", "", ""),
    ("compensationAmount", "intermediary_compensation_text", "", "", ""),
    ("financialInterest", "intermediary_financial_interest_text", "", "", ""),
    ("securityOfferedType", "security_type", "", "", ""),
    ("securityOfferedOtherDesc", "security_description", "", "", ""),
    ("noOfSecurityOffered", "number_of_securities_offered", "count", "", ""),
    ("price", "price_per_security", "currency", "USD", ""),
    ("priceDeterminationMethod", "price_determination_method", "", "", ""),
    ("offeringAmount", "target_offering_amount", "currency", "USD", ""),
    ("overSubscriptionAccepted", "oversubscription_accepted", "", "", ""),
    ("maximumOfferingAmount", "maximum_offering_amount", "currency", "USD", ""),
    ("deadlineDate", "offering_deadline", "date", "", ""),
    ("currentEmployees", "current_employees", "count", "", ""),
    ("totalAssetMostRecentFiscalYear", "total_assets", "currency", "USD", "most_recent_fiscal_year"),
    ("totalAssetPriorFiscalYear", "total_assets", "currency", "USD", "prior_fiscal_year"),
    ("cashEquiMostRecentFiscalYear", "cash_and_equivalents", "currency", "USD", "most_recent_fiscal_year"),
    ("cashEquiPriorFiscalYear", "cash_and_equivalents", "currency", "USD", "prior_fiscal_year"),
    ("actReceivedMostRecentFiscalYear", "accounts_receivable", "currency", "USD", "most_recent_fiscal_year"),
    ("shortTermDebtMostRecentFiscalYear", "short_term_debt", "currency", "USD", "most_recent_fiscal_year"),
    ("shortTermDebtPriorFiscalYear", "short_term_debt", "currency", "USD", "prior_fiscal_year"),
    ("longTermDebtMostRecentFiscalYear", "long_term_debt", "currency", "USD", "most_recent_fiscal_year"),
    ("longTermDebtPriorFiscalYear", "long_term_debt", "currency", "USD", "prior_fiscal_year"),
    ("revenueMostRecentFiscalYear", "revenue", "currency", "USD", "most_recent_fiscal_year"),
    ("revenuePriorFiscalYear", "revenue", "currency", "USD", "prior_fiscal_year"),
    ("costGoodsSoldMostRecentFiscalYear", "cost_of_goods_sold", "currency", "USD", "most_recent_fiscal_year"),
    ("costGoodsSoldPriorFiscalYear", "cost_of_goods_sold", "currency", "USD", "prior_fiscal_year"),
    ("actReceivedPriorFiscalYear", "accounts_receivable", "currency", "USD", "prior_fiscal_year"),
    ("taxPaidPriorFiscalYear", "taxes_paid", "currency", "USD", "prior_fiscal_year"),
    ("netIncomeMostRecentFiscalYear", "net_income", "currency", "USD", "most_recent_fiscal_year"),
    ("netIncomePriorFiscalYear", "net_income", "currency", "USD", "prior_fiscal_year"),
    ("taxPaidMostRecentFiscalYear", "taxes_paid", "currency", "USD", "most_recent_fiscal_year"),
]

# Bounded term candidates in document text. Each hit needs review against the contract text.
TERM_PATTERNS = {
    "valuation_cap_candidate": re.compile(r"valuation\s+cap[^$\n]{0,60}\$\s?([\d,]+(?:\.\d+)?(?:[ \t]?(?:million|billion)\b|M\b)?)", re.I),
    "discount_rate_candidate": re.compile(r"discount(?:\s+rate)?[^%\n]{0,40}?(\d{1,2}(?:\.\d+)?)\s?%", re.I),
    "interest_rate_candidate": re.compile(r"interest[^%\n]{0,40}?(\d{1,2}(?:\.\d+)?)\s?%\s*(?:per annum|annually|simple|compounded)?", re.I),
    "maturity_candidate": re.compile(r"maturity\s+date[^.\n]{0,80}", re.I),
    "minimum_investment_candidate": re.compile(r"minimum\s+investment[^$\n]{0,40}\$\s?([\d,]+(?:\.\d+)?)", re.I),
    "pre_money_valuation_candidate": re.compile(r"pre-?money\s+valuation[^$\n]{0,40}\$\s?([\d,]+(?:\.\d+)?(?:[ \t]?million\b|M\b)?)", re.I),
    "post_money_valuation_candidate": re.compile(r"post-?money\s+valuation[^$\n]{0,40}\$\s?([\d,]+(?:\.\d+)?(?:[ \t]?million\b|M\b)?)", re.I),
}
# Language that identifies the security instrument itself (contract text present in the capture).
CONTRACT_MARKERS = re.compile(r"THIS CERTIFIES THAT[^.]{0,200}(in exchange for the payment|purchase amount)|"
                              r"SIMPLE AGREEMENT FOR FUTURE EQUITY|CONVERTIBLE PROMISSORY NOTE|SUBSCRIPTION AGREEMENT", re.I)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_xml(data: bytes) -> dict[str, list[str]]:
    """Flatten an EDGAR XML document to {local_tag: [text, ...]} for leaf elements."""
    out: dict[str, list[str]] = {}
    root = ET.fromstring(data)
    for el in root.iter():
        if len(el) == 0 and el.text and el.text.strip():
            out.setdefault(_local(el.tag), []).append(el.text.strip())
    return out


def form_c_facts(x: dict[str, list[str]]) -> list[dict]:
    facts = []
    for tag, field, unit, cur, period in XML_FIELDS:
        vals = x.get(tag)
        if vals:
            facts.append({"field": field, "value": vals[0], "unit": unit, "currency": cur, "financial_period": period,
                          "locator": f"primary_doc.xml <{tag}>", "verification_status": "structured_form_field_issuer_reported",
                          "fact_kind": "source_statement", "extraction_method": "xml"})
        else:
            facts.append({"field": field, "value": None, "unit": unit, "currency": cur, "financial_period": period,
                          "locator": f"primary_doc.xml <{tag}> absent", "verification_status": "missing",
                          "missing_reason": "field absent or blank in Form C XML", "fact_kind": "source_statement",
                          "extraction_method": "xml"})
    return facts


def pdf_pages(path: Path) -> list[str]:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return [(p.extract_text() or "") for p in pdf.pages]


def text_terms(pages: list[str]) -> tuple[list[dict], dict]:
    """Return term candidates with page locators and a summary (text quality, contract markers)."""
    facts, contract_pages = [], []
    joined_quality = text_quality(" ".join(pages[:20])) if pages else 0.0
    for i, t in enumerate(pages, start=1):
        if CONTRACT_MARKERS.search(t):
            contract_pages.append(i)
        for field, rx in TERM_PATTERNS.items():
            for m in rx.finditer(t):
                snippet = re.sub(r"\s+", " ", t[max(0, m.start() - 60): m.end() + 60]).strip()
                raw = m.group(1) if m.groups() else m.group(0)
                facts.append({"field": field, "value": re.sub(r"\s+", " ", raw).strip(),
                              "unit": "", "currency": "", "financial_period": "", "locator": f"page {i}: …{snippet}…",
                              "verification_status": "text_regex_unreviewed", "fact_kind": "extracted_fact",
                              "extraction_method": "pdfplumber_text_regex"})
    return facts, {"pages": len(pages), "text_quality": round(joined_quality, 3), "contract_marker_pages": contract_pages}
