import re
import json
import requests
from datetime import datetime
from typing import List
from loguru import logger

from app.api.core.config import settings
from app.api.models.schemas import AnalysisResult, DocumentType, SupportedLanguage
from app.api.services.classifier_service import ClassifierService


TEMPLATES = {
    DocumentType.RENT_AGREEMENT: {
        "obligations": [
            "Pay the agreed rent on or before the due date each month without fail.",
            "Maintain the property in good condition and report any damages to landlord promptly.",
            "Do not sublet or transfer the property to anyone without landlord's written consent.",
            "Give the required notice period before vacating — check the exact number of days.",
            "Pay utility bills (electricity, water, gas) on time in your name if specified.",
        ],
        "red_flags": [
            "⚠️ Check if security deposit return timeline is clearly specified — it should be within 30 days of vacating.",
            "⚠️ Verify the notice period is equal for BOTH landlord and tenant — one-sided notice is unfair.",
            "⚠️ Look for automatic rent escalation clauses — ensure % increase is capped and agreed upon.",
            "⚠️ Agreements over 11 months MUST be registered at Sub-Registrar office or they are not legally valid.",
            "⚠️ Check if landlord can enter property without notice — they must give 24 hours notice.",
        ],
        "next_steps": (
            "Read every clause carefully before signing. Get the agreement registered at your local "
            "Sub-Registrar office if it is over 11 months. Keep a copy of all receipts. "
            "Take photos of the property before moving in to avoid false damage claims."
        ),
    },
    DocumentType.FIR: {
        "obligations": [
            "Cooperate fully with the investigating officer when officially summoned.",
            "Do not tamper with, destroy, or hide any evidence related to the case.",
            "Appear in court if you receive a summons — ignoring it is a criminal offence.",
            "Provide accurate statements — giving false information in an FIR is punishable.",
        ],
        "red_flags": [
            "⚠️ Note the IPC/BNS sections carefully — they determine if the offence is bailable or non-bailable.",
            "⚠️ If you are named as accused, get a criminal lawyer IMMEDIATELY — do not wait.",
            "⚠️ Check if the FIR was filed within the limitation period for the offence.",
            "⚠️ Verify the FIR number and police station details are correct on your copy.",
        ],
        "next_steps": (
            "Keep a certified copy of the FIR at all times. If you are the accused, contact a criminal "
            "lawyer without delay and apply for anticipatory bail if arrest is likely. "
            "Track the case on ecourts.gov.in using the FIR number."
        ),
    },
    DocumentType.PROPERTY_DEED: {
        "obligations": [
            "Pay the full sale amount as agreed in the deed before or at the time of registration.",
            "Pay stamp duty (5-7% of property value) and registration charges (1%) at Sub-Registrar office.",
            "Complete registration within 4 months of execution of the deed.",
            "Apply for mutation of property records at local municipal office after registration.",
        ],
        "red_flags": [
            "⚠️ CRITICAL: Get full title chain verified by a property lawyer before paying ANY amount.",
            "⚠️ Obtain Encumbrance Certificate (EC) for minimum 30 years — check for mortgages or liens.",
            "⚠️ Verify all property tax receipts are paid up to date — unpaid taxes become buyer's liability.",
            "⚠️ Check for multiple ownership or joint owners — all must sign the deed.",
            "⚠️ Verify that the seller's Aadhaar, PAN, and identity match exactly with documents.",
        ],
        "next_steps": (
            "Do NOT pay full amount before title verification. Register within 4 months. "
            "Apply for mutation after registration. Keep all original documents in a safe place. "
            "Get property insurance after purchase."
        ),
    },
    DocumentType.COURT_NOTICE: {
        "obligations": [
            "Appear in court on the EXACT date and time mentioned — missing causes ex-parte orders against you.",
            "Engage a qualified lawyer immediately — do not attend court without legal representation.",
            "File your written response/reply within the court-given deadline — usually 30 days.",
            "Collect all relevant documents and evidence before your first court appearance.",
        ],
        "red_flags": [
            "⚠️ URGENT: Missing even one court date can result in the case being decided against you.",
            "⚠️ Verify the notice is genuine on the eCourts portal (ecourts.gov.in) before responding.",
            "⚠️ Check if the notice requires you to produce specific documents or witnesses.",
            "⚠️ Note the court name, case number, and judge's name — these are critical reference points.",
        ],
        "next_steps": (
            "Do NOT ignore a court notice under any circumstances. Engage a lawyer within 48 hours. "
            "Check case status on ecourts.gov.in. File your response well before the deadline. "
            "Free legal aid is available at District Legal Services Authority (DLSA) — call NALSA: 15100."
        ),
    },
    DocumentType.LOAN_AGREEMENT: {
        "obligations": [
            "Repay EMIs on the exact dates specified — even one missed EMI affects your CIBIL score.",
            "Maintain any collateral or security pledged in good condition throughout the loan tenure.",
            "Inform the lender immediately of any change in address, employment, or contact details.",
            "Do not take additional loans that may affect your repayment capacity without informing lender.",
        ],
        "red_flags": [
            "⚠️ Check the ACTUAL interest rate (APR/EIR) — not just the advertised flat rate — they differ significantly.",
            "⚠️ Look for prepayment penalty clauses — some lenders charge 2-5% for early repayment.",
            "⚠️ Verify foreclosure charges if you plan to close the loan early.",
            "⚠️ Check if interest rate is fixed or floating — floating rates can increase your EMI unexpectedly.",
            "⚠️ Read the cross-default clause — defaulting on one loan may trigger default on others.",
        ],
        "next_steps": (
            "Set up auto-debit for EMIs to avoid missed payments. Keep all payment receipts and statements. "
            "Check your CIBIL score every 6 months. Never sign blank loan documents. "
            "Get a loan account statement every year to verify outstanding balance."
        ),
    },
    DocumentType.EMPLOYMENT: {
        "obligations": [
            "Join on the agreed date — failure to join after accepting may have legal or financial consequences.",
            "Serve the full notice period as specified when resigning — usually 30-90 days.",
            "Maintain strict confidentiality of all company data, clients, and business information.",
            "Return all company property (laptop, ID card, access cards) on last working day.",
            "Comply with all company policies, codes of conduct, and HR policies.",
        ],
        "red_flags": [
            "⚠️ Check if notice period is EQUAL for both you and employer — asymmetric notice is unfair.",
            "⚠️ Read non-compete clauses carefully — excessive restrictions on future employment may not be enforceable.",
            "⚠️ Verify the FULL CTC breakup: in-hand salary vs variable pay vs deferred components.",
            "⚠️ Check if variable pay has unrealistic targets attached — it may never be paid.",
            "⚠️ Look for IP assignment clauses — some companies claim ownership of personal projects.",
            "⚠️ Verify probation period terms — can they terminate without notice during probation?",
        ],
        "next_steps": (
            "Negotiate any unfair clauses BEFORE signing — it is much harder after. "
            "Keep signed copies of offer letter, appointment letter, and all policies. "
            "Clarify variable pay targets in writing. "
            "Excessive non-compete clauses (>1 year, entire industry) are generally not enforceable in India."
        ),
    },
    DocumentType.AFFIDAVIT: {
        "obligations": [
            "Ensure ALL statements in the affidavit are true — false statements constitute perjury.",
            "Sign the affidavit only in front of a Notary Public or authorised officer.",
            "Submit within the specified deadline — late affidavits may not be accepted.",
            "Use the correct stamp paper denomination as specified by the authority requiring it.",
        ],
        "red_flags": [
            "⚠️ Verify the correct stamp paper denomination is used — wrong denomination invalidates the affidavit.",
            "⚠️ Ensure your name, address, and ID details match EXACTLY with your identity documents.",
            "⚠️ Check the purpose — an affidavit submitted for wrong purpose is invalid.",
            "⚠️ Verify the Notary's registration number and seal are present after attestation.",
        ],
        "next_steps": (
            "Get the affidavit attested by a registered Notary Public. "
            "Keep the original and get at least 3 certified copies. "
            "Submit within the deadline and get an acknowledgement receipt."
        ),
    },
    DocumentType.UNKNOWN: {
        "obligations": [
            "Read ALL clauses carefully before signing — once signed, you are legally bound.",
            "Fulfil any payment or performance obligations mentioned within stated timelines.",
            "Comply with all deadlines, notice periods, and conditions specified.",
            "Keep records of all communications, payments, and actions taken under this document.",
        ],
        "red_flags": [
            "⚠️ Look for one-sided penalty clauses that apply only to you and not the other party.",
            "⚠️ Check for automatic renewal clauses — these can bind you beyond your intended period.",
            "⚠️ Verify the identity, authority, and legitimacy of ALL parties signing.",
            "⚠️ Check if dispute resolution (arbitration/court) location is inconvenient for you.",
            "⚠️ Look for clauses allowing the other party to change terms unilaterally.",
        ],
        "next_steps": (
            "If unsure about ANY clause, consult a lawyer BEFORE signing — never after. "
            "Free legal aid is available at your nearest District Legal Services Authority (DLSA). "
            "Call NALSA helpline: 15100. Keep signed copies of all documents safely."
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
        amounts = re.findall(r"Rs\.?\s*[\d,]+(?:\s*(?:Lakhs?|Crores?|Thousands?))?|INR\s*[\d,]+", text)[:6]
        parties = re.findall(r"(?:between|by and between|party of the first part)[:\s]+([A-Z][A-Za-z\s]+?)(?:,|\band\b)", text)[:2]

        key_dates = (
            [f"📅 Date found: {d}" for d in dates] +
            [f"💰 Amount mentioned: {a}" for a in amounts]
        ) or ["Refer to dates and amounts mentioned in the document."]

        label = ClassifierService.get_doc_type_label(doc_type)
        party_text = f" Parties involved: {', '.join(parties)}." if parties else ""
        amount_text = f" Key amounts: {', '.join(amounts[:3])}." if amounts else ""

        summary = (
            f"This is a {label}. It is a legally binding document that sets out the rights and "
            f"obligations of all parties involved.{party_text}{amount_text} "
            f"Read all clauses carefully before signing."
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

        system_prompt = f"""You are VakilAI, India's most accurate AI legal document analyzer. 
You help ordinary Indian citizens understand complex legal documents in simple language.

Your task: Analyze the provided legal document and extract SPECIFIC, ACCURATE information from it.

CRITICAL RULES:
1. ALWAYS identify the EXACT document type from the actual content — do not guess
2. Extract REAL names, amounts, dates, and parties from the document — never use generic placeholders
3. Identify SPECIFIC risky or unfair clauses with exact clause references
4. Flag anything that is one-sided, excessive, or unusual compared to standard Indian legal practice
5. Use simple language that a Class 8 student can understand
6. Output language: {lang_name} (translate all values except JSON keys)
7. Respond ONLY with valid JSON — no markdown, no extra text

WHAT TO LOOK FOR (Red Flags):
- Unfair termination clauses (one party gets more notice than other)
- Excessive non-compete duration (>1 year is usually unenforceable in India)
- IP ownership of personal work/portfolio
- Payment withholding without specific reason
- Arbitration costs borne entirely by one party
- Liability caps that are extremely low
- Automatic renewal without notification
- Unilateral amendment rights (one party can change terms alone)
- Confidentiality periods beyond 3 years
- Penalties that are disproportionately high

OUTPUT FORMAT (strict JSON):
{{
  "document_type": "Exact type of document as identified from content",
  "summary": "3-4 sentence plain language summary including: what this document is, who the parties are, what it covers, and the most important thing to know",
  "obligations": [
    "Specific obligation 1 with exact details from document",
    "Specific obligation 2 with exact details from document", 
    "Specific obligation 3 with exact details from document",
    "Specific obligation 4 with exact details from document",
    "Specific obligation 5 with exact details from document"
  ],
  "key_dates": [
    "💰 Amount: [exact amount] — [what it is for]",
    "📅 Date: [exact date] — [what it is for]",
    "⏰ Timeline: [exact period] — [what it applies to]"
  ],
  "red_flags": [
    "🚨 CRITICAL: [specific dangerous clause with exact details]",
    "⚠️ WARNING: [specific unfair clause with exact details]",
    "⚠️ WARNING: [specific unusual clause with exact details]",
    "⚠️ CHECK: [something to verify before signing]",
    "⚠️ CHECK: [another thing to verify]"
  ],
  "next_steps": "Specific actionable advice for this exact document — what to do, what to negotiate, what to verify, in order of priority"
}}

IMPORTANT: 
- If you find a dangerous clause, quote the EXACT problematic text in your red flag
- Always mention specific amounts, dates, and names from the actual document
- Compare terms to standard Indian practice and flag deviations
- Never give generic advice — be specific to THIS document"""

        headers = {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json"
        }

        # Send full document text up to 8000 chars for better accuracy
        doc_text = text[:8000] if len(text) > 8000 else text

        payload = {
            "model": settings.groq_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Please analyze this legal document carefully and extract all specific details:\n\n"
                        f"Document Name: {document_name}\n"
                        f"Document Type (pre-classified): {label}\n\n"
                        f"--- DOCUMENT TEXT START ---\n{doc_text}\n--- DOCUMENT TEXT END ---\n\n"
                        f"Now provide your detailed analysis in {lang_name} language as JSON."
                    )
                }
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
            "top_p": 0.9,
        }

        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=45
            )

            if response.status_code != 200:
                logger.error(f"Groq API error {response.status_code}: {response.text}")
                return await cls._rule_based(text, doc_type, language, document_id, document_name)

            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip()

            # Clean markdown code blocks if present
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

            # Find JSON object in response
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                raw = raw[start:end]

            result_data = json.loads(raw)

            # Use AI-detected document type if available and different
            ai_doc_type = result_data.get("document_type", label)

            # Ensure we have minimum quality data — fall back to rule-based for missing fields
            summary = result_data.get("summary", "")
            obligations = result_data.get("obligations", [])
            key_dates = result_data.get("key_dates", [])
            red_flags = result_data.get("red_flags", [])
            next_steps = result_data.get("next_steps", "")

            # If AI returned poor quality (too short), enhance with rule-based
            tmpl = TEMPLATES.get(doc_type, TEMPLATES[DocumentType.UNKNOWN])
            if len(obligations) < 3:
                obligations = tmpl["obligations"]
            if len(red_flags) < 2:
                red_flags = tmpl["red_flags"]
            if not next_steps:
                next_steps = tmpl["next_steps"]

            # Enhance key_dates with regex extraction if AI missed amounts
            if len(key_dates) < 2:
                amounts = re.findall(r"Rs\.?\s*[\d,]+(?:\s*(?:Lakhs?|Crores?|Thousands?))?|INR\s*[\d,]+", text)[:4]
                dates = re.findall(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", text)[:3]
                key_dates += [f"💰 Amount: {a}" for a in amounts[:3]]
                key_dates += [f"📅 Date: {d}" for d in dates[:2]]

            return AnalysisResult(
                document_id=document_id,
                document_name=document_name,
                document_type=doc_type,
                language=language,
                summary=summary,
                obligations=obligations[:6],
                key_dates=key_dates[:8],
                red_flags=red_flags[:7],
                next_steps=next_steps,
                ai_powered=True,
                processed_at=datetime.utcnow(),
            )

        except json.JSONDecodeError as e:
            logger.error(f"Groq returned invalid JSON: {e} | raw: {raw[:300]}")
            return await cls._rule_based(text, doc_type, language, document_id, document_name)
        except Exception as e:
            logger.error(f"Groq API failed: {e}")
            return await cls._rule_based(text, doc_type, language, document_id, document_name)