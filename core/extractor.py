import hashlib
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd
import pytesseract
from PIL import Image
from pypdf import PdfReader

PDF_DIR = Path("synthetic_data/pdfs")
OUT_CSV = Path("synthetic_data/extracted.csv")
RECORDS = Path("synthetic_data/records.csv")

DOC_KEYWORDS = {
    "affidavit": "AFFIDAVIT",
    "fire_noc": "FIRE SAFETY",
    "accreditation": "ACCREDITATION",
}
FIELD_MAP = {
    "institution name": "institution_name",
    "institution id": "institution_id",
    "certificate no": "certificate_no",
    "issued by": "issued_by",
    "issue date": "issue_date",
    "valid until": "valid_until",
    "sanctioned intake": "intake",
    "programme": "programme",
    "date": "signed_date",
}
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def ocr_pdf(path):
    doc = fitz.open(path)
    pix = doc[0].get_pixmap(dpi=200)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return pytesseract.image_to_string(img)


def detect_doc_type(title):
    upper = title.upper()
    for doc_type, keyword in DOC_KEYWORDS.items():
        if keyword in upper:
            return doc_type
    return "unknown"


def parse_fields(text):
    fields = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        if key in FIELD_MAP:
            fields[FIELD_MAP[key]] = value.strip()
    return fields


def clean_date(value):
    match = DATE_RE.search(value or "")
    return match.group(0) if match else None


def to_int(value):
    digits = re.sub(r"\D", "", value or "")
    return int(digits) if digits else None


def file_info(path):
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    meta = PdfReader(str(path)).metadata
    creator = meta.creator if meta and meta.creator else ""
    return sha, creator


def extract_document(path):
    text = ocr_pdf(path)
    fields = parse_fields(text)
    sha, creator = file_info(path)
    title = next((line for line in text.splitlines() if line.strip()), "")
    return {
        "file": path.name,
        "app_id": path.stem.split("_")[0],
        "true_doc_type": path.stem.split("_", 1)[1],
        "doc_type": detect_doc_type(title),
        "institution_name": fields.get("institution_name"),
        "institution_id": fields.get("institution_id"),
        "certificate_no": fields.get("certificate_no"),
        "issued_by": fields.get("issued_by"),
        "issue_date": clean_date(fields.get("issue_date")),
        "valid_until": clean_date(fields.get("valid_until")),
        "signed_date": clean_date(fields.get("signed_date")),
        "intake": to_int(fields.get("intake")),
        "creator": creator,
        "sha256": sha,
    }


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    pdfs = sorted(PDF_DIR.glob("*.pdf"))[:limit]
    rows = []
    for i, pdf in enumerate(pdfs, start=1):
        rows.append(extract_document(pdf))
        print(f"[{i}/{len(pdfs)}] {pdf.name}")

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)

    records = pd.read_csv(RECORDS)[["app_id", "institution_id"]]
    merged = df.merge(records, on="app_id", suffixes=("", "_true"))
    id_acc = (merged["institution_id"] == merged["institution_id_true"]).mean() * 100
    cls_acc = (df["doc_type"] == df["true_doc_type"]).mean() * 100

    print(f"\nDone. Saved {OUT_CSV}")
    print(f"Document classification accuracy: {cls_acc:.1f}%")
    print(f"Institution ID extraction accuracy: {id_acc:.1f}%")


if __name__ == "__main__":
    main()