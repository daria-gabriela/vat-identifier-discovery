# ============================================================
# IMPORTS
# ============================================================

import re
import time
import random

from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

from bs4 import BeautifulSoup
from pypdf import PdfReader
from ddgs import DDGS


# ============================================================
# CONFIGURATION
# ============================================================

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent

INPUT_SAMPLE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "sample_companies.csv"
)

OUTPUT_CANDIDATES = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "vat_candidates.csv"
)

OUTPUT_LOG = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "discovery_log.csv"
)

MAX_SEARCH_RESULTS = 5
HTTP_TIMEOUT = 15
MAX_CONTENT_SIZE = 5 * 1024 * 1024

USER_AGENT = (
    "VATIdentifierResearchPoC/1.0 "
    "(academic/recruitment research; low-rate requests)"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,"
        "application/xhtml+xml,"
        "application/pdf;q=0.9,"
        "*/*;q=0.8"
    )
}


# ============================================================
# VAT REGEX
# ============================================================

GB_VAT_PATTERN = re.compile(
    r"\bGB[\s.\-:]*(\d(?:[\s.\-]?\d){8})\b",
    flags=re.IGNORECASE
)

NINE_DIGIT_PATTERN = re.compile(
    r"(?<!\d)(\d(?:[\s.\-]?\d){8})(?!\d)"
)

VAT_CONTEXT_PATTERN = re.compile(
    r"\bVAT\b"
    r"|VAT\s*(?:NO|NUMBER|REG|REGISTRATION)",
    flags=re.IGNORECASE
)


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_vat(raw_vat):

    digits = re.sub(
        r"\D",
        "",
        raw_vat
    )

    if len(digits) != 9:
        return None

    return digits


def normalize_text(text):

    if text is None:
        return ""

    text = str(text)

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def normalize_company_name(name):

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


# ============================================================
# VAT EXTRACTION
# ============================================================

def extract_vat_candidates(text):

    text = normalize_text(text)

    candidates = []
    seen = set()

    # --------------------------------------------------------
    # 1. VAT WITH GB PREFIX
    # --------------------------------------------------------

    for match in GB_VAT_PATTERN.finditer(text):

        raw_number = match.group(1)

        vat = normalize_vat(
            raw_number
        )

        if vat is None:
            continue

        context_start = max(
            0,
            match.start() - 120
        )

        context_end = min(
            len(text),
            match.end() + 120
        )

        evidence = text[
            context_start:context_end
        ]

        if vat not in seen:

            seen.add(vat)

            candidates.append(
                {
                    "vat": vat,
                    "raw_match": match.group(0),
                    "evidence_text": evidence,
                    "extraction_reason": "GB_PREFIX"
                }
            )

    # --------------------------------------------------------
    # 2. 9 DIGITS WITH VAT CONTEXT
    # --------------------------------------------------------

    for match in NINE_DIGIT_PATTERN.finditer(text):

        raw_number = match.group(1)

        vat = normalize_vat(
            raw_number
        )

        if vat is None:
            continue

        context_start = max(
            0,
            match.start() - 100
        )

        context_end = min(
            len(text),
            match.end() + 100
        )

        context = text[
            context_start:context_end
        ]

        has_vat_context = bool(
            VAT_CONTEXT_PATTERN.search(
                context
            )
        )

        if not has_vat_context:
            continue

        if vat in seen:
            continue

        seen.add(vat)

        candidates.append(
            {
                "vat": vat,
                "raw_match": match.group(0),
                "evidence_text": context,
                "extraction_reason": "VAT_CONTEXT"
            }
        )

    return candidates


# ============================================================
# DOMAIN / SOURCE
# ============================================================

def get_domain(url):

    try:

        domain = urlparse(
            url
        ).netloc.lower()

        return domain.removeprefix(
            "www."
        )

    except Exception:

        return ""


def classify_source(
    url,
    content_type=""
):

    domain = get_domain(
        url
    )

    if "datalog.co.uk" in domain:
        return "DATALOG"

    if "vat-lookup.co.uk" in domain:
        return "VAT_LOOKUP"

    if domain.endswith("gov.uk"):
        return "PUBLIC_SECTOR"

    if (
        "pdf" in content_type.lower()
        or url.lower().endswith(".pdf")
    ):
        return "PDF"

    return "WEBPAGE"


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf_text(content):

    try:

        pdf_file = BytesIO(
            content
        )

        reader = PdfReader(
            pdf_file
        )

        page_texts = []

        for page in reader.pages[:50]:

            page_text = page.extract_text()

            if page_text:
                page_texts.append(
                    page_text
                )

        return "\n".join(
            page_texts
        )

    except Exception:

        return ""


# ============================================================
# FETCH DOCUMENT
# ============================================================

def fetch_document(url):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=HTTP_TIMEOUT,
            allow_redirects=True
        )

        if response.status_code >= 400:
            return None

        content_length = response.headers.get(
            "Content-Length"
        )

        if content_length:

            try:

                if int(content_length) > MAX_CONTENT_SIZE:
                    return None

            except ValueError:
                pass

        content = response.content

        if len(content) > MAX_CONTENT_SIZE:
            return None

        content_type = response.headers.get(
            "Content-Type",
            ""
        ).lower()

        # ----------------------------------------------------
        # PDF
        # ----------------------------------------------------

        if (
            "application/pdf" in content_type
            or response.url.lower().endswith(".pdf")
        ):

            text = extract_pdf_text(
                content
            )

            return {
                "url": response.url,
                "text": text,
                "content_type": "application/pdf"
            }

        # ----------------------------------------------------
        # HTML
        # ----------------------------------------------------

        if (
            "text/html" in content_type
            or "application/xhtml" in content_type
            or content_type == ""
        ):

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            for tag in soup(
                [
                    "script",
                    "style",
                    "noscript"
                ]
            ):
                tag.decompose()

            text = soup.get_text(
                separator=" ",
                strip=True
            )

            return {
                "url": response.url,
                "text": text,
                "content_type": "text/html"
            }

        return None

    except requests.RequestException:

        return None

    except Exception:

        return None


# ============================================================
# ENTITY EVIDENCE
# ============================================================

def evaluate_entity_evidence(
    text,
    company_number,
    company_name
):

    clean_text = normalize_text(
        text
    )

    uppercase_text = clean_text.upper()

    company_number_found = (
        str(company_number).upper()
        in uppercase_text
    )

    normalized_company = normalize_company_name(
        company_name
    )

    normalized_page_text = normalize_company_name(
        clean_text
    )

    company_name_found = (
        len(normalized_company) >= 4
        and normalized_company
        in normalized_page_text
    )

    return (
        company_number_found,
        company_name_found
    )


def get_entity_evidence_label(
    company_number_found,
    company_name_found
):

    if company_number_found:
        return "COMPANY_NUMBER"

    if company_name_found:
        return "COMPANY_NAME"

    return "NONE"


# ============================================================
# BUILD SEARCH QUERIES
# ============================================================

def build_queries(
    company_number,
    company_name,
    postcode
):

    queries = []

    # --------------------------------------------------------
    # GENERIC SEARCH
    # --------------------------------------------------------

    queries.append(
        {
            "query_type": "COMPANY_NUMBER_GENERAL",
            "query": f'"{company_number}" VAT'
        }
    )

    queries.append(
        {
            "query_type": "COMPANY_NAME_GENERAL",
            "query": f'"{company_name}" "VAT"'
        }
    )

    if (
        postcode
        and str(postcode).strip()
        and str(postcode).lower() != "nan"
    ):

        queries.append(
            {
                "query_type": "NAME_POSTCODE_GENERAL",
                "query": (
                    f'"{company_name}" '
                    f'"{postcode}" VAT'
                )
            }
        )

    # --------------------------------------------------------
    # DATALOG TARGETED SEARCH
    # --------------------------------------------------------

    queries.append(
        {
            "query_type": "DATALOG_COMPANY_NUMBER",
            "query": (
                f'"{company_number}" '
                f'site:datalog.co.uk'
            )
        }
    )

    queries.append(
        {
            "query_type": "DATALOG_COMPANY_NAME",
            "query": (
                f'"{company_name}" '
                f'site:datalog.co.uk VAT'
            )
        }
    )

    # --------------------------------------------------------
    # VAT LOOKUP TARGETED SEARCH
    # --------------------------------------------------------

    queries.append(
        {
            "query_type": "VAT_LOOKUP_COMPANY_NUMBER",
            "query": (
                f'"{company_number}" '
                f'site:vat-lookup.co.uk'
            )
        }
    )

    queries.append(
        {
            "query_type": "VAT_LOOKUP_COMPANY_NAME",
            "query": (
                f'"{company_name}" '
                f'site:vat-lookup.co.uk'
            )
        }
    )

    return queries


# ============================================================
# SEARCH WEB
# ============================================================

def search_web(query):

    try:

        search_client = DDGS(
            timeout=10
        )

        results = search_client.text(
            query,
            region="uk-en",
            safesearch="off",
            max_results=MAX_SEARCH_RESULTS,
            backend="auto"
        )

        if results is None:
            return [], "NO_RESULTS"

        results = list(
            results
        )

        if len(results) == 0:
            return [], "NO_RESULTS"

        return results, "SUCCESS"

    except Exception as error:

        error_text = str(
            error
        )

        if "No results found" in error_text:
            return [], "NO_RESULTS"

        print(
            f"    Search error: {error}"
        )

        return [], "FAILED"


# ============================================================
# LOAD SAMPLE
# ============================================================

if not INPUT_SAMPLE.exists():

    raise FileNotFoundError(
        f"Sample not found:\n{INPUT_SAMPLE}"
    )


sample_df = pd.read_csv(
    INPUT_SAMPLE,
    dtype=str
)


# ============================================================
# RESUME SUPPORT
# ============================================================

if OUTPUT_CANDIDATES.exists():

    existing_candidates_df = pd.read_csv(
        OUTPUT_CANDIDATES,
        dtype=str
    )

    all_candidates = (
        existing_candidates_df
        .to_dict("records")
    )

else:

    all_candidates = []


if OUTPUT_LOG.exists():

    existing_log_df = pd.read_csv(
        OUTPUT_LOG,
        dtype=str
    )

    processed_sample_ids = set(
        existing_log_df[
            "sample_id"
        ].astype(str)
    )

    discovery_log = (
        existing_log_df
        .to_dict("records")
    )

else:

    processed_sample_ids = set()
    discovery_log = []


# ============================================================
# MAIN LOOP
# ============================================================

# TEST MODE:
#
# momentan primele 10 companii.
#
# Pentru rularea finală:
#
# for _, company in sample_df.iterrows():
#
for _, company in sample_df.iterrows():
    
    sample_id = str(
        company["sample_id"]
    )

    if sample_id in processed_sample_ids:

        print(
            f"[{sample_id}] Already processed - skipping."
        )

        continue

    company_number = str(
        company["company_number"]
    ).strip()

    company_name = str(
        company["company_name"]
    ).strip()

    postcode = str(
        company.get(
            "postcode",
            ""
        )
    ).strip()

    print()
    print("=" * 70)

    print(
        f"[{sample_id}/200] "
        f"{company_name} "
        f"({company_number})"
    )

    queries = build_queries(
        company_number,
        company_name,
        postcode
    )

    processed_urls = set()

    company_candidate_count = 0
    search_result_count = 0
    fetched_document_count = 0

    queries_with_results_count = 0
    no_result_query_count = 0
    failed_query_count = 0

    # Contorizăm și pe tip de query.
    query_type_stats = {}

    # ========================================================
    # QUERY LOOP
    # ========================================================

    for query_info in queries:

        query_type = query_info[
            "query_type"
        ]

        query = query_info[
            "query"
        ]

        print(
            f"  [{query_type}] {query}"
        )

        (
            search_results,
            search_status
        ) = search_web(
            query
        )

        if query_type not in query_type_stats:

            query_type_stats[
                query_type
            ] = {
                "executed": 0,
                "with_results": 0,
                "no_results": 0,
                "failed": 0
            }

        query_type_stats[
            query_type
        ]["executed"] += 1

        if search_status == "SUCCESS":

            queries_with_results_count += 1

            query_type_stats[
                query_type
            ]["with_results"] += 1

        elif search_status == "NO_RESULTS":

            no_result_query_count += 1

            query_type_stats[
                query_type
            ]["no_results"] += 1

        elif search_status == "FAILED":

            failed_query_count += 1

            query_type_stats[
                query_type
            ]["failed"] += 1

        search_result_count += len(
            search_results
        )

        # ====================================================
        # RESULT LOOP
        # ====================================================

        for result in search_results:

            url = str(
                result.get(
                    "href",
                    ""
                )
            ).strip()

            snippet = str(
                result.get(
                    "body",
                    ""
                )
            )

            if not url:
                continue

            # =================================================
            # SEARCH SNIPPET EXTRACTION
            # =================================================

            snippet_candidates = (
                extract_vat_candidates(
                    snippet
                )
            )

            for candidate in snippet_candidates:

                (
                    number_found,
                    name_found
                ) = evaluate_entity_evidence(
                    snippet,
                    company_number,
                    company_name
                )

                # Fără entity linkage = reject.
                if (
                    not number_found
                    and not name_found
                ):

                    continue

                entity_evidence = (
                    get_entity_evidence_label(
                        number_found,
                        name_found
                    )
                )

                candidate_row = {

                    "sample_id":
                        sample_id,

                    "company_number":
                        company_number,

                    "company_name":
                        company_name,

                    "candidate_vat":
                        candidate["vat"],

                    "raw_match":
                        candidate["raw_match"],

                    "source_url":
                        url,

                    "source_domain":
                        get_domain(
                            url
                        ),

                    "source_type":
                        "SEARCH_SNIPPET",

                    "query_type":
                        query_type,

                    "search_query":
                        query,

                    "extraction_reason":
                        candidate[
                            "extraction_reason"
                        ],

                    "company_number_on_page":
                        number_found,

                    "company_name_on_page":
                        name_found,

                    "entity_evidence":
                        entity_evidence,

                    "evidence_text":
                        candidate[
                            "evidence_text"
                        ]
                }

                all_candidates.append(
                    candidate_row
                )

                company_candidate_count += 1

            # =================================================
            # FETCH RESULT DOCUMENT
            # =================================================

            if url in processed_urls:
                continue

            processed_urls.add(
                url
            )

            print(
                f"    Fetching: {get_domain(url)}"
            )

            document = fetch_document(
                url
            )

            if document is None:
                continue

            fetched_document_count += 1

            document_text = document[
                "text"
            ]

            if not document_text:
                continue

            document_candidates = (
                extract_vat_candidates(
                    document_text
                )
            )

            (
                company_number_found,
                company_name_found
            ) = evaluate_entity_evidence(
                document_text,
                company_number,
                company_name
            )

            # =================================================
            # DOCUMENT VAT CANDIDATES
            # =================================================

            for candidate in document_candidates:

                if (
                    not company_number_found
                    and not company_name_found
                ):

                    continue

                source_type = classify_source(
                    document["url"],
                    document["content_type"]
                )

                entity_evidence = (
                    get_entity_evidence_label(
                        company_number_found,
                        company_name_found
                    )
                )

                candidate_row = {

                    "sample_id":
                        sample_id,

                    "company_number":
                        company_number,

                    "company_name":
                        company_name,

                    "candidate_vat":
                        candidate["vat"],

                    "raw_match":
                        candidate["raw_match"],

                    "source_url":
                        document["url"],

                    "source_domain":
                        get_domain(
                            document["url"]
                        ),

                    "source_type":
                        source_type,

                    "query_type":
                        query_type,

                    "search_query":
                        query,

                    "extraction_reason":
                        candidate[
                            "extraction_reason"
                        ],

                    "company_number_on_page":
                        company_number_found,

                    "company_name_on_page":
                        company_name_found,

                    "entity_evidence":
                        entity_evidence,

                    "evidence_text":
                        candidate[
                            "evidence_text"
                        ]
                }

                all_candidates.append(
                    candidate_row
                )

                company_candidate_count += 1

            time.sleep(
                random.uniform(
                    0.7,
                    1.5
                )
            )

        time.sleep(
            random.uniform(
                2.0,
                4.0
            )
        )

    # ========================================================
    # DEDUPLICATE + SAVE CANDIDATES
    # ========================================================

    candidates_df = pd.DataFrame(
        all_candidates
    )

    if not candidates_df.empty:

        candidates_df = (
            candidates_df
            .drop_duplicates(
                subset=[
                    "sample_id",
                    "candidate_vat",
                    "source_url"
                ],
                keep="first"
            )
        )

        all_candidates = (
            candidates_df
            .to_dict("records")
        )

        candidates_df.to_csv(
            OUTPUT_CANDIDATES,
            index=False,
            encoding="utf-8-sig"
        )

    # ========================================================
    # DISCOVERY LOG
    # ========================================================

    log_row = {

        "sample_id":
            sample_id,

        "company_number":
            company_number,

        "company_name":
            company_name,

        "queries_executed":
            len(queries),

        "queries_with_results":
            queries_with_results_count,

        "queries_no_results":
            no_result_query_count,

        "failed_queries":
            failed_query_count,

        "search_results_seen":
            search_result_count,

        "documents_fetched":
            fetched_document_count,

        "candidate_occurrences_found":
            company_candidate_count
    }

    # Adăugăm statistici separate pe tip de query.
    for query_type, stats in query_type_stats.items():

        safe_query_type = (
            query_type
            .lower()
        )

        log_row[
            f"{safe_query_type}_with_results"
        ] = stats[
            "with_results"
        ]

        log_row[
            f"{safe_query_type}_no_results"
        ] = stats[
            "no_results"
        ]

        log_row[
            f"{safe_query_type}_failed"
        ] = stats[
            "failed"
        ]

    discovery_log.append(
        log_row
    )

    discovery_log_df = pd.DataFrame(
        discovery_log
    )

    discovery_log_df.to_csv(
        OUTPUT_LOG,
        index=False,
        encoding="utf-8-sig"
    )

    processed_sample_ids.add(
        sample_id
    )

    # ========================================================
    # COMPANY SUMMARY
    # ========================================================

    print(
        f"  Queries with results: "
        f"{queries_with_results_count}/{len(queries)}"
    )

    print(
        f"  Queries with no results: "
        f"{no_result_query_count}"
    )

    print(
        f"  Technical failures: "
        f"{failed_query_count}"
    )

    print(
        f"  Search results seen: "
        f"{search_result_count}"
    )

    print(
        f"  Documents fetched: "
        f"{fetched_document_count}"
    )

    print(
        f"  Candidate occurrences accepted: "
        f"{company_candidate_count}"
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

print()
print("=" * 70)
print("VAT DISCOVERY COMPLETE")
print("=" * 70)


# ============================================================
# CANDIDATE SUMMARY
# ============================================================

if OUTPUT_CANDIDATES.exists():

    final_candidates = pd.read_csv(
        OUTPUT_CANDIDATES,
        dtype=str
    )

    total_candidate_rows = len(
        final_candidates
    )

    companies_with_candidate = (
        final_candidates[
            "sample_id"
        ]
        .nunique()
    )

    unique_vats = (
        final_candidates[
            "candidate_vat"
        ]
        .nunique()
    )

    evidence_distribution = (
        final_candidates[
            "entity_evidence"
        ]
        .value_counts()
    )

    source_distribution = (
        final_candidates[
            "source_type"
        ]
        .value_counts()
    )

    query_type_distribution = (
        final_candidates[
            "query_type"
        ]
        .value_counts()
    )

else:

    total_candidate_rows = 0
    companies_with_candidate = 0
    unique_vats = 0

    evidence_distribution = pd.Series(
        dtype=int
    )

    source_distribution = pd.Series(
        dtype=int
    )

    query_type_distribution = pd.Series(
        dtype=int
    )


# ============================================================
# DISCOVERY LOG SUMMARY
# ============================================================

if OUTPUT_LOG.exists():

    final_log = pd.read_csv(
        OUTPUT_LOG
    )

    processed_companies = len(
        final_log
    )

    total_queries_executed = (
        final_log[
            "queries_executed"
        ]
        .fillna(0)
        .astype(int)
        .sum()
    )

    total_queries_with_results = (
        final_log[
            "queries_with_results"
        ]
        .fillna(0)
        .astype(int)
        .sum()
    )

    total_queries_no_results = (
        final_log[
            "queries_no_results"
        ]
        .fillna(0)
        .astype(int)
        .sum()
    )

    total_failed_queries = (
        final_log[
            "failed_queries"
        ]
        .fillna(0)
        .astype(int)
        .sum()
    )

    total_search_results = (
        final_log[
            "search_results_seen"
        ]
        .fillna(0)
        .astype(int)
        .sum()
    )

    total_documents_fetched = (
        final_log[
            "documents_fetched"
        ]
        .fillna(0)
        .astype(int)
        .sum()
    )

else:

    processed_companies = 0
    total_queries_executed = 0
    total_queries_with_results = 0
    total_queries_no_results = 0
    total_failed_queries = 0
    total_search_results = 0
    total_documents_fetched = 0


# ============================================================
# PRINT FINAL SUMMARY
# ============================================================

print()

print(
    f"Sample companies total:     "
    f"{len(sample_df)}"
)

print(
    f"Companies processed:        "
    f"{processed_companies}"
)

print()

print(
    f"Queries executed:           "
    f"{total_queries_executed}"
)

print(
    f"Queries with results:       "
    f"{total_queries_with_results}"
)

print(
    f"Queries with no results:    "
    f"{total_queries_no_results}"
)

print(
    f"Technical failures:         "
    f"{total_failed_queries}"
)

print()

print(
    f"Search results seen:        "
    f"{total_search_results}"
)

print(
    f"Documents fetched:          "
    f"{total_documents_fetched}"
)

print()

print(
    f"Companies with candidate:   "
    f"{companies_with_candidate}"
)

print(
    f"Unique VAT candidates:      "
    f"{unique_vats}"
)

print(
    f"Candidate evidence rows:    "
    f"{total_candidate_rows}"
)

print()


if not evidence_distribution.empty:

    print(
        "Entity evidence distribution:"
    )

    print(
        evidence_distribution.to_string()
    )

    print()


if not source_distribution.empty:

    print(
        "Candidate source distribution:"
    )

    print(
        source_distribution.to_string()
    )

    print()


if not query_type_distribution.empty:

    print(
        "Candidate query type distribution:"
    )

    print(
        query_type_distribution.to_string()
    )

    print()


print(
    "Candidates saved to:"
)

print(
    OUTPUT_CANDIDATES
)

print()

print(
    "Discovery log saved to:"
)

print(
    OUTPUT_LOG
)