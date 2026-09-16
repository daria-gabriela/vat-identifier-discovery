from pathlib import Path
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

OUTPUT_SUMMARY = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "candidate_audit_summary.csv"
)

OUTPUT_DETAIL = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "candidate_audit_detail.csv"
)


# ============================================================
# LOAD
# ============================================================

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f"Candidate file not found: {INPUT_FILE}"
    )

df = pd.read_csv(
    INPUT_FILE,
    dtype=str
)


print("=" * 70)
print("VAT CANDIDATE AUDIT")
print("=" * 70)

print(f"\nEvidence rows: {len(df)}")
print(
    "Companies with candidates:",
    df["sample_id"].nunique()
)
print(
    "Globally unique VAT candidates:",
    df["candidate_vat"].nunique()
)


# ============================================================
# NORMALISE BASIC FIELDS
# ============================================================

for column in [
    "candidate_vat",
    "company_number",
    "company_name",
    "source_domain",
    "source_type",
    "query_type",
    "entity_evidence",
    "evidence_text",
    "source_url"
]:
    if column in df.columns:
        df[column] = df[column].fillna("").astype(str)


# ============================================================
# NUMBER OF UNIQUE VATS PER COMPANY
# ============================================================

company_stats = (
    df
    .groupby(
        [
            "sample_id",
            "company_number",
            "company_name"
        ],
        dropna=False
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
)


company_stats = company_stats.sort_values(
    [
        "unique_vats",
        "evidence_rows"
    ],
    ascending=False
)


# ============================================================
# NUMBER OF SOURCES PER COMPANY + VAT
# ============================================================

vat_stats = (
    df
    .groupby(
        [
            "sample_id",
            "company_number",
            "company_name",
            "candidate_vat"
        ],
        dropna=False
    )
    .agg(
        evidence_rows=(
            "candidate_vat",
            "size"
        ),
        unique_domains=(
            "source_domain",
            "nunique"
        ),
        source_domains=(
            "source_domain",
            lambda x: " | ".join(
                sorted(
                    set(
                        value
                        for value in x
                        if value
                    )
                )
            )
        ),
        source_types=(
            "source_type",
            lambda x: " | ".join(
                sorted(
                    set(
                        value
                        for value in x
                        if value
                    )
                )
            )
        ),
        query_types=(
            "query_type",
            lambda x: " | ".join(
                sorted(
                    set(
                        value
                        for value in x
                        if value
                    )
                )
            )
        ),
        entity_evidence_types=(
            "entity_evidence",
            lambda x: " | ".join(
                sorted(
                    set(
                        value
                        for value in x
                        if value
                    )
                )
            )
        )
    )
    .reset_index()
)


# ============================================================
# SIMPLE PRE-HMRC CONFIDENCE
# ============================================================
#
# IMPORTANT:
# This is NOT a statement that the VAT is correct.
#
# It is only a way to prioritise manual/HMRC verification.
#
# HMRC remains the verification source.
# ============================================================

def assign_pre_hmrc_confidence(row):

    evidence = str(
        row["entity_evidence_types"]
    )

    domains = int(
        row["unique_domains"]
    )

    source_types = str(
        row["source_types"]
    )


    # Strong entity linkage + more than one source/domain.
    if (
        "COMPANY_NUMBER" in evidence
        and domains >= 2
    ):
        return "HIGH"


    # Company number on one source.
    if "COMPANY_NUMBER" in evidence:
        return "MEDIUM"


    # Company name only.
    if "COMPANY_NAME" in evidence:
        return "LOW"


    return "LOW"


vat_stats[
    "pre_hmrc_confidence"
] = vat_stats.apply(
    assign_pre_hmrc_confidence,
    axis=1
)


# ============================================================
# ADD NUMBER OF VATS FOR COMPANY
# ============================================================

vat_stats = vat_stats.merge(
    company_stats[
        [
            "sample_id",
            "unique_vats"
        ]
    ],
    on="sample_id",
    how="left",
    suffixes=(
        "",
        "_for_company"
    )
)


vat_stats = vat_stats.rename(
    columns={
        "unique_vats":
            "company_unique_vats"
    }
)


# ============================================================
# SUSPECT MULTIPLICITY
# ============================================================
#
# A company with many different VAT candidates deserves
# inspection before HMRC verification.
# ============================================================

vat_stats[
    "multiplicity_flag"
] = vat_stats[
    "company_unique_vats"
].apply(
    lambda value:
        "REVIEW"
        if int(value) >= 4
        else "NORMAL"
)


# ============================================================
# SORT
# ============================================================

vat_stats = vat_stats.sort_values(
    [
        "company_unique_vats",
        "unique_domains",
        "evidence_rows"
    ],
    ascending=[
        False,
        False,
        False
    ]
)


# ============================================================
# SAVE SUMMARY
# ============================================================

company_stats.to_csv(
    OUTPUT_SUMMARY,
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# SAVE DETAIL
# ============================================================

vat_stats.to_csv(
    OUTPUT_DETAIL,
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# TERMINAL REPORT
# ============================================================

print("\n" + "=" * 70)
print("UNIQUE VAT CANDIDATES PER COMPANY")
print("=" * 70)

print(
    company_stats[
        [
            "sample_id",
            "company_number",
            "company_name",
            "unique_vats",
            "evidence_rows",
            "unique_domains"
        ]
    ].to_string(
        index=False
    )
)


# ============================================================
# MULTIPLICITY DISTRIBUTION
# ============================================================

print("\n" + "=" * 70)
print("MULTIPLICITY DISTRIBUTION")
print("=" * 70)

distribution = (
    company_stats[
        "unique_vats"
    ]
    .value_counts()
    .sort_index()
)

for number_of_vats, number_of_companies in distribution.items():

    print(
        f"{number_of_vats} VAT candidate(s): "
        f"{number_of_companies} company/companies"
    )


# ============================================================
# SUSPICIOUS COMPANIES
# ============================================================

suspicious = company_stats[
    company_stats[
        "unique_vats"
    ] >= 4
]

print("\n" + "=" * 70)
print("COMPANIES REQUIRING MULTIPLICITY REVIEW")
print("=" * 70)

if suspicious.empty:

    print(
        "No company has 4 or more VAT candidates."
    )

else:

    print(
        suspicious[
            [
                "sample_id",
                "company_number",
                "company_name",
                "unique_vats",
                "evidence_rows",
                "unique_domains"
            ]
        ].to_string(
            index=False
        )
    )


# ============================================================
# PRE-HMRC CONFIDENCE
# ============================================================

print("\n" + "=" * 70)
print("PRE-HMRC CONFIDENCE DISTRIBUTION")
print("=" * 70)

print(
    vat_stats[
        "pre_hmrc_confidence"
    ]
    .value_counts()
    .to_string()
)


# ============================================================
# TOP CANDIDATES
# ============================================================

print("\n" + "=" * 70)
print("CANDIDATE DETAILS")
print("=" * 70)

print(
    vat_stats[
        [
            "sample_id",
            "company_name",
            "candidate_vat",
            "company_unique_vats",
            "unique_domains",
            "entity_evidence_types",
            "source_domains",
            "pre_hmrc_confidence",
            "multiplicity_flag"
        ]
    ].to_string(
        index=False
    )
)


# ============================================================
# OUTPUT
# ============================================================

print("\n" + "=" * 70)
print("AUDIT COMPLETE")
print("=" * 70)

print(
    f"\nCompany summary saved to:\n"
    f"{OUTPUT_SUMMARY}"
)

print(
    f"\nCandidate detail saved to:\n"
    f"{OUTPUT_DETAIL}"
)