from pathlib import Path
import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "hmrc_manual_verification.csv"
)


# ============================================================
# MANUAL HMRC VERIFICATION RESULTS
#
# Verification source:
# https://www.tax.service.gov.uk/check-vat-number/known
#
# These results were manually checked against HMRC's public
# production VAT checker.
#
# IMPORTANT:
# VALID VAT != correct company.
#
# final_status:
#
# VERIFIED_MATCH
#     VAT is registered and HMRC business name corresponds
#     to the target Companies House entity.
#
# VALID_WRONG_ENTITY
#     VAT exists, but HMRC says it belongs to another business.
#
# INVALID
#     HMRC says the VAT number does not match a UK
#     VAT-registered business.
#
# AMBIGUOUS
#     VAT exists but identity could not be linked confidently.
# ============================================================


rows = [

    {
        "company_number": "12498554",
        "company_name": "ALUQO LTD",
        "candidate_vat": "GB347020919",
        "hmrc_valid": True,
        "hmrc_name": "ALUQO LIMITED",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "08780811",
        "company_name": "FRESHBUILD LIMITED",
        "candidate_vat": "GB341306832",
        "hmrc_valid": True,
        "hmrc_name": "FRESHBUILD LIMITED",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "SC464934",
        "company_name": "ATLAS ENGINES LTD",
        "candidate_vat": "GB187610292",
        "hmrc_valid": True,
        "hmrc_name": "ATLAS ENGINES LTD",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "11406651",
        "company_name": "JUST DESIGNER BRANDS LIMITED",
        "candidate_vat": "GB117513828",
        "hmrc_valid": True,
        "hmrc_name": "JANAN LTD",
        "final_status": "VALID_WRONG_ENTITY",
    },

    {
        "company_number": "11406651",
        "company_name": "JUST DESIGNER BRANDS LIMITED",
        "candidate_vat": "GB324864588",
        "hmrc_valid": True,
        "hmrc_name": "CAFE JANAN LIMITED",
        "final_status": "VALID_WRONG_ENTITY",
    },

    {
        "company_number": "11406651",
        "company_name": "JUST DESIGNER BRANDS LIMITED",
        "candidate_vat": "GB325056719",
        "hmrc_valid": True,
        "hmrc_name": "JUST DESIGNER BRANDS LTD",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "04104009",
        "company_name": "ENGINEERING DIAMONDS LIMITED",
        "candidate_vat": "GB272431866",
        "hmrc_valid": True,
        "hmrc_name": "ENGINEERING DIAMONDS LIMITED",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "16650513",
        "company_name": "BYRECROFT LTD",
        "candidate_vat": "GB500664621",
        "hmrc_valid": True,
        "hmrc_name": "BYRECROFT LTD",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "05615719",
        "company_name": "ALDWYCH HOLDINGS LIMITED",
        "candidate_vat": "GB888219670",
        "hmrc_valid": True,
        "hmrc_name": "ANERGI INTERNATIONAL LTD",
        "final_status": "VALID_WRONG_ENTITY",
    },

    {
        "company_number": "06595711",
        "company_name": "D & R BUILDING LIMITED",
        "candidate_vat": "GB128383111",
        "hmrc_valid": True,
        "hmrc_name": "D & R BUILDING MAINTENANCE LTD",
        "final_status": "VALID_WRONG_ENTITY",
    },

    {
        "company_number": "SC450443",
        "company_name": "AITKEN PROFESSIONAL SERVICES LIMITED",
        "candidate_vat": "GB171135632",
        "hmrc_valid": True,
        "hmrc_name": "AITKEN PROFESSIONAL SERVICES LIMITED",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "12277319",
        "company_name": "AGP AUTOSERVICE LTD",
        "candidate_vat": "GB339851858",
        "hmrc_valid": True,
        "hmrc_name": "AGP AUTOSERVICE LTD",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "05212950",
        "company_name": "MATT COX LTD",
        "candidate_vat": "GB816091440",
        "hmrc_valid": False,
        "hmrc_name": "",
        "final_status": "INVALID",
    },

    {
        "company_number": "13883568",
        "company_name": "IVI FRESH LIMITED",
        "candidate_vat": "GB437807766",
        "hmrc_valid": True,
        "hmrc_name": "IVI FRESH LIMITED",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "10958121",
        "company_name": "GINASWORLDBOUTIQUE & TRAVEL LTD",
        "candidate_vat": "GB322291432",
        "hmrc_valid": True,
        "hmrc_name": "GINASWORLDBOUTIQUE & TRAVEL LTD",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "03954623",
        "company_name": "MADE REAL LTD",
        "candidate_vat": "GB107325051",
        "hmrc_valid": True,
        "hmrc_name": "ACCOUNTANCY ALLIANCE LTD",
        "final_status": "VALID_WRONG_ENTITY",
    },

    {
        "company_number": "03954623",
        "company_name": "MADE REAL LTD",
        "candidate_vat": "GB114357436",
        "hmrc_valid": True,
        "hmrc_name": "ARRAMPICA LTD",
        "final_status": "VALID_WRONG_ENTITY",
    },

    {
        "company_number": "03954623",
        "company_name": "MADE REAL LTD",
        "candidate_vat": "GB186460386",
        "hmrc_valid": True,
        "hmrc_name": "MADE REAL LTD",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "11403509",
        "company_name": "DEVON FIRE & SECURITY LTD",
        "candidate_vat": "GB324581311",
        "hmrc_valid": True,
        "hmrc_name": "DEVON FIRE & SECURITY LTD",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "06649176",
        "company_name": "PJK ENGINEERING LTD",
        "candidate_vat": "GB132842036",
        "hmrc_valid": True,
        "hmrc_name": "PJK ENGINEERING LTD",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "04442079",
        "company_name": "BIRCHWOOD CLADDING SYSTEMS LIMITED",
        "candidate_vat": "GB790297889",
        "hmrc_valid": True,
        "hmrc_name": "BIRCHWOOD BOARDING KENNELS & CATTERY LIMITED",
        "final_status": "VALID_WRONG_ENTITY",
    },

    {
        "company_number": "04442079",
        "company_name": "BIRCHWOOD CLADDING SYSTEMS LIMITED",
        "candidate_vat": "GB801699717",
        "hmrc_valid": True,
        "hmrc_name": "BIRCHWOOD CLADDING SYSTEMS LIMITED",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "SC248517",
        "company_name": "CRAIGHEAD & WOOLF LIMITED",
        "candidate_vat": "GB635008071",
        "hmrc_valid": True,
        "hmrc_name": "CRAIGHEAD & WOOLF LIMITED",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "13965119",
        "company_name": "BACKSTORY BOOKS LTD",
        "candidate_vat": "GB406068415",
        "hmrc_valid": True,
        "hmrc_name": "BACKSTORY BOOKS LIMITED",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "06521162",
        "company_name": "EARLY RISE SCAFFOLDING LIMITED",
        "candidate_vat": "GB704523268",
        "hmrc_valid": True,
        "hmrc_name": "ALGARNICK FARMS LIMITED",
        "final_status": "VALID_WRONG_ENTITY",
    },

    {
        "company_number": "06521162",
        "company_name": "EARLY RISE SCAFFOLDING LIMITED",
        "candidate_vat": "GB723384341",
        "hmrc_valid": True,
        "hmrc_name": "EARLY RISE SCAFFOLDING LIMITED",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "06521162",
        "company_name": "EARLY RISE SCAFFOLDING LIMITED",
        "candidate_vat": "GB898631659",
        "hmrc_valid": True,
        "hmrc_name": "AFFINA MARINE LTD",
        "final_status": "VALID_WRONG_ENTITY",
    },

    {
        "company_number": "03822445",
        "company_name": "WELLOW HEALTH AND FITNESS LIMITED",
        "candidate_vat": "GB744943016",
        "hmrc_valid": True,
        "hmrc_name": "WELLOW HEALTH AND FITNESS LIMITED",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "01393294",
        "company_name": "MALLONCREST LIMITED",
        "candidate_vat": "GB814233362",
        "hmrc_valid": True,
        "hmrc_name": "MALLONCREST LIMITED",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "10547971",
        "company_name": "M & A BRANDS LTD",
        "candidate_vat": "GB160418335",
        "hmrc_valid": True,
        "hmrc_name": "E1 PRINTING LIMITED",
        "final_status": "VALID_WRONG_ENTITY",
    },

    {
        "company_number": "10547971",
        "company_name": "M & A BRANDS LTD",
        "candidate_vat": "GB175765957",
        "hmrc_valid": True,
        "hmrc_name": "LASTMINUTEPRINT.COM LIMITED",
        "final_status": "VALID_WRONG_ENTITY",
    },

    {
        "company_number": "10547971",
        "company_name": "M & A BRANDS LTD",
        "candidate_vat": "GB360448307",
        "hmrc_valid": True,
        "hmrc_name": "M & A BRANDS LTD",
        "final_status": "VERIFIED_MATCH",
    },

    {
        "company_number": "SC524754",
        "company_name": "TR PLUMBING & HEATING LTD",
        "candidate_vat": "GB238984062",
        "hmrc_valid": True,
        "hmrc_name": "TR PLUMBING & HEATING LTD",
        "final_status": "VERIFIED_MATCH",
    },

]


# ============================================================
# ADD VERIFICATION METADATA
# ============================================================

for row in rows:

    row["verification_source"] = (
        "HMRC_PUBLIC_VAT_CHECKER"
    )

    row["verification_method"] = "MANUAL"

    row["verification_date"] = "2026-09-14"


# ============================================================
# SAVE
# ============================================================

df = pd.DataFrame(rows)

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)

df.to_csv(
    OUTPUT_FILE,
    index=False,
)

print("=" * 70)
print("MANUAL HMRC VERIFICATION SAVED")
print("=" * 70)

print()
print(f"Rows: {len(df)}")
print(
    f"Companies: "
    f"{df['company_number'].nunique()}"
)
print(
    f"VAT numbers: "
    f"{df['candidate_vat'].nunique()}"
)

print()
print("Status distribution:")
print(
    df["final_status"]
    .value_counts()
    .to_string()
)

print()
print("Saved to:")
print(OUTPUT_FILE)