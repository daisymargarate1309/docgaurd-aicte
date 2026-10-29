import difflib
from datetime import date
from pathlib import Path

import pandas as pd

APP_DATE = date(2026, 10, 28)
DATA = Path("synthetic_data")
EXPECTED_DOCS = ["affidavit", "fire_noc", "accreditation"]
VALIDITY_DOCS = ["fire_noc", "accreditation"]
SUSPICIOUS_CREATORS = ["photoshop", "canva", "gimp", "illustrator"]
NAME_THRESHOLD = 0.95


def make_flag(app_id, doc, kind, reason):
    return {"app_id": app_id, "doc_type": doc, "flag": kind, "reason": reason}


def similarity(a, b):
    return difflib.SequenceMatcher(None, str(a).lower().strip(), str(b).lower().strip()).ratio()


def run_rules(extracted, records):
    flags = []
    rec = records.set_index("app_id")

    hash_counts = extracted.groupby("sha256")["app_id"].nunique()
    dup_hashes = set(hash_counts[hash_counts > 1].index)

    for app_id in rec.index:
        docs = extracted[extracted["app_id"] == app_id]
        present = set(docs["doc_type"])

        for doc in EXPECTED_DOCS:
            if doc not in present:
                flags.append(make_flag(app_id, doc, "missing", f"{doc} not submitted"))

        for _, d in docs.iterrows():
            doc = d["doc_type"]

            if doc in VALIDITY_DOCS and pd.notna(d["valid_until"]):
                if date.fromisoformat(d["valid_until"]) < APP_DATE:
                    flags.append(make_flag(
                        app_id, doc, "expired",
                        f"Valid Until {d['valid_until']} is before application date {APP_DATE}"))

            if pd.notna(d["institution_name"]):
                true_name = rec.loc[app_id, "institution_name"]
                score = similarity(d["institution_name"], true_name)
                if score < NAME_THRESHOLD:
                    flags.append(make_flag(
                        app_id, doc, "name_mismatch",
                        f"Name '{d['institution_name']}' vs AICTE record '{true_name}' (similarity {score:.2f})"))

            if doc == "affidavit" and pd.notna(d["intake"]):
                approved = int(rec.loc[app_id, "approved_intake"])
                if int(d["intake"]) != approved:
                    flags.append(make_flag(
                        app_id, doc, "intake_mismatch",
                        f"Affidavit intake {int(d['intake'])} vs AICTE approved intake {approved}"))

            creator = str(d["creator"]).lower() if pd.notna(d["creator"]) else ""
            if any(word in creator for word in SUSPICIOUS_CREATORS):
                flags.append(make_flag(
                    app_id, doc, "metadata_edited", f"PDF created with '{d['creator']}'"))

            if d["sha256"] in dup_hashes:
                others = set(extracted[extracted["sha256"] == d["sha256"]]["app_id"]) - {app_id}
                flags.append(make_flag(
                    app_id, doc, "duplicate", f"Identical file also in {', '.join(sorted(others))}"))

    return flags


def evaluate(flags, truth):
    by_app = flags.groupby("app_id")["flag"].apply(set).to_dict()

    print("\nDetection by issue type:")
    for label in sorted(truth["label"].unique()):
        if label == "clean":
            continue
        apps = truth[truth["label"] == label]["app_id"]
        hit = sum(label in by_app.get(a, set()) for a in apps)
        print(f"  {label:<16} {hit}/{len(apps)} caught")

    bad = truth[truth["label"] != "clean"]["app_id"]
    clean = truth[truth["label"] == "clean"]["app_id"]
    caught = sum(a in by_app for a in bad)
    false_alarms = sum(a in by_app for a in clean)
    print(f"\nProblem applications caught: {caught}/{len(bad)}")
    print(f"Clean applications wrongly flagged: {false_alarms}/{len(clean)}")


def main():
    extracted = pd.read_csv(DATA / "extracted.csv")
    records = pd.read_csv(DATA / "records.csv")
    truth = pd.read_csv(DATA / "ground_truth.csv")

    columns = ["app_id", "doc_type", "flag", "reason"]
    flags = pd.DataFrame(run_rules(extracted, records), columns=columns)
    flags.to_csv(DATA / "flags.csv", index=False)

    print(f"Total flags raised: {len(flags)}")
    evaluate(flags, truth)
    print("\nSample flags:")
    print(flags.head(8).to_string(index=False))


if __name__ == "__main__":
    main()