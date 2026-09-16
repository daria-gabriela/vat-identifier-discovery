# Importăm modulul hashlib.
# Îl vom folosi la final pentru a calcula un SHA-256 hash al sample-ului.
# Hash-ul demonstrează că sample-ul a fost "înghețat" înainte de VAT discovery.
import hashlib

# Importăm modulul zipfile din Python.
# Ne permite să citim fișierul CSV direct din arhiva ZIP fără să-l dezarhivăm manual.
import zipfile

# Importăm Path.
# Path ne ajută să lucrăm mai curat și mai sigur cu căile către fișiere.
from pathlib import Path

# Importăm pandas.
# Pandas va fi folosit pentru citirea CSV-ului, filtrare, sampling și salvarea rezultatului.
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

# Numărul de companii pe care vrem să le avem în Proof of Concept.
SAMPLE_SIZE = 200

# Seed fix pentru random sampling.
# Folosirea aceluiași seed pe același dataset va produce același sample.
RANDOM_SEED = 20260914


# __file__ reprezintă locația acestui script.
# .resolve() transformă calea într-o cale absolută.
SCRIPT_PATH = Path(__file__).resolve()

# Scriptul este în folderul /src.
# .parent este /src.
# .parent.parent ajunge în rădăcina proiectului.
PROJECT_ROOT = SCRIPT_PATH.parent.parent


# Construim calea către fișierul ZIP Companies House.
INPUT_ZIP = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "BasicCompanyDataAsOneFile-2026-09-01.zip"
)

# Construim calea către folderul unde vom pune rezultatele procesate.
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

# Construim calea către fișierul final cu cele 200 de companii.
OUTPUT_SAMPLE = OUTPUT_DIR / "sample_companies.csv"

# Vom salva și statistici despre sampling.
OUTPUT_STATS = OUTPUT_DIR / "sampling_stats.txt"


# ============================================================
# CHECK INPUT FILE
# ============================================================

# Verificăm dacă fișierul ZIP există.
if not INPUT_ZIP.exists():

    # Dacă fișierul nu există, oprim programul și afișăm un mesaj clar.
    raise FileNotFoundError(
        f"\nNu am găsit fișierul Companies House:\n"
        f"{INPUT_ZIP}\n\n"
        f"Descarcă BasicCompanyDataAsOneFile-2026-09-01.zip "
        f"și pune-l în data/raw/."
    )


# Creăm folderul data/processed dacă nu există deja.
# parents=True permite crearea folderelor-părinte dacă lipsesc.
# exist_ok=True înseamnă că nu primim eroare dacă folderul există deja.
OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# OPEN ZIP
# ============================================================

# Deschidem arhiva ZIP în read mode.
with zipfile.ZipFile(INPUT_ZIP, "r") as zip_file:

    # Obținem lista tuturor fișierelor din interiorul arhivei.
    files_inside_zip = zip_file.namelist()

    # Filtrăm lista și păstrăm doar fișierele care se termină în .csv.
    csv_files = [
        file_name
        for file_name in files_inside_zip
        if file_name.lower().endswith(".csv")
    ]

    # Verificăm că am găsit cel puțin un CSV.
    if len(csv_files) == 0:

        # Dacă nu există CSV, ceva este greșit cu arhiva.
        raise RuntimeError(
            "Arhiva Companies House nu conține niciun fișier CSV."
        )

    # Fișierul 'AsOneFile' ar trebui să conțină un singur CSV.
    # Îl selectăm pe primul.
    csv_file_name = csv_files[0]

    # Afișăm ce fișier am găsit.
    print("CSV found inside ZIP:")
    print(csv_file_name)
    print()

    # Deschidem CSV-ul direct din arhivă.
    with zip_file.open(csv_file_name) as csv_file:

        # Citim CSV-ul Companies House.
        #
        # dtype=str:
        # păstrăm toate valorile ca text, foarte important pentru identificatori
        # precum CompanyNumber, care pot începe cu 0.
        #
        # low_memory=False:
        # evităm inferența diferită a tipurilor pe bucăți de fișier.
        #
        # on_bad_lines="warn":
        # Companies House bulk data poate conține ocazional rânduri malformed.
        # În loc să oprim tot procesul pentru un singur rând problematic,
        # pandas va ignora acel rând și va afișa un warning.
        #
        # NU folosim on_bad_lines="skip" deoarece vrem să vedem în terminal
        # exact ce rânduri au fost ignorate și să documentăm acest lucru.
        df = pd.read_csv(
            csv_file,
            dtype=str,
            low_memory=False,
            on_bad_lines="warn"
        )


# ============================================================
# CLEAN COLUMN NAMES
# ============================================================

# Unele versiuni istorice ale Companies House bulk CSV
# au avut spații în jurul unor nume de coloane.
#
# De exemplu:
# " CompanyNumber"
# în loc de:
# "CompanyNumber"
#
# .str.strip() elimină spațiile de la început și sfârșit.
df.columns = df.columns.str.strip()


# ============================================================
# BASIC INSPECTION
# ============================================================

# Numărul total de rânduri citite.
raw_count = len(df)

# Afișăm câte entități am încărcat.
print("Total rows loaded:")
print(f"{raw_count:,}")
print()


# Afișăm toate coloanele.
# Acest output este util și ca dovadă că am inspectat schema reală.
print("Columns found:")
for column in df.columns:
    print(f" - {column}")

print()


# ============================================================
# REQUIRED COLUMNS CHECK
# ============================================================

# Definim coloanele de care pipeline-ul nostru are nevoie obligatoriu.
required_columns = [
    "CompanyName",
    "CompanyNumber",
    "CompanyStatus",
    "CompanyCategory",
    "IncorporationDate",
    "Accounts.AccountCategory"
]

# Construim o listă cu eventualele coloane lipsă.
missing_columns = [
    column
    for column in required_columns
    if column not in df.columns
]

# Dacă lipsește ceva, oprim scriptul.
if missing_columns:

    # Mesajul ne spune exact ce nu a fost găsit.
    raise RuntimeError(
        "Lipsesc următoarele coloane necesare:\n"
        + "\n".join(missing_columns)
    )


# ============================================================
# FILTER 1: ACTIVE COMPANIES
# ============================================================

# CompanyStatus poate avea valori precum:
# Active
# Liquidation
# Administration
# etc.
#
# Pentru PoC vrem doar companii active.
#
# fillna("") înlocuiește eventualele valori lipsă cu string gol.
#
# str.strip() elimină spațiile.
#
# str.lower() face comparația case-insensitive.
active_mask = (
    df["CompanyStatus"]
    .fillna("")
    .str.strip()
    .str.lower()
    == "active"
)

# Aplicăm filtrul.
active_df = df[active_mask].copy()

# Numărăm companiile active.
active_count = len(active_df)

# Afișăm numărul.
print("Active companies:")
print(f"{active_count:,}")
print()


# ============================================================
# FILTER 2: EXPLICITLY DORMANT COMPANIES
# ============================================================

# Luăm coloana cu categoria ultimelor conturi.
accounts_category = (
    active_df["Accounts.AccountCategory"]
    .fillna("")
    .str.strip()
    .str.upper()
)

# Creăm un mask True pentru companiile cu accounts category DORMANT.
#
# Folosim equality, nu contains("DORMANT"),
# pentru a evita clasificări accidentale.
dormant_mask = accounts_category == "DORMANT"

# Numărăm companiile explicit dormant.
dormant_count = int(dormant_mask.sum())

# Eliminăm companiile explicit dormant.
eligible_df = active_df[~dormant_mask].copy()

# Calculăm dimensiunea populației eligibile.
eligible_count = len(eligible_df)

# Afișăm rezultatele.
print("Explicitly dormant companies excluded:")
print(f"{dormant_count:,}")
print()

print("Eligible population:")
print(f"{eligible_count:,}")
print()


# ============================================================
# VALIDATE SAMPLE SIZE
# ============================================================

# Ne asigurăm că populația eligibilă are cel puțin 200 de companii.
if eligible_count < SAMPLE_SIZE:

    # Dacă nu are, nu putem extrage 200 fără replacement.
    raise RuntimeError(
        f"Populația eligibilă are doar {eligible_count} rânduri, "
        f"dar SAMPLE_SIZE este {SAMPLE_SIZE}."
    )


# ============================================================
# RANDOM SAMPLE
# ============================================================

# sample() selectează aleator 200 de rânduri.
#
# n=SAMPLE_SIZE:
# numărul de observații.
#
# random_state=RANDOM_SEED:
# face rezultatul reproductibil.
#
# replace=False:
# aceeași companie nu poate fi selectată de două ori.
sample_df = eligible_df.sample(
    n=SAMPLE_SIZE,
    random_state=RANDOM_SEED,
    replace=False
).copy()


# ============================================================
# RESET SAMPLE INDEX
# ============================================================

# Pandas păstrează indexurile originale din fișier.
#
# Le resetăm astfel încât sample-ul nostru să aibă index 0...199.
sample_df = sample_df.reset_index(drop=True)


# ============================================================
# ADD SAMPLE ID
# ============================================================

# Adăugăm o coloană proprie numită sample_id.
#
# range(1, len(sample_df) + 1)
# produce valorile:
#
# 1, 2, 3, ..., 200
sample_df.insert(
    0,
    "sample_id",
    range(1, len(sample_df) + 1)
)


# ============================================================
# SELECT COLUMNS
# ============================================================

# Acestea sunt coloanele pe care vrem să le păstrăm în sample.
#
# Unele coloane sunt utile pentru matching ulterior,
# iar altele pentru analiza reprezentativității.
wanted_columns = [
    "sample_id",
    "CompanyName",
    "CompanyNumber",
    "CompanyCategory",
    "CompanyStatus",
    "CountryOfOrigin",
    "IncorporationDate",
    "RegAddress.CareOf",
    "RegAddress.POBox",
    "RegAddress.AddressLine1",
    "RegAddress.AddressLine2",
    "RegAddress.PostTown",
    "RegAddress.County",
    "RegAddress.Country",
    "RegAddress.PostCode",
    "Accounts.AccountCategory",
    "SICCode.SicText_1",
    "SICCode.SicText_2",
    "SICCode.SicText_3",
    "SICCode.SicText_4",
    "URI"
]

# Unele câmpuri pot lipsi în anumite versiuni.
#
# De aceea păstrăm doar coloanele care există efectiv.
existing_columns = [
    column
    for column in wanted_columns
    if column in sample_df.columns
]

# Limităm DataFrame-ul la coloanele selectate.
sample_df = sample_df[existing_columns]


# ============================================================
# RENAME COLUMNS
# ============================================================

# Pentru propriul nostru dataset preferăm nume mai simple și consistente.
rename_map = {
    "CompanyName": "company_name",
    "CompanyNumber": "company_number",
    "CompanyCategory": "company_category",
    "CompanyStatus": "company_status",
    "CountryOfOrigin": "country_of_origin",
    "IncorporationDate": "incorporation_date",

    "RegAddress.CareOf": "address_care_of",
    "RegAddress.POBox": "address_po_box",
    "RegAddress.AddressLine1": "address_line_1",
    "RegAddress.AddressLine2": "address_line_2",
    "RegAddress.PostTown": "post_town",
    "RegAddress.County": "county",
    "RegAddress.Country": "address_country",
    "RegAddress.PostCode": "postcode",

    "Accounts.AccountCategory": "accounts_category",

    "SICCode.SicText_1": "sic_1",
    "SICCode.SicText_2": "sic_2",
    "SICCode.SicText_3": "sic_3",
    "SICCode.SicText_4": "sic_4",

    "URI": "companies_house_uri"
}

# Aplicăm redenumirea.
sample_df = sample_df.rename(
    columns=rename_map
)


# ============================================================
# ADD EMPTY COLUMNS FOR LATER PIPELINE STEPS
# ============================================================

# Aceste coloane nu au încă valori.
#
# Le creăm acum pentru a avea de la început schema finală.
sample_df["website_found"] = ""
sample_df["website_url"] = ""

sample_df["vat_candidate"] = ""
sample_df["vat_source"] = ""
sample_df["vat_source_url"] = ""

sample_df["hmrc_checked"] = ""
sample_df["hmrc_valid"] = ""
sample_df["hmrc_registered_name"] = ""
sample_df["hmrc_registered_address"] = ""

sample_df["name_match"] = ""
sample_df["address_match"] = ""
sample_df["entity_match"] = ""

sample_df["final_status"] = ""
sample_df["notes"] = ""


# ============================================================
# SAVE SAMPLE
# ============================================================

# Salvăm sample-ul în format CSV.
#
# index=False:
# nu salvăm indexul intern pandas.
#
# encoding="utf-8-sig":
# face fișierul compatibil și cu Excel fără probleme de encoding.
sample_df.to_csv(
    OUTPUT_SAMPLE,
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# SHA-256 HASH
# ============================================================

# Deschidem sample-ul în mod binary.
with open(OUTPUT_SAMPLE, "rb") as file:

    # Citim conținutul complet al fișierului.
    file_bytes = file.read()

# Calculăm SHA-256.
sample_hash = hashlib.sha256(file_bytes).hexdigest()


# ============================================================
# SAMPLE DESCRIPTIVE STATISTICS
# ============================================================

# Calculăm distribuția după company category.
company_category_distribution = (
    sample_df["company_category"]
    .fillna("MISSING")
    .value_counts()
)

# Calculăm distribuția după accounts category.
accounts_distribution = (
    sample_df["accounts_category"]
    .fillna("MISSING")
    .value_counts()
)

# Dacă avem address_country, calculăm distribuția geografică.
if "address_country" in sample_df.columns:

    country_distribution = (
        sample_df["address_country"]
        .fillna("MISSING")
        .value_counts()
    )

else:

    # Dacă nu există coloana, folosim o serie goală.
    country_distribution = pd.Series(dtype=int)


# ============================================================
# SAVE SAMPLING STATISTICS
# ============================================================

# Deschidem fișierul text unde vom salva statisticile.
with open(
    OUTPUT_STATS,
    "w",
    encoding="utf-8"
) as stats_file:

    # Titlu.
    stats_file.write(
        "VAT Identifier Discovery - Sampling Statistics\n"
    )

    stats_file.write(
        "==============================================\n\n"
    )

    # Snapshot folosit.
    stats_file.write(
        "Companies House snapshot: 2026-09-01\n"
    )

    # Seed.
    stats_file.write(
        f"Random seed: {RANDOM_SEED}\n"
    )

    # Dimensiunea sample-ului.
    stats_file.write(
        f"Sample size: {SAMPLE_SIZE}\n\n"
    )

    # Numărul brut de rânduri.
    stats_file.write(
        f"Rows loaded: {raw_count:,}\n"
    )

    # Numărul activ.
    stats_file.write(
        f"Active rows: {active_count:,}\n"
    )

    # Numărul dormant exclus.
    stats_file.write(
        f"Explicit dormant excluded: {dormant_count:,}\n"
    )

    # Populația eligibilă.
    stats_file.write(
        f"Eligible population: {eligible_count:,}\n\n"
    )

    # Hash.
    stats_file.write(
        f"Sample SHA-256: {sample_hash}\n\n"
    )

    # Company category.
    stats_file.write(
        "Company category distribution\n"
    )

    stats_file.write(
        "-----------------------------\n"
    )

    stats_file.write(
        company_category_distribution.to_string()
    )

    stats_file.write("\n\n")

    # Accounts category.
    stats_file.write(
        "Accounts category distribution\n"
    )

    stats_file.write(
        "------------------------------\n"
    )

    stats_file.write(
        accounts_distribution.to_string()
    )

    stats_file.write("\n\n")

    # Geography.
    stats_file.write(
        "Registered address country distribution\n"
    )

    stats_file.write(
        "---------------------------------------\n"
    )

    stats_file.write(
        country_distribution.to_string()
    )

    stats_file.write("\n")


# ============================================================
# FINAL OUTPUT
# ============================================================

# Afișăm un sumar în terminal.
print("=" * 60)

print("SAMPLING COMPLETE")

print("=" * 60)

print()

print(f"Rows loaded:              {raw_count:,}")
print(f"Active companies:         {active_count:,}")
print(f"Dormant excluded:         {dormant_count:,}")
print(f"Eligible population:      {eligible_count:,}")
print(f"Sample size:              {len(sample_df):,}")

print()

print("Sample saved to:")
print(OUTPUT_SAMPLE)

print()

print("Statistics saved to:")
print(OUTPUT_STATS)

print()

print("Sample SHA-256:")
print(sample_hash)

print()

print("First 10 sampled companies:")

print(
    sample_df[
        [
            "sample_id",
            "company_number",
            "company_name"
        ]
    ].head(10).to_string(index=False)
)