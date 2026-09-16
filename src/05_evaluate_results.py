from pathlib import Path
import json

import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROCESSED_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
)

VERIFICATION_FILE = (
    PROCESSED_DIR
    / "hmrc_manual_verification.csv"
)

SAMPLE_FILE = (
    PROCESSED_DIR
    / "sample_companies.csv"
)

METRICS_JSON = (
    PROCESSED_DIR
    / "evaluation_metrics.json"
)

VERIFIED_DATASET = (
    PROCESSED_DIR
    / "verified_company_vat.csv"
)


# ============================================================
# LOAD DATA
# ============================================================

if not VERIFICATION_FILE.exists():

    raise FileNotFoundError(
        f"Missing verification file:\n"
        f"{VERIFICATION_FILE}\n\n"
        "Run 041_save_manual_hmrc.py first."
    )


verification = pd.read_csv(
    VERIFICATION_FILE,
    dtype=str,
).fillna("")


# ============================================================
# SAMPLE SIZE
# ============================================================

if SAMPLE_FILE.exists():

    sample = pd.read_csv(
        SAMPLE_FILE,
        dtype=str,
    )

    sample_size = len(sample)

else:

    # Frozen sample size used by this PoC.
    sample_size = 200


# ============================================================
# BASIC COUNTS
# ============================================================

candidate_pairs = len(
    verification
)

unique_candidate_vats = (
    verification[
        "candidate_vat"
    ]
    .nunique()
)

candidate_companies = (
    verification[
        "company_number"
    ]
    .nunique()
)


# ============================================================
# STATUS COUNTS
# ============================================================

verified = verification[
    verification[
        "final_status"
    ]
    == "VERIFIED_MATCH"
].copy()


wrong_entity = verification[
    verification[
        "final_status"
    ]
    == "VALID_WRONG_ENTITY"
].copy()


invalid = verification[
    verification[
        "final_status"
    ]
    == "INVALID"
].copy()


ambiguous = verification[
    verification[
        "final_status"
    ]
    == "AMBIGUOUS"
].copy()


verified_candidates = len(
    verified
)

wrong_entity_candidates = len(
    wrong_entity
)

invalid_candidates = len(
    invalid
)

ambiguous_candidates = len(
    ambiguous
)


# ============================================================
# HMRC VAT VALIDITY
#
# This deliberately differs from entity correctness.
#
# Example:
# a VAT can be VALID according to HMRC but belong to
# another company.
# ============================================================

valid_vat_candidates = int(
    (
        verification[
            "hmrc_valid"
        ]
        .str.lower()
        == "true"
    ).sum()
)


vat_validity_rate = (
    valid_vat_candidates
    / candidate_pairs
    if candidate_pairs
    else 0
)


# ============================================================
# VERIFIED COMPANIES
# ============================================================

verified_companies = (
    verified[
        "company_number"
    ]
    .nunique()
)


# ============================================================
# CANDIDATE PRECISION
#
# Of all web-discovered VAT candidates that were checked,
# how many actually belonged to the intended company?
# ============================================================

candidate_precision = (
    verified_candidates
    / candidate_pairs
    if candidate_pairs
    else 0
)


# ============================================================
# CANDIDATE FALSE-POSITIVE PROPORTION
#
# False positives are:
#
# - a valid VAT belonging to the wrong company
# - an invalid VAT candidate
#
# We call this "candidate false-positive rate" in the PoC.
#
# Strict statistical FPR would require a known set of true
# negatives, which is unavailable here.
# ============================================================

false_positive_candidates = (
    wrong_entity_candidates
    + invalid_candidates
)

candidate_false_positive_rate = (
    false_positive_candidates
    / candidate_pairs
    if candidate_pairs
    else 0
)


# ============================================================
# VERIFIED SAMPLE COVERAGE
#
# This is NOT recall.
#
# We do not know how many of the remaining companies are
# actually VAT registered.
# ============================================================

verified_sample_coverage = (
    verified_companies
    / sample_size
    if sample_size
    else 0
)


# ============================================================
# RAW DISCOVERY COVERAGE
#
# Percentage of the 200-company sample for which Step 3
# produced at least one surviving VAT candidate.
# ============================================================

raw_candidate_company_coverage = (
    candidate_companies
    / sample_size
    if sample_size
    else 0
)


# ============================================================
# SUCCESS AMONG COMPANIES WITH CANDIDATES
# ============================================================

candidate_company_success_rate = (
    verified_companies
    / candidate_companies
    if candidate_companies
    else 0
)


# ============================================================
# IMPORTANT ERROR TYPE:
# VAT VALID, BUT WRONG COMPANY
# ============================================================

wrong_entity_among_valid = (
    wrong_entity_candidates
    / valid_vat_candidates
    if valid_vat_candidates
    else 0
)


# ============================================================
# OUTPUT FINAL VERIFIED DATASET
# ============================================================

verified_output = verified[
    [
        "company_number",
        "company_name",
        "candidate_vat",
        "hmrc_name",
        "verification_source",
        "verification_method",
        "verification_date",
    ]
].copy()


verified_output = verified_output.rename(
    columns={
        "candidate_vat": "vat_number",
        "hmrc_name": "hmrc_registered_name",
    }
)


verified_output.to_csv(
    VERIFIED_DATASET,
    index=False,
)


# ============================================================
# METRICS
# ============================================================

metrics = {

    "sample_size": int(
        sample_size
    ),

    "candidate_companies": int(
        candidate_companies
    ),

    "candidate_pairs_checked": int(
        candidate_pairs
    ),

    "unique_candidate_vats": int(
        unique_candidate_vats
    ),

    "hmrc_valid_vats": int(
        valid_vat_candidates
    ),

    "verified_matches": int(
        verified_candidates
    ),

    "valid_wrong_entity": int(
        wrong_entity_candidates
    ),

    "invalid_candidates": int(
        invalid_candidates
    ),

    "ambiguous_candidates": int(
        ambiguous_candidates
    ),

    "verified_companies": int(
        verified_companies
    ),

    "vat_validity_rate": (
        vat_validity_rate
    ),

    "candidate_precision": (
        candidate_precision
    ),

    "candidate_false_positive_rate": (
        candidate_false_positive_rate
    ),

    "raw_candidate_company_coverage": (
        raw_candidate_company_coverage
    ),

    "verified_sample_coverage": (
        verified_sample_coverage
    ),

    "candidate_company_success_rate": (
        candidate_company_success_rate
    ),

    "wrong_entity_among_valid_vats": (
        wrong_entity_among_valid
    ),

}


with open(
    METRICS_JSON,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        metrics,
        file,
        indent=2,
    )


# ============================================================
# PRINT REPORT
# ============================================================

print("=" * 72)
print("VAT IDENTIFIER DISCOVERY - FINAL POC EVALUATION")
print("=" * 72)

print()

print("SAMPLE")
print("-" * 72)

print(
    f"Companies in frozen sample:          "
    f"{sample_size}"
)

print(
    f"Companies with VAT candidate:        "
    f"{candidate_companies}"
)

print(
    f"Raw candidate company coverage:      "
    f"{raw_candidate_company_coverage:.2%}"
)

print()

print("HMRC VERIFICATION")
print("-" * 72)

print(
    f"Candidate VATs checked:              "
    f"{candidate_pairs}"
)

print(
    f"HMRC-valid VAT numbers:              "
    f"{valid_vat_candidates}"
)

print(
    f"HMRC VAT validity rate:              "
    f"{vat_validity_rate:.2%}"
)

print()

print(
    f"VERIFIED_MATCH:                      "
    f"{verified_candidates}"
)

print(
    f"VALID_WRONG_ENTITY:                  "
    f"{wrong_entity_candidates}"
)

print(
    f"INVALID:                             "
    f"{invalid_candidates}"
)

print(
    f"AMBIGUOUS:                           "
    f"{ambiguous_candidates}"
)

print()

print("QUALITY")
print("-" * 72)

print(
    f"Candidate precision:                 "
    f"{candidate_precision:.2%}"
)

print(
    f"Candidate false-positive rate:       "
    f"{candidate_false_positive_rate:.2%}"
)

print(
    f"Wrong entity among valid VATs:       "
    f"{wrong_entity_among_valid:.2%}"
)

print()

print("COVERAGE")
print("-" * 72)

print(
    f"Verified companies:                  "
    f"{verified_companies}"
)

print(
    f"Verified sample coverage:            "
    f"{verified_sample_coverage:.2%}"
)

print(
    f"Verified / candidate-company rate:   "
    f"{candidate_company_success_rate:.2%}"
)

print()

print("IMPORTANT")
print("-" * 72)

print(
    "Verified sample coverage is NOT recall."
)

print(
    "The true number of VAT-registered companies in the sample "
    "is unknown because no complete public ground-truth dataset exists."
)

print()

print(
    "Candidate false-positive rate is defined here as:"
)

print(
    "(VALID_WRONG_ENTITY + INVALID) / all checked candidates."
)

print(
    "A strict statistical FPR cannot be calculated without "
    "a known set of true negatives."
)

print()

print("=" * 72)

print(
    f"Verified dataset saved to:\n"
    f"{VERIFIED_DATASET}"
)

print()

print(
    f"Metrics saved to:\n"
    f"{METRICS_JSON}"
)