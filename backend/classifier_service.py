import re
from typing import Dict, Tuple
from loguru import logger
from app.models.schemas import DocumentType

KEYWORD_RULES: Dict[DocumentType, list] = {
    DocumentType.RENT_AGREEMENT: [
        "lessor", "lessee", "tenant", "landlord", "rent", "tenancy",
        "rental", "lease", "security deposit", "monthly rent", "notice period", "vacate",
    ],
    DocumentType.FIR: [
        "first information report", "fir", "cognizable offence", "police station",
        "sections ipc", "arrested", "accused", "complaint", "investigating officer", "crpc",
    ],
    DocumentType.PROPERTY_DEED: [
        "sale deed", "vendor", "vendee", "conveyance", "transfer of property",
        "sub-registrar", "stamp duty", "possession", "mutation", "immovable property",
    ],
    DocumentType.COURT_NOTICE: [
        "court", "summons", "hearing", "plaintiff", "defendant", "civil judge",
        "high court", "district court", "order", "judgement", "petition", "case no",
    ],
    DocumentType.LOAN_AGREEMENT: [
        "loan", "borrower", "lender", "principal amount", "interest rate",
        "emi", "repayment", "collateral", "mortgage", "hypothecation",
    ],
    DocumentType.EMPLOYMENT: [
        "employer", "employee", "salary", "designation", "joining date",
        "probation", "non-disclosure", "nda", "confidentiality", "termination", "ctc",
    ],
    DocumentType.AFFIDAVIT: [
        "affidavit", "deponent", "solemnly affirm", "sworn",
        "notary", "oath", "true and correct", "declared",
    ],
}

MIN_SCORE = 2


class ClassifierService:

    @classmethod
    def classify(cls, text: str) -> Tuple[DocumentType, float]:
        text_lower = text.lower()
        scores: Dict[DocumentType, int] = {}
        for doc_type, keywords in KEYWORD_RULES.items():
            score = sum(
                len(re.findall(r"\b" + re.escape(kw) + r"\b", text_lower))
                for kw in keywords
            )
            scores[doc_type] = score

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        total = sum(scores.values()) or 1

        if best_score < MIN_SCORE:
            return DocumentType.UNKNOWN, 0.0

        confidence = min(best_score / total, 1.0)
        logger.info(f"Classified: {best_type} (score={best_score}, conf={confidence:.2f})")
        return best_type, round(confidence, 2)

    @classmethod
    def get_doc_type_label(cls, doc_type: DocumentType) -> str:
        labels = {
            DocumentType.RENT_AGREEMENT: "Rent / Lease Agreement",
            DocumentType.FIR: "FIR / Police Complaint",
            DocumentType.PROPERTY_DEED: "Property / Sale Deed",
            DocumentType.COURT_NOTICE: "Court Notice / Summons",
            DocumentType.LOAN_AGREEMENT: "Loan Agreement",
            DocumentType.EMPLOYMENT: "Employment Contract",
            DocumentType.AFFIDAVIT: "Affidavit",
            DocumentType.UNKNOWN: "Legal Document",
        }
        return labels.get(doc_type, "Legal Document")
