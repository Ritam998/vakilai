import io
import re
from pathlib import Path
from typing import Tuple
from loguru import logger

try:
    import fitz
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image, ImageFilter, ImageEnhance
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


class PDFExtractionError(Exception):
    pass


class PDFService:
    MIN_TEXT_LENGTH = 50
    

    @classmethod
    async def extract_text(cls, file_bytes: bytes, filename: str) -> Tuple[str, str]:
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            return await cls._from_pdf(file_bytes, filename)
        elif ext in {".doc", ".docx"}:
            return await cls._extract_from_docx(file_bytes), "docx"
        else:
            return cls._mock_text(filename), "mock"

    @classmethod
    async def _from_pdf(cls, file_bytes: bytes, filename: str) -> Tuple[str, str]:
        if not PYMUPDF_AVAILABLE:
            return cls._mock_text(filename), "mock"
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            text = "\n\n".join(p.get_text("text") for p in doc).strip()
            doc.close()
            if len(text) >= cls.MIN_TEXT_LENGTH:
                return cls._clean(text), "pymupdf"
            return await cls._ocr_pdf(file_bytes)
        except Exception as e:
            raise PDFExtractionError(f"Could not read PDF: {str(e)}")

    @classmethod
    async def _ocr_pdf(cls, file_bytes: bytes) -> Tuple[str, str]:
        if not (PYMUPDF_AVAILABLE and TESSERACT_AVAILABLE):
            raise PDFExtractionError("OCR not available.")
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        texts = []
        for i in range(min(len(doc), 10)):
            pix = doc[i].get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            texts.append(pytesseract.image_to_string(cls._preprocess(img), lang="eng+hin"))
        doc.close()
        result = cls._clean("\n\n".join(texts))
        if len(result) < cls.MIN_TEXT_LENGTH:
            raise PDFExtractionError("Could not extract readable text.")
        return result, "tesseract"

    @classmethod
    async def _from_image(cls, file_bytes: bytes) -> Tuple[str, str]:
        if not TESSERACT_AVAILABLE:
            raise PDFExtractionError("Install pytesseract and Pillow.")
        img = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(cls._preprocess(img), lang="eng+hin")
        if len(text.strip()) < cls.MIN_TEXT_LENGTH:
            raise PDFExtractionError("Could not read text from image.")
        return cls._clean(text), "tesseract"

    @staticmethod
    def _preprocess(image):
        image = image.convert("L")
        image = image.filter(ImageFilter.SHARPEN)
        return ImageEnhance.Contrast(image).enhance(2.0)

    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return re.sub(r" {2,}", " ", text).strip()
    
    @classmethod
    async def _extract_from_docx(cls, file_bytes: bytes) -> str:
        import io
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
        if len(text) < cls.MIN_TEXT_LENGTH:
            raise PDFExtractionError("Could not extract text from Word document.")
        return cls._clean(text)

    @staticmethod
    def _mock_text(filename: str) -> str:
        return (
            "RENTAL AGREEMENT. "
            "This agreement is between the Lessor and the Lessee. "
            "Monthly rent Rs 12000. Security deposit Rs 36000. "
            "Notice period one month. Tenant must not sublet. "
            f"File: {filename}"
        )
    
