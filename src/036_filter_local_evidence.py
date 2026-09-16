from pathlib import Path
import re
import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "vat_candidates.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "vat_candidates_filtered.csv"
)

OUTPUT_REJECTED = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "vat_candidates_rejected.csv"
)


# ============================================================
# HELPERS
# ============================================================

def normalize_company_name(name):
    """
    Normalize company name so that:
    - LTD / LIMITED / PLC / LLP do not affect matching
    - punctuation is ignored
    - comparison becomes more robust
    """

    if pd.isna(name):
        return ""

    name = str(name).upper()

    name = re.sub(
        r"\b(LIMITED|LTD|PLC|LLP)\b",
        " ",
        name
    )

    name = re.sub(
        r"[^A-Z0-9]+",
        " ",
        name
    )

    name = re.sub(
        r"\s+",
        " ",
        name
    )

    return name.strip()


def normalize_text(text):
    """
    Basic whitespace normalization.
    """

    if pd.isna(text):
        return ""

    text = str(text)

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def contains_company_number(
    evidence_text,
    company_number
):
    """
    Exact company-number lookup inside the LOCAL evidence window.
    """

    evidence_text = normalize_text(
        evidence_text
    ).upper()

    company_number = str(
        company_number
    ).strip().upper()

    if not company_number:
        return False

    return company_number in evidence_text


def contains_company_name(
    evidence_text,
    company_name
):
    """
    Checks normalized company name inside local evidence.
    """

    normalized_evidence = normalize_company_name(
        evidence_text
    )

    normalized_company = normalize_company_name(
        company_name
    )

    if len(normalized_company) < 4:
        return False

    return (
        normalized_company
        in normalized_evidence
    )


# ============================================================
# LOAD INPUT
# ============================================================

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f"Input file not found:\n{INPUT_FILE}"
    )

df = pd.read_csv(
    INPUT_FILE,
    dtype=str
)

print("=" * 70)
print("LOCAL EVIDENCE FILTER")
print("=" * 70)

print(
    f"\nOriginal evidence rows: {len(df)}"
)

print(
    "Original companies:",
    df["sample_id"].nunique()
)

print(
    "Original unique VATs:",
    df["candidate_vat"].nunique()
)


# ============================================================
# LOCAL EVIDENCE CHECK
# ============================================================

local_number_flags = []
local_name_flags = []
local_evidence_labels = []
keep_flags = []


for _, row in df.iterrows():

    evidence_text = row.get(
        "evidence_text",
        ""
    )

    company_number = row.get(
        "company_number",
        ""
    )

    company_name = row.get(
        "company_name",
        ""
    )

    number_found = contains_company_number(
        evidence_text,
        company_number
    )

    name_found = contains_company_name(
        evidence_text,
        company_name
    )

    # --------------------------------------------
    # Precision-first rule
    # --------------------------------------------
    #
    # We retain the candidate only if the LOCAL
    # evidence surrounding the VAT contains either
    # the Companies House number or company name.
    #
    # Company number is stronger than company name.
    # --------------------------------------------

    if number_found:
        evidence_label = "LOCAL_COMPANY_NUMBER"

    elif name_found:
        evidence_label = "LOCAL_COMPANY_NAME"

    else:
        evidence_label = "NO_LOCAL_ENTITY_LINK"


    keep = (
        number_found
        or name_found
    )

    local_number_flags.append(
        number_found
    )

    local_name_flags.append(
        name_found
    )

    local_evidence_labels.append(
        evidence_label
    )

    keep_flags.append(
        keep
    )


df[
    "local_company_number"
] = local_number_flags

df[
    "local_company_name"
] = local_name_flags

df[
    "local_entity_evidence"
] = local_evidence_labels

df[
    "keep_after_local_filter"
] = keep_flags


# ============================================================
# SPLIT KEPT / REJECTED
# ============================================================

kept_df = df[
    df["keep_after_local_filter"] == True
].copy()

rejected_df = df[
    df["keep_after_local_filter"] == False
].copy()


# ============================================================
# DEDUPLICATE KEPT CANDIDATES
# ============================================================
#
# Same VAT may appear more than once for same company.
# We preserve evidence rows in rejected/original files,
# but this output is intended as the HMRC candidate input.
# ============================================================

kept_df = (
    kept_df
    .sort_values(
        by=[
            "sample_id",
            "candidate_vat"
        ]
    )
)


# ============================================================
# SAVE
# ============================================================

kept_df.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig"
)

rejected_df.to_csv(
    OUTPUT_REJECTED,
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# SUMMARY AFTER FILTER
# ============================================================

print("\n" + "=" * 70)
print("AFTER LOCAL FILTER")
print("=" * 70)

print(
    f"\nEvidence rows kept:     {len(kept_df)}"
)

print(
    f"Evidence rows rejected: {len(rejected_df)}"
)

print(
    "Companies retained:",
    kept_df["sample_id"].nunique()
)

print(
    "Unique VATs retained:",
    kept_df["candidate_vat"].nunique()
)


# ============================================================
# LOCAL EVIDENCE DISTRIBUTION
# ============================================================

print("\nLocal evidence distribution:")

if not kept_df.empty:

    print(
        kept_df[
            "local_entity_evidence"
        ]
        .value_counts()
        .to_string()
    )

else:

    print("No candidates retained.")


# ============================================================
# VAT COUNT PER COMPANY
# ============================================================

if not kept_df.empty:

    company_summary = (
        kept_df
        .groupby(
            [
                "sample_id",
                "company_number",
                "company_name"
            ]
        )
        .agg(
            unique_vats=(
                "candidate_vat",
                "nunique"
            ),
            evidence_rows=(
                "candidate_vat",
                "size"
            ),
            unique_domains=(
                "source_domain",
                "nunique"
            )
        )
        .reset_index()
        .sort_values(
            [
                "unique_vats",
                "evidence_rows"
            ],
            ascending=False
        )
    )

    print("\n" + "=" * 70)
    print("VAT CANDIDATES PER COMPANY AFTER FILTER")
    print("=" * 70)

    print(
        company_summary.to_string(
            index=False
        )
    )


# ============================================================
# IMPORTANT REVIEW GROUP
# ============================================================

if not kept_df.empty:

    multiple_vat_companies = (
        company_summary[
            company_summary[
                "unique_vats"
            ] > 1
        ]
    )

    print("\n" + "=" * 70)
    print("COMPANIES STILL HAVING MULTIPLE VAT CANDIDATES")
    print("=" * 70)

    if multiple_vat_companies.empty:

        print(
            "None."
        )

    else:

        print(
            multiple_vat_companies.to_string(
                index=False
            )
        )


# ============================================================
# FINAL
# ============================================================

print("\n" + "=" * 70)
print("LOCAL FILTER COMPLETE")
print("=" * 70)

print(
    f"\nFiltered candidates:\n{OUTPUT_FILE}"
)

print(
    f"\nRejected evidence:\n{OUTPUT_REJECTED}"
)