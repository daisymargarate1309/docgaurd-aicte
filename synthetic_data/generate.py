import csv
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

from faker import Faker
from fpdf import FPDF

random.seed(42)
Faker.seed(42)
fake = Faker("en_IN")

OUT = Path("synthetic_data")
PDF_DIR = OUT / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)

APP_DATE = date(2026, 10, 28)
DOC_TYPES = ["affidavit", "fire_noc", "accreditation"]
TITLES = {
    "affidavit": "AFFIDAVIT / UNDERTAKING",
    "fire_noc": "FIRE SAFETY NO OBJECTION CERTIFICATE",
    "accreditation": "ACCREDITATION CERTIFICATE",
}
ISSUERS = {
    "fire_noc": "State Fire Services Department",
    "accreditation": "National Board of Accreditation",
}


def make_pdf(path, title, fields, creator="Microsoft Word"):
    pdf = FPDF()
    pdf.set_creator(creator)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 14, title, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(8)
    pdf.set_font("Helvetica", size=14)
    for key, value in fields:
        pdf.multi_cell(0, 10, f"{key}: {value}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    pdf.output(str(path))


def build_doc(app_id, doc, inst_id, name, programme, intake, valid_until, creator):
    issue_date = valid_until - timedelta(days=1095)
    if doc == "affidavit":
        sign_date = APP_DATE - timedelta(days=random.randint(1, 20))
        fields = [
            ("Institution Name", name),
            ("Institution ID", inst_id),
            ("Programme", programme),
            ("Sanctioned Intake", intake),
            ("Date", sign_date.isoformat()),
        ]
    else:
        fields = [
            ("Institution Name", name),
            ("Institution ID", inst_id),
            ("Certificate No", f"{doc[:3].upper()}-{random.randint(100000, 999999)}"),
            ("Issued By", ISSUERS[doc]),
            ("Issue Date", issue_date.isoformat()),
            ("Valid Until", valid_until.isoformat()),
        ]
    path = PDF_DIR / f"{app_id}_{doc}.pdf"
    make_pdf(path, TITLES[doc], fields, creator)
    return path


def main():
    labels = (
        ["clean"] * 20 + ["expired"] * 5 + ["missing"] * 4 + ["name_mismatch"] * 4
        + ["intake_mismatch"] * 3 + ["duplicate"] * 2 + ["metadata_edited"] * 2
    )
    random.shuffle(labels)

    records, truth, made = [], [], {}
    for i, label in enumerate(labels, start=1):
        app_id = f"APP{i:03d}"
        inst_id = f"1-{random.randint(1000000, 9999999)}"
        name = f"{fake.last_name()} Institute of Technology"
        intake = random.choice([60, 120, 180, 240])
        programme = "B.Tech Computer Science"
        records.append([app_id, inst_id, name, fake.city(), programme, intake])

        if label == "expired":
            target = random.choice(["fire_noc", "accreditation"])
        elif label == "intake_mismatch":
            target = "affidavit"
        elif label == "clean":
            target = ""
        else:
            target = random.choice(DOC_TYPES)
        truth.append([app_id, label, target])

        for doc in DOC_TYPES:
            bad = (doc == target)
            if bad and label == "missing":
                continue
            doc_name, doc_intake, creator = name, intake, "Microsoft Word"
            valid_until = APP_DATE + timedelta(days=random.randint(120, 1000))
            if bad and label == "expired":
                valid_until = APP_DATE - timedelta(days=random.randint(10, 300))
            if bad and label == "name_mismatch":
                doc_name = name.replace("Institute of Technology", "Institute of Engineering")
            if bad and label == "intake_mismatch":
                doc_intake = intake + 60
            if bad and label == "metadata_edited":
                creator = "Adobe Photoshop 25.0"
            made[(app_id, doc)] = build_doc(
                app_id, doc, inst_id, doc_name, programme, doc_intake, valid_until, creator
            )

    # duplicates: copy another application's clean file over this one
    clean_apps = [t[0] for t in truth if t[1] == "clean"]
    for app_id, label, target in truth:
        if label == "duplicate":
            src = made[(random.choice(clean_apps), target)]
            shutil.copy(src, made[(app_id, target)])

    with open(OUT / "records.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["app_id", "institution_id", "institution_name", "city", "programme", "approved_intake"])
        w.writerows(records)
    with open(OUT / "ground_truth.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["app_id", "label", "target_doc"])
        w.writerows(truth)

    print(f"Done: {len(records)} applications, {len(list(PDF_DIR.glob('*.pdf')))} PDFs")


if __name__ == "__main__":
    main()