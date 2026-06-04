import re
import json
import requests
from datetime import datetime
from typing import List
from loguru import logger

from app.core.config import settings
from app.models.schemas import AnalysisResult, DocumentType, SupportedLanguage
from app.services.classifier_service import ClassifierService

TEMPLATES = {
    DocumentType.RENT_AGREEMENT: {
        "obligations": [
            "Pay the agreed rent on or before the due date each month.",
            "Maintain the property in good condition and report damages promptly.",
            "Do not sublet without the landlord's written consent.",
            "Give the required notice period before vacating.",
        ],
        "red_flags": [
            "Check if security deposit return timeline is specified.",
            "Verify notice period is equal for both parties.",
            "Look for automatic rent escalation clauses.",
            "Register agreements over 11 months at Sub-Registrar office.",
        ],
        "next_steps": (
            "Read every clause before signing. Get the agreement registered "
            "at your local Sub-Registrar office for agreements over 11 months."
        ),
    },
    DocumentType.FIR: {
        "obligations": [
            "Cooperate with the investigating officer when officially summoned.",
            "Do not tamper with any evidence related to the case.",
            "Appear in court if you receive a summons.",
        ],
        "red_flags": [
            "Note the IPC/BNS sections - they determine bail eligibility.",
            "If you are named as accused, get legal counsel immediately.",
        ],
        "next_steps": (
            "Keep a certified copy of the FIR. If you are the accused, "
            "contact a criminal lawyer without delay."
        ),
    },
    DocumentType.PROPERTY_DEED: {
        "obligations": [
            "Pay the full sale amount as agreed before registration.",
            "Pay applicable stamp duty and registration charges.",
            "Complete registration at Sub-Registrar office within 4 months.",
        ],
        "red_flags": [
            "Get title chain verified by a property lawyer before paying.",
            "Check for mortgages via Encumbrance Certificate.",
            "Verify all property tax receipts are paid.",
        ],
        "next_steps": (
            "Verify title before paying. Register before the deadline. "
            "Apply for mutation after registration."
        ),
    },
    DocumentType.COURT_NOTICE: {
        "obligations": [
            "Appear on the date mentioned - missing it causes ex-parte orders.",
            "Engage a lawyer immediately.",
            "File your response within the court-given deadline.",
        ],
        "red_flags": [
            "Verify the notice is genuine via eCourts portal.",
            "Missing the response deadline can decide the case against you.",
        ],
        "next_steps": (
            "Do not ignore a court notice. Engage a lawyer immediately. "
            "Check case status on ecourts.gov.in."
        ),
    },
    DocumentType.LOAN_AGREEMENT: {
        "obligations": [
            "Repay EMIs on the dates specified.",
            "Maintain the collateral or security in good condition if pledged.",
            "Inform the lender of any change in address or employment.",
        ],
        "red_flags": [
            "Check the actual interest rate (APR) not just the advertised rate.",
            "Look for prepayment penalty clauses.",
            "Verify foreclosure charges if you want to close the loan early.",
        ],
        "next_steps": (
            "Set up auto-debit for EMIs. Keep all payment receipts. "
            "Check your CIBIL score regularly."
        ),
    },
    DocumentType.EMPLOYMENT: {
        "obligations": [
            "Join on the agreed date and serve the full notice period if you resign.",
            "Maintain confidentiality of company information.",
            "Return all company property on exit.",
        ],
        "red_flags": [
            "Check the notice period for both resignation and termination.",
            "Look for non-compete clauses restricting future employment.",
            "Verify the CTC breakup - in-hand vs variable vs deferred.",
        ],
        "next_steps": (
            "Negotiate unfair clauses before signing. "
            "Keep signed copies of your offer letter and appointment letter."
        ),
    },
    DocumentType.AFFIDAVIT: {
        "obligations": [
            "Ensure all statements are true - false statements can lead to perjury.",
            "Sign the affidavit in front of a Notary Public.",
            "Submit within the specified deadline.",
        ],
        "red_flags": [
            "Verify the correct stamp paper denomination is used.",
            "Ensure your name, address, and ID details are correct.",
        ],
        "next_steps": (
            "Get the affidavit attested by a Notary Public. "
            "Keep the original and get certified copies."
        ),
    },
    DocumentType.UNKNOWN: {
        "obligations": [
            "Read all clauses carefully before signing.",
            "Fulfil any payment or performance obligations mentioned.",
            "Comply with all timelines and deadlines stated.",
        ],
        "red_flags": [
            "Look for one-sided penalty clauses that apply only to you.",
            "Check for automatic renewal clauses.",
            "Verify the identity and authority of all parties.",
        ],
        "next_steps": (
            "If unsure about any clause, consult a lawyer before signing. "
            "Free legal aid is available at your nearest DLSA. Call NALSA helpline: 15100."
        ),
    },
}


class ExplanationService:

    @classmethod
    async def explain(
        cls,
        text: str,
        doc_type: DocumentType,
        language: SupportedLanguage,
        document_id: str,
        document_name: str,
    ) -> AnalysisResult:
        if settings.ai_ready:
            return await cls._llm(text, doc_type, language, document_id, document_name)
        return await cls._rule_based(text, doc_type, language, document_id, document_name)
    @classmethod
    async def _rule_based(
        cls, text, doc_type, language, document_id, document_name
    ) -> AnalysisResult:
        tmpl = TEMPLATES.get(doc_type, TEMPLATES[DocumentType.UNKNOWN])
        dates = re.findall(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", text)[:4]
        amounts = re.findall(r"Rs\.?\s*[\d,]+|INR\s*[\d,]+", text)[:4]
        key_dates = (
            [f"Date found: {d}" for d in dates] +
            [f"Amount mentioned: {a}" for a in amounts]
        ) or ["Refer to dates and amounts mentioned in the document."]

        label = ClassifierService.get_doc_type_label(doc_type)
        summary = (
            f"This is a {label}. It is a legally binding document that sets out "
            f"the rights and obligations of the parties involved. "
            + (f"Key amounts: {', '.join(amounts[:2])}." if amounts else "")
        ).strip()

        return AnalysisResult(
            document_id=document_id,
            document_name=document_name,
            document_type=doc_type,
            language=language,
            summary=summary,
            obligations=tmpl["obligations"],
            key_dates=key_dates,
            red_flags=tmpl["red_flags"],
            next_steps=tmpl["next_steps"],
            ai_powered=False,
            processed_at=datetime.utcnow(),
        )

    @classmethod
    async def _llm(
        cls, text, doc_type, language, document_id, document_name
    ) -> AnalysisResult:

        label = ClassifierService.get_doc_type_label(doc_type)
        lang_name = language.value.capitalize()

        system_prompt = f"""You are VakilAI, a legal document assistant for Indian citizens.
Document type: {label}
Output language: {lang_name}

Explain this document clearly to someone with no legal background.
Respond ONLY with valid JSON. No markdown, no extra text outside JSON.

{{
  "summary": "2-3 sentence plain language description of what this document is",
  "obligations": ["obligation 1", "obligation 2", "obligation 3", "obligation 4"],
  "key_dates": ["specific date or amount from document 1", "specific date or amount 2"],
  "red_flags": ["concern 1", "concern 2", "concern 3"],
  "next_steps": "What the person should do next in simple language"
}}

Rules:
- Use simple language a Class 10 student understands
- Output ALL text in {lang_name} except the JSON keys
- Extract actual values (amounts, dates, names) from the document
- Flag anything unusual or one-sided as a red flag
- Never use legal jargon without explaining it immediately"""

        headers = {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": settings.groq_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Here is the document text:\n\n{text[:6000]}"}
            ],
            "temperature": 0.3,
            "max_tokens": 1200
        }

        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Groq API error {response.status_code}: {response.text}")
                return await cls._rule_based(text, doc_type, language, document_id, document_name)

            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip()

            # Clean markdown if Groq wraps in code blocks
            if "```" in raw:
                parts = raw.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{"):
                        raw = part
                        break

            raw = raw.strip()
            result_data = json.loads(raw)

            return AnalysisResult(
                document_id=document_id,
                document_name=document_name,
                document_type=doc_type,
                language=language,
                summary=result_data.get("summary", ""),
                obligations=result_data.get("obligations", []),
                key_dates=result_data.get("key_dates", []),
                red_flags=result_data.get("red_flags", []),
                next_steps=result_data.get("next_steps", ""),
                ai_powered=True,
                processed_at=datetime.utcnow(),
            )

        except json.JSONDecodeError as e:
            logger.error(f"Groq returned invalid JSON: {e} | raw: {raw[:200]}")
            return await cls._rule_based(text, doc_type, language, document_id, document_name)
        except Exception as e:
            logger.error(f"Groq API failed: {e}")
            return await cls._rule_based(text, doc_type, language, document_id, document_name)