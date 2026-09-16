# Importăm zipfile pentru a putea citi CSV-ul Companies House
# direct din arhiva ZIP.
import zipfile

# Importăm Path pentru căi către fișiere.
from pathlib import Path

# Importăm pandas pentru manipularea datelor.
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

# Obținem calea absolută către script.
SCRIPT_PATH = Path(__file__).resolve()

# Scriptul este în /src, deci mergem două niveluri în sus
# pentru a ajunge în rădăcina proiectului.
PROJECT_ROOT = SCRIPT_PATH.parent.parent


# Calea către snapshot-ul Companies House.
INPUT_ZIP = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "BasicCompanyDataAsOneFile-2026-09-01.zip"
)

# Calea către sample-ul generat de primul script.
SAMPLE_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "sample_companies.csv"
)

# Calea către raportul pe care îl vom genera.
OUTPUT_REPORT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "sample_validation.txt"
)


# ============================================================
# CHECK FILES
# ============================================================

# Verificăm dacă snapshot-ul Companies House există.
if not INPUT_ZIP.exists():
    raise FileNotFoundError(
        f"Companies House ZIP not found:\n{INPUT_ZIP}"
    )


# Verificăm dacă sample-ul există.
if not SAMPLE_FILE.exists():
    raise FileNotFoundError(
        f"Sample file not found:\n{SAMPLE_FILE}\n"
        f"Run 01_build_sample.py first."
    )


# ============================================================
# LOAD COMPANIES HOUSE DATA
# ============================================================

# Deschidem ZIP-ul.
with zipfile.ZipFile(INPUT_ZIP, "r") as zip_file:

    # Luăm lista fișierelor din ZIP.
    files_inside_zip = zip_file.namelist()

    # Păstrăm doar fișierele CSV.
    csv_files = [
        file_name
        for file_name in files_inside_zip
        if file_name.lower().endswith(".csv")
    ]

    # Dacă nu găsim CSV, oprim programul.
    if not csv_files:
        raise RuntimeError(
            "No CSV file found inside Companies House ZIP."
        )

    # Folosim primul CSV.
    csv_file_name = csv_files[0]

    # Îl deschidem direct din ZIP.
    with zip_file.open(csv_file_name) as csv_file:

        # Citim dataset-ul.
        #
        # dtype=str:
        # toate valorile rămân text.
        #
        # on_bad_lines="warn":
        # rândurile malformed sunt ignorate,
        # dar pandas afișează warning.
        population_df = pd.read_csv(
            csv_file,
            dtype=str,
            low_memory=False,
            on_bad_lines="warn"
        )


# Eliminăm eventualele spații din numele coloanelor.
population_df.columns = population_df.columns.str.strip()


# ============================================================
# RECREATE ELIGIBLE POPULATION
# ============================================================

# Construim același filtru folosit în primul script.
active_mask = (
    population_df["CompanyStatus"]
    .fillna("")
    .str.strip()
    .str.lower()
    == "active"
)

# Păstrăm doar companiile active.
active_df = population_df[active_mask].copy()


# Curățăm Accounts.AccountCategory.
accounts_category = (
    active_df["Accounts.AccountCategory"]
    .fillna("")
    .str.strip()
    .str.upper()
)

# Identificăm companiile explicit DORMANT.
dormant_mask = accounts_category == "DORMANT"

# Recreăm populația eligibilă.
eligible_df = active_df[~dormant_mask].copy()


# ============================================================
# LOAD SAMPLE
# ============================================================

# Citim sample-ul generat de scriptul 01.
sample_df = pd.read_csv(
    SAMPLE_FILE,
    dtype=str
)


# ============================================================
# HELPER: PERCENTAGE DISTRIBUTION
# ============================================================

# Această funcție calculează distribuția procentuală
# pentru o coloană.
def percentage_distribution(series):

    # Înlocuim valorile lipsă cu MISSING.
    clean_series = (
        series
        .fillna("MISSING")
        .replace("", "MISSING")
        .astype(str)
        .str.strip()
    )

    # Calculăm procentul fiecărei categorii.
    distribution = (
        clean_series
        .value_counts(normalize=True)
        .mul(100)
        .round(2)
    )

    # Returnăm rezultatul.
    return distribution


# ============================================================
# COMPANY CATEGORY
# ============================================================

# Distribuția company category în populația eligibilă.
population_company_category = percentage_distribution(
    eligible_df["CompanyCategory"]
)

# Distribuția company category în sample.
sample_company_category = percentage_distribution(
    sample_df["company_category"]
)


# ============================================================
# ACCOUNTS CATEGORY
# ============================================================

# Distribuția account categories în populație.
population_accounts = percentage_distribution(
    eligible_df["Accounts.AccountCategory"]
)

# Distribuția account categories în sample.
sample_accounts = percentage_distribution(
    sample_df["accounts_category"]
)


# ============================================================
# COMPANY AGE
# ============================================================

# Data snapshot-ului.
snapshot_date = pd.Timestamp("2026-09-01")


# Funcție care transformă incorporation date într-o categorie de vârstă.
def create_age_bucket(date_series):

    # Convertim textul în dată.
    #
    # dayfirst=True este necesar deoarece Companies House
    # folosește în mod obișnuit format DD/MM/YYYY.
    dates = pd.to_datetime(
        date_series,
        errors="coerce",
        dayfirst=True
    )

    # Calculăm aproximativ vârsta companiei în ani.
    ages = (
        snapshot_date - dates
    ).dt.days / 365.25

    # Funcție pentru clasificarea unei singure vârste.
    def classify_age(age):

        # Dacă nu avem o dată validă.
        if pd.isna(age):
            return "Unknown"

        # Mai puțin de un an.
        if age < 1:
            return "<1 year"

        # Între 1 și 3 ani.
        if age < 3:
            return "1-3 years"

        # Între 3 și 10 ani.
        if age < 10:
            return "3-10 years"

        # Între 10 și 20 ani.
        if age < 20:
            return "10-20 years"

        # 20 sau mai mulți ani.
        return "20+ years"

    # Aplicăm clasificarea.
    return ages.apply(classify_age)


# Creăm age bucket pentru populație.
eligible_df["age_bucket"] = create_age_bucket(
    eligible_df["IncorporationDate"]
)

# Creăm age bucket pentru sample.
sample_df["age_bucket"] = create_age_bucket(
    sample_df["incorporation_date"]
)


# Calculăm distribuțiile.
population_age = percentage_distribution(
    eligible_df["age_bucket"]
)

sample_age = percentage_distribution(
    sample_df["age_bucket"]
)


# ============================================================
# GEOGRAPHY
# ============================================================

# Companies House poate folosi valori ușor diferite
# pentru țările din registered address.
#
# Le normalizăm într-o formă simplă.
def normalize_country(series):

    # Curățăm textul.
    clean = (
        series
        .fillna("MISSING")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # Funcția transformă fiecare valoare într-o categorie standard.
    def classify_country(country):

        if country in ["ENGLAND", "ENGLAND & WALES"]:
            return "England"

        if country == "SCOTLAND":
            return "Scotland"

        if country == "WALES":
            return "Wales"

        if country in [
            "NORTHERN IRELAND",
            "N. IRELAND"
        ]:
            return "Northern Ireland"

        if country in [
            "",
            "MISSING",
            "NAN"
        ]:
            return "Unknown"

        return "Other"

    # Aplicăm funcția.
    return clean.apply(classify_country)


# Verificăm dacă coloana există în populație.
if "RegAddress.Country" in eligible_df.columns:

    # Normalizăm țările.
    eligible_df["country_group"] = normalize_country(
        eligible_df["RegAddress.Country"]
    )

    # Distribuția geografică în populație.
    population_country = percentage_distribution(
        eligible_df["country_group"]
    )

else:

    # Dacă nu există coloana, folosim Series gol.
    population_country = pd.Series(dtype=float)


# Verificăm dacă sample-ul are address_country.
if "address_country" in sample_df.columns:

    # Normalizăm.
    sample_df["country_group"] = normalize_country(
        sample_df["address_country"]
    )

    # Distribuție sample.
    sample_country = percentage_distribution(
        sample_df["country_group"]
    )

else:

    sample_country = pd.Series(dtype=float)


# ============================================================
# SIC SECTION
# ============================================================

# În dataset-ul Companies House,
# SIC-ul este de obicei stocat ca:
#
# 62020 - Information technology consultancy activities
#
# Ne interesează momentan primele două cifre.
def extract_sic_division(series):

    # Transformăm în text.
    clean = (
        series
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # Extragem primele două cifre consecutive.
    sic_division = clean.str.extract(
        r"^(\d{2})",
        expand=False
    )

    # Valorile lipsă devin Unknown.
    return sic_division.fillna("Unknown")


# Pentru populație folosim primul SIC.
eligible_df["sic_division"] = extract_sic_division(
    eligible_df["SICCode.SicText_1"]
)

# Pentru sample folosim primul SIC.
sample_df["sic_division"] = extract_sic_division(
    sample_df["sic_1"]
)


# Calculăm distribuția SIC.
population_sic = percentage_distribution(
    eligible_df["sic_division"]
)

sample_sic = percentage_distribution(
    sample_df["sic_division"]
)


# ============================================================
# HELPER: COMPARISON TABLE
# ============================================================

# Funcția combină două distribuții:
# population vs sample.
def create_comparison(
    population_distribution,
    sample_distribution
):

    # Construim DataFrame cu ambele distribuții.
    comparison = pd.concat(
        [
            population_distribution.rename(
                "population_percent"
            ),
            sample_distribution.rename(
                "sample_percent"
            )
        ],
        axis=1
    )

    # Valorile care nu apar într-una dintre distribuții devin 0.
    comparison = comparison.fillna(0)

    # Calculăm diferența absolută în puncte procentuale.
    comparison["difference_pp"] = (
        comparison["sample_percent"]
        - comparison["population_percent"]
    ).round(2)

    # Sortăm după procentul din populație.
    comparison = comparison.sort_values(
        "population_percent",
        ascending=False
    )

    return comparison


# Creăm comparațiile.
company_category_comparison = create_comparison(
    population_company_category,
    sample_company_category
)

accounts_comparison = create_comparison(
    population_accounts,
    sample_accounts
)

age_comparison = create_comparison(
    population_age,
    sample_age
)

country_comparison = create_comparison(
    population_country,
    sample_country
)

sic_comparison = create_comparison(
    population_sic,
    sample_sic
)


# ============================================================
# SAVE REPORT
# ============================================================

# Deschidem fișierul pentru raport.
with open(
    OUTPUT_REPORT,
    "w",
    encoding="utf-8"
) as report:

    # Titlu.
    report.write(
        "VAT Identifier Discovery - Sample Validation\n"
    )

    report.write(
        "============================================\n\n"
    )

    # Dimensiunea populației.
    report.write(
        f"Eligible population: {len(eligible_df):,}\n"
    )

    # Dimensiunea sample-ului.
    report.write(
        f"Sample size: {len(sample_df):,}\n\n"
    )

    # --------------------------------------------------------
    # COMPANY CATEGORY
    # --------------------------------------------------------

    report.write(
        "1. Company category\n"
    )

    report.write(
        "-------------------\n"
    )

    report.write(
        company_category_comparison.to_string()
    )

    report.write("\n\n")

    # --------------------------------------------------------
    # ACCOUNTS CATEGORY
    # --------------------------------------------------------

    report.write(
        "2. Accounts category\n"
    )

    report.write(
        "--------------------\n"
    )

    report.write(
        accounts_comparison.to_string()
    )

    report.write("\n\n")

    # --------------------------------------------------------
    # COMPANY AGE
    # --------------------------------------------------------

    report.write(
        "3. Company age\n"
    )

    report.write(
        "--------------\n"
    )

    report.write(
        age_comparison.to_string()
    )

    report.write("\n\n")

    # --------------------------------------------------------
    # GEOGRAPHY
    # --------------------------------------------------------

    report.write(
        "4. Geography\n"
    )

    report.write(
        "------------\n"
    )

    report.write(
        country_comparison.to_string()
    )

    report.write("\n\n")

    # --------------------------------------------------------
    # SIC
    # --------------------------------------------------------

    report.write(
        "5. SIC division - top 30\n"
    )

    report.write(
        "-----------------------\n"
    )

    report.write(
        sic_comparison.head(30).to_string()
    )

    report.write("\n")


# ============================================================
# TERMINAL OUTPUT
# ============================================================

# Afișăm separator.
print("=" * 70)

# Titlu.
print("SAMPLE VALIDATION")

print("=" * 70)

print()

# Dimensiuni.
print(
    f"Eligible population: {len(eligible_df):,}"
)

print(
    f"Sample size:         {len(sample_df):,}"
)

print()


# Company category.
print("COMPANY CATEGORY")
print(company_category_comparison.head(15))
print()


# Accounts.
print("ACCOUNTS CATEGORY")
print(accounts_comparison.head(15))
print()


# Age.
print("COMPANY AGE")
print(age_comparison)
print()


# Geography.
print("GEOGRAPHY")
print(country_comparison)
print()


# SIC.
print("TOP SIC DIVISIONS")
print(sic_comparison.head(20))
print()


# Raport.
print("Full validation report saved to:")
print(OUTPUT_REPORT)