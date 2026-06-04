from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from enum import Enum
from datetime import datetime


class SupportedLanguage(str, Enum):
    ENGLISH = "english"
    HINDI = "hindi"
    BENGALI = "bengali"
    TAMIL = "tamil"
    TELUGU = "telugu"
    MARATHI = "marathi"
    GUJARATI = "gujarati"
    KANNADA = "kannada"
    MALAYALAM = "malayalam"
    ODIA = "odia"
    PUNJABI = "punjabi"


class DocumentType(str, Enum):
    RENT_AGREEMENT = "rent_agreement"
    FIR = "fir"
    PROPERTY_DEED = "property_deed"
    COURT_NOTICE = "court_notice"
    LOAN_AGREEMENT = "loan_agreement"
    EMPLOYMENT = "employment_contract"
    AFFIDAVIT = "affidavit"
    UNKNOWN = "unknown"


class SignupRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str]
    plan: str = "free"
    docs_used: int = 0
    docs_limit: int = 3
    created_at: datetime

    class Config:
        from_attributes = True


class AnalysisResult(BaseModel):
    document_id: str
    document_name: str
    document_type: DocumentType
    language: SupportedLanguage
    summary: str
    obligations: List[str]
    key_dates: List[str]
    red_flags: List[str]
    next_steps: str
    disclaimer: str = (
        "This explanation is for informational purposes only and does not "
        "constitute legal advice. Consult a qualified lawyer before taking legal action."
    )
    ai_powered: bool = False
    processed_at: datetime


class DocumentHistoryItem(BaseModel):
    document_id: str
    document_name: str
    document_type: DocumentType
    language: SupportedLanguage
    processed_at: datetime


class DocumentHistoryResponse(BaseModel):
    items: List[DocumentHistoryItem]
    total: int


class UsageResponse(BaseModel):
    plan: str
    docs_used: int
    docs_limit: int
    resets_on: str


class MessageResponse(BaseModel):
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
