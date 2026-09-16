"""
04_hmrc_verify.py

HMRC VAT verification stage for the VAT Identifier Discovery PoC.

IMPORTANT
---------
There are two completely different execution modes:

1. SANDBOX
   - Used only to test HMRC authentication/API integration.
   - Does NOT validate the real VAT candidates discovered from the web.
   - Does NOT calculate PoC precision / FPR / coverage.

2. PRODUCTION
   - Validates the real VAT candidates.
   - Retrieves the registered business name/address from HMRC.
   - Links the returned HMRC entity back to the target Companies House entity.
   - Calculates final PoC metrics.

Environment variables
---------------------

Required:

    HMRC_ENV
        "sandbox" or "production"

    HMRC_CLIENT_ID
    HMRC_CLIENT_SECRET

Optional for sandbox:

    HMRC_SANDBOX_VAT

        A mock VAT registration number explicitly supplied by HMRC
        for sandbox testing.

Example PowerShell:

    $env:HMRC_ENV="sandbox"
    $env:HMRC_CLIENT_ID="..."
    $env:HMRC_CLIENT_SECRET="..."
    python .\\src\\04_hmrc_verify.py

Production:

    $env:HMRC_ENV="production"
    $env:HMRC_CLIENT_ID="..."
    $env:HMRC_CLIENT_SECRET="..."
    python .\\src\\04_hmrc_verify.py

Do NOT commit HMRC credentials to Git.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata

from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd
import requests


# ============================================================================
# PATHS
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"

CANDIDATES_FILE = PROCESSED_DIR / "vat_candidates_filtered.csv"
SAMPLE_FILE = PROCESSED_DIR / "sample_companies.csv"

PRODUCTION_OUTPUT_FILE = (
    PROCESSED_DIR / "hmrc_verified_candidates.csv"
)

SANDBOX_OUTPUT_FILE = (
    PROCESSED_DIR / "hmrc_sandbox_test.json"
)


# ============================================================================
# HMRC CONFIGURATION
# ============================================================================

HMRC_ENV = os.getenv(
    "HMRC_ENV",
    "sandbox",
).strip().lower()

HMRC_CLIENT_ID = os.getenv(
    "HMRC_CLIENT_ID",
    "",
).strip()

HMRC_CLIENT_SECRET = os.getenv(
    "HMRC_CLIENT_SECRET",
    "",
).strip()

HMRC_SANDBOX_VAT = os.getenv(
    "HMRC_SANDBOX_VAT",
    "",
).strip()


if HMRC_ENV not in {"sandbox", "production"}:
    raise RuntimeError(
        "HMRC_ENV must be either 'sandbox' or 'production'."
    )


if HMRC_ENV == "sandbox":

    BASE_URL = "https://test-api.service.hmrc.gov.uk"

else:

    BASE_URL = "https://api.service.hmrc.gov.uk"


TOKEN_URL = f"{BASE_URL}/oauth/token"

API_VERSION_HEADER = "application/vnd.hmrc.2.0+json"


# ============================================================================
# HTTP CONFIGURATION
# ============================================================================

REQUEST_TIMEOUT = 30

MAX_RETRIES = 4

RETRYABLE_HTTP_CODES = {
    429,
    500,
    502,
    503,
    504,
}


# ============================================================================
# BASIC HELPERS
# ============================================================================


def safe_string(value: Any) -> str:
    """
    Convert a value to a clean string.

    Pandas NaN values are converted to an empty string.
    """

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(value).strip()


def normalize_vat(value: Any) -> str:
    """
    Normalize a UK VAT number to its 9 numeric digits.

    Examples:

        GB347020919 -> 347020919
        347 0209 19 -> 347020919
    """

    text = safe_string(value).upper()

    text = re.sub(
        r"^GB",
        "",
        text,
    )

    digits = re.sub(
        r"\D",
        "",
        text,
    )

    return digits


def format_vat(value: Any) -> str:
    """
    Return normalized VAT with GB prefix.
    """

    vat = normalize_vat(value)

    if not vat:
        return ""

    return f"GB{vat}"


def normalize_postcode(value: Any) -> str:
    """
    Normalize UK postcode for comparisons.
    """

    return re.sub(
        r"[^A-Z0-9]",
        "",
        safe_string(value).upper(),
    )


# ============================================================================
# COMPANY NAME NORMALIZATION
# ============================================================================


LEGAL_SUFFIXES = {
    "LIMITED",
    "LTD",
    "PLC",
    "LLP",
    "LP",
}


def normalize_company_name(value: Any) -> str:
    """
    Normalize legal/trading company names for conservative matching.

    The function:
    - converts Unicode consistently
    - uppercases
    - turns '&' into 'AND'
    - removes punctuation
    - removes common UK legal suffixes

    It intentionally does NOT perform aggressive fuzzy transformations.
    """

    text = safe_string(value)

    if not text:
        return ""

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = text.upper()

    text = text.replace(
        "&",
        " AND ",
    )

    # Replace punctuation with spaces.
    text = re.sub(
        r"[^A-Z0-9]+",
        " ",
        text,
    )

    words = [
        word
        for word in text.split()
        if word not in LEGAL_SUFFIXES
    ]

    return " ".join(words).strip()


def company_name_similarity(
    target_name: Any,
    hmrc_name: Any,
) -> float:
    """
    Compute similarity between normalized Companies House name
    and the HMRC registered business name.
    """

    target = normalize_company_name(target_name)
    hmrc = normalize_company_name(hmrc_name)

    if not target or not hmrc:
        return 0.0

    if target == hmrc:
        return 1.0

    return SequenceMatcher(
        None,
        target,
        hmrc,
    ).ratio()


# ============================================================================
# INPUT COLUMN HELPERS
# ============================================================================


def find_column(
    df: pd.DataFrame,
    possible_names: list[str],
    required: bool = True,
) -> str | None:
    """
    Find the first matching column from several possible names.

    This makes the script tolerant of small changes made in earlier stages.
    """

    normalized_map = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for candidate in possible_names:

        key = candidate.lower()

        if key in normalized_map:
            return normalized_map[key]

    if required:
        raise RuntimeError(
            "Could not find any of these columns: "
            + ", ".join(possible_names)
            + "\nAvailable columns:\n"
            + ", ".join(map(str, df.columns))
        )

    return None


# ============================================================================
# HMRC AUTHENTICATION
# ============================================================================


def get_access_token() -> str:
    """
    Obtain an application-restricted OAuth 2.0 token
    using client_credentials.
    """

    if not HMRC_CLIENT_ID:

        raise RuntimeError(
            "HMRC_CLIENT_ID environment variable is missing."
        )

    if not HMRC_CLIENT_SECRET:

        raise RuntimeError(
            "HMRC_CLIENT_SECRET environment variable is missing."
        )

    payload = {
        "client_id": HMRC_CLIENT_ID,
        "client_secret": HMRC_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }

    try:

        response = requests.post(
            TOKEN_URL,
            data=payload,
            timeout=REQUEST_TIMEOUT,
        )

    except requests.RequestException as exc:

        raise RuntimeError(
            f"Could not connect to HMRC OAuth endpoint: {exc}"
        ) from exc

    if response.status_code != 200:

        raise RuntimeError(
            "\nHMRC OAuth authentication failed.\n"
            f"HTTP status: {response.status_code}\n"
            f"Response: {response.text}"
        )

    try:

        payload = response.json()

    except ValueError as exc:

        raise RuntimeError(
            "HMRC OAuth endpoint returned non-JSON response."
        ) from exc

    token = payload.get(
        "access_token"
    )

    if not token:

        raise RuntimeError(
            "HMRC authentication response did not contain access_token."
        )

    return token


# ============================================================================
# HMRC VAT REQUEST
# ============================================================================


def build_hmrc_address(
    address: dict[str, Any] | None,
) -> str:
    """
    Convert HMRC address JSON into a readable single-line address.
    """

    if not isinstance(
        address,
        dict,
    ):
        return ""

    fields = [
        "line1",
        "line2",
        "line3",
        "line4",
        "postcode",
        "countryCode",
    ]

    parts = []

    for field in fields:

        value = safe_string(
            address.get(field)
        )

        if value:
            parts.append(value)

    return ", ".join(parts)


def empty_hmrc_result(
    status: str,
    http_status: int | str = "",
    error: str = "",
) -> dict[str, Any]:
    """
    Standard empty HMRC result structure.
    """

    return {
        "hmrc_status": status,
        "hmrc_http_status": http_status,
        "hmrc_name": "",
        "hmrc_vat_number": "",
        "hmrc_address": "",
        "hmrc_postcode": "",
        "hmrc_country_code": "",
        "hmrc_processing_date": "",
        "hmrc_error": error,
    }


def verify_vat_with_hmrc(
    vat_number: Any,
    access_token: str,
) -> dict[str, Any]:
    """
    Check one VAT registration number against HMRC.

    200:
        VAT registration exists and HMRC business details are returned.

    404:
        VAT is not registered / not found.

    401 / 403:
        authentication or API subscription/access problem.

    Retry:
        429 and selected server-side errors.
    """

    vat = normalize_vat(
        vat_number
    )

    if not re.fullmatch(
        r"\d{9}",
        vat,
    ):

        return empty_hmrc_result(
            status="MALFORMED",
            error=(
                "VAT number was not exactly nine digits "
                "after normalization."
            ),
        )

    endpoint = (
        f"{BASE_URL}"
        f"/organisations/vat/check-vat-number/"
        f"lookup/{vat}"
    )

    headers = {
        "Accept": API_VERSION_HEADER,
        "Authorization": f"Bearer {access_token}",
    }

    last_error = ""

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:

            response = requests.get(
                endpoint,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )

        except requests.RequestException as exc:

            last_error = str(exc)

            if attempt < MAX_RETRIES:

                time.sleep(
                    2 ** (attempt - 1)
                )

                continue

            return empty_hmrc_result(
                status="NETWORK_ERROR",
                error=last_error,
            )

        # --------------------------------------------------------------
        # VALID / REGISTERED
        # --------------------------------------------------------------

        if response.status_code == 200:

            try:

                payload = response.json()

            except ValueError:

                return empty_hmrc_result(
                    status="RESPONSE_ERROR",
                    http_status=200,
                    error="HMRC returned invalid JSON.",
                )

            target = payload.get(
                "target",
                {},
            )

            address = target.get(
                "address",
                {},
            )

            return {
                "hmrc_status": "VALID",
                "hmrc_http_status": 200,
                "hmrc_name": safe_string(
                    target.get("name")
                ),
                "hmrc_vat_number": safe_string(
                    target.get("vatNumber")
                ),
                "hmrc_address": build_hmrc_address(
                    address
                ),
                "hmrc_postcode": safe_string(
                    address.get("postcode")
                )
                if isinstance(address, dict)
                else "",
                "hmrc_country_code": safe_string(
                    address.get("countryCode")
                )
                if isinstance(address, dict)
                else "",
                "hmrc_processing_date": safe_string(
                    payload.get("processingDate")
                ),
                "hmrc_error": "",
            }

        # --------------------------------------------------------------
        # NOT REGISTERED
        # --------------------------------------------------------------

        if response.status_code == 404:

            return empty_hmrc_result(
                status="INVALID",
                http_status=404,
            )

        # --------------------------------------------------------------
        # AUTHENTICATION / ACCESS ERROR
        # --------------------------------------------------------------

        if response.status_code in {
            401,
            403,
        }:

            return empty_hmrc_result(
                status="AUTH_ERROR",
                http_status=response.status_code,
                error=response.text[:2000],
            )

        # --------------------------------------------------------------
        # RATE LIMIT / SERVER ERROR
        # --------------------------------------------------------------

        if (
            response.status_code
            in RETRYABLE_HTTP_CODES
        ):

            last_error = (
                f"HTTP {response.status_code}: "
                f"{response.text[:1000]}"
            )

            if attempt < MAX_RETRIES:

                retry_after = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                try:
                    sleep_seconds = float(
                        retry_after
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    sleep_seconds = (
                        2 ** (attempt - 1)
                    )

                time.sleep(
                    sleep_seconds
                )

                continue

            return empty_hmrc_result(
                status="TEMPORARY_ERROR",
                http_status=response.status_code,
                error=last_error,
            )

        # --------------------------------------------------------------
        # ANY OTHER RESPONSE
        # --------------------------------------------------------------

        return empty_hmrc_result(
            status="HTTP_ERROR",
            http_status=response.status_code,
            error=response.text[:2000],
        )

    return empty_hmrc_result(
        status="UNKNOWN_ERROR",
        error=last_error,
    )


# ============================================================================
# ENTITY LINKAGE
# ============================================================================


def classify_entity_match(
    company_name: Any,
    company_postcode: Any,
    hmrc_result: dict[str, Any],
) -> tuple[str, float, bool | None]:
    """
    Decide whether a valid VAT registration belongs to the
    Companies House company we are trying to identify.

    Precision is intentionally favoured over recall.

    Returns:

        entity_status
        name_similarity
        postcode_match
    """

    hmrc_status = safe_string(
        hmrc_result.get(
            "hmrc_status"
        )
    )

    if hmrc_status == "INVALID":

        return (
            "INVALID",
            0.0,
            None,
        )

    if hmrc_status != "VALID":

        return (
            "UNRESOLVED",
            0.0,
            None,
        )

    target_name = safe_string(
        company_name
    )

    target_postcode = normalize_postcode(
        company_postcode
    )

    hmrc_name = safe_string(
        hmrc_result.get(
            "hmrc_name"
        )
    )

    hmrc_postcode = normalize_postcode(
        hmrc_result.get(
            "hmrc_postcode"
        )
    )

    target_normalized = normalize_company_name(
        target_name
    )

    hmrc_normalized = normalize_company_name(
        hmrc_name
    )

    score = company_name_similarity(
        target_name,
        hmrc_name,
    )

    postcode_match: bool | None

    if (
        target_postcode
        and hmrc_postcode
    ):

        postcode_match = (
            target_postcode
            == hmrc_postcode
        )

    else:

        postcode_match = None

    # --------------------------------------------------------------
    # Very strong evidence:
    # normalized legal names match exactly.
    # --------------------------------------------------------------

    if (
        target_normalized
        and hmrc_normalized
        and target_normalized
        == hmrc_normalized
    ):

        return (
            "VERIFIED_MATCH",
            score,
            postcode_match,
        )

    # --------------------------------------------------------------
    # Strong fuzzy name + same postcode.
    # --------------------------------------------------------------

    if (
        score >= 0.92
        and postcode_match is True
    ):

        return (
            "VERIFIED_MATCH",
            score,
            postcode_match,
        )

    # --------------------------------------------------------------
    # Very strong name similarity, but postcode unavailable.
    # Keep conservative.
    # --------------------------------------------------------------

    if (
        score >= 0.97
        and postcode_match is None
    ):

        return (
            "VERIFIED_MATCH",
            score,
            postcode_match,
        )

    # --------------------------------------------------------------
    # Clearly another entity.
    #
    # Low name similarity + conflicting postcode.
    # --------------------------------------------------------------

    if (
        score < 0.60
        and postcode_match is False
    ):

        return (
            "VALID_WRONG_ENTITY",
            score,
            postcode_match,
        )

    # Very different company name even where postcode is absent.
    if (
        score < 0.40
        and postcode_match is not True
    ):

        return (
            "VALID_WRONG_ENTITY",
            score,
            postcode_match,
        )

    # --------------------------------------------------------------
    # Anything uncertain requires manual review.
    # --------------------------------------------------------------

    return (
        "AMBIGUOUS",
        score,
        postcode_match,
    )


# ============================================================================
# LOAD REAL CANDIDATES
# ============================================================================


def load_candidates() -> pd.DataFrame:
    """
    Load candidate VAT numbers created by Step 3.6.

    Multiple evidence rows for the same company/VAT are collapsed to
    a single candidate pair before querying HMRC.
    """

    if not CANDIDATES_FILE.exists():

        raise FileNotFoundError(
            f"Candidate file not found:\n{CANDIDATES_FILE}"
        )

    candidates = pd.read_csv(
        CANDIDATES_FILE,
        dtype=str,
    ).fillna("")

    vat_col = find_column(
        candidates,
        [
            "candidate_vat",
            "vat_number",
            "vat",
        ],
    )

    company_number_col = find_column(
        candidates,
        [
            "company_number",
            "companynumber",
        ],
    )

    company_name_col = find_column(
        candidates,
        [
            "company_name",
            "companyname",
        ],
    )

    sample_id_col = find_column(
        candidates,
        [
            "sample_id",
            "sampleid",
        ],
        required=False,
    )

    candidates[
        "_candidate_vat_normalized"
    ] = candidates[
        vat_col
    ].apply(
        normalize_vat
    )

    candidates[
        "_company_number"
    ] = candidates[
        company_number_col
    ].astype(str).str.strip()

    candidates[
        "_company_name"
    ] = candidates[
        company_name_col
    ].astype(str).str.strip()

    if sample_id_col:

        candidates[
            "_sample_id"
        ] = candidates[
            sample_id_col
        ].astype(str).str.strip()

    else:

        candidates[
            "_sample_id"
        ] = ""

    # Keep a representative evidence row for each unique
    # company/VAT pair.
    candidates = candidates.drop_duplicates(
        subset=[
            "_company_number",
            "_candidate_vat_normalized",
        ],
        keep="first",
    ).copy()

    return candidates


# ============================================================================
# COMPANIES HOUSE POSTCODES
# ============================================================================


def load_company_postcodes() -> dict[str, str]:
    """
    Build company_number -> postcode mapping from frozen sample.

    If postcode is unavailable, entity linkage can still use company name.
    """

    if not SAMPLE_FILE.exists():

        return {}

    sample = pd.read_csv(
        SAMPLE_FILE,
        dtype=str,
    ).fillna("")

    number_col = find_column(
        sample,
        [
            "company_number",
            "companynumber",
            "CompanyNumber",
        ],
        required=False,
    )

    postcode_col = find_column(
        sample,
        [
            "postcode",
            "registered_office_postcode",
            "regaddress.postcode",
            "RegAddress.PostCode",
        ],
        required=False,
    )

    if (
        number_col is None
        or postcode_col is None
    ):

        return {}

    mapping = {}

    for _, row in sample.iterrows():

        company_number = safe_string(
            row[number_col]
        )

        postcode = safe_string(
            row[postcode_col]
        )

        if company_number:

            mapping[
                company_number.upper()
            ] = postcode

    return mapping


# ============================================================================
# SANDBOX MODE
# ============================================================================


def run_sandbox() -> None:
    """
    Sandbox is deliberately separated from the real PoC.

    It demonstrates:
    - OAuth authentication
    - API subscription/access
    - request/response handling

    It does NOT test discovered real VAT numbers.
    """

    print(
        "=" * 70
    )

    print(
        "HMRC VAT API - SANDBOX INTEGRATION TEST"
    )

    print(
        "=" * 70
    )

    print()
    print(
        "Environment: SANDBOX"
    )

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "HMRC Sandbox does not validate the real VAT candidates "
        "discovered by this PoC."
    )

    print(
        "The 33 real candidate VAT numbers will NOT be sent "
        "to the Sandbox."
    )

    print(
        "Sandbox results will NOT be used for precision, "
        "false-positive rate, or coverage."
    )

    print()

    print(
        "Requesting HMRC OAuth token..."
    )

    token = get_access_token()

    print(
        "Authentication successful."
    )

    result: dict[str, Any] = {
        "environment": "sandbox",
        "oauth_authentication": "SUCCESS",
        "real_candidates_tested": False,
        "poc_metrics_calculated": False,
        "sandbox_vat_tested": False,
    }

    # --------------------------------------------------------------
    # Optional HMRC-provided mock VAT
    # --------------------------------------------------------------

    if HMRC_SANDBOX_VAT:

        vat = normalize_vat(
            HMRC_SANDBOX_VAT
        )

        print()
        print(
            f"Testing HMRC mock VAT: GB{vat}"
        )

        mock_result = verify_vat_with_hmrc(
            vat,
            token,
        )

        result[
            "sandbox_vat_tested"
        ] = True

        result[
            "sandbox_vat"
        ] = format_vat(
            vat
        )

        result[
            "sandbox_response"
        ] = mock_result

        print(
            "HTTP status:",
            mock_result.get(
                "hmrc_http_status"
            ),
        )

        print(
            "HMRC status:",
            mock_result.get(
                "hmrc_status"
            ),
        )

        if mock_result.get(
            "hmrc_name"
        ):

            print(
                "Mock registered name:",
                mock_result[
                    "hmrc_name"
                ],
            )

    else:

        print()
        print(
            "No HMRC_SANDBOX_VAT was supplied."
        )

        print(
            "OAuth authentication was tested successfully."
        )

        print(
            "To test the lookup endpoint as well, set "
            "HMRC_SANDBOX_VAT to one of HMRC's documented mock VAT "
            "registration numbers."
        )

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        SANDBOX_OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            result,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print(
        "=" * 70
    )

    print(
        "SANDBOX TEST COMPLETE"
    )

    print(
        "=" * 70
    )

    print()

    print(
        "Real VAT candidate checks: NOT PERFORMED"
    )

    print(
        "PoC accuracy metrics:      NOT CALCULATED"
    )

    print()

    print(
        "This is intentional."
    )

    print(
        "Sandbox is used only as evidence that the HMRC API "
        "integration/authentication works."
    )

    print()

    print(
        "Result saved to:"
    )

    print(
        SANDBOX_OUTPUT_FILE
    )


# ============================================================================
# PRODUCTION RESUME SUPPORT
# ============================================================================


def load_existing_production_results() -> pd.DataFrame:
    """
    Load previously saved production verification results.

    Sandbox data can never enter this file through this script.
    """

    if not PRODUCTION_OUTPUT_FILE.exists():

        return pd.DataFrame()

    try:

        existing = pd.read_csv(
            PRODUCTION_OUTPUT_FILE,
            dtype=str,
        ).fillna("")

    except Exception:

        return pd.DataFrame()

    # Defensive check:
    # only accept rows explicitly produced in production.
    if "environment" in existing.columns:

        existing = existing[
            existing[
                "environment"
            ].str.lower()
            == "production"
        ].copy()

    return existing


def result_key(
    company_number: Any,
    vat_number: Any,
) -> str:
    """
    Stable pair identifier for resume support.
    """

    return (
        safe_string(
            company_number
        ).upper()
        + "|"
        + normalize_vat(
            vat_number
        )
    )


# ============================================================================
# METRICS
# ============================================================================


def print_production_metrics(
    results: pd.DataFrame,
    total_sample_size: int = 200,
) -> None:
    """
    Print conservative PoC metrics.

    Recall is deliberately NOT calculated because there is no complete
    ground-truth dataset of VAT registrations for the sample.
    """

    print()
    print(
        "=" * 70
    )

    print(
        "HMRC PRODUCTION VERIFICATION COMPLETE"
    )

    print(
        "=" * 70
    )

    print()

    print(
        f"Candidate pairs checked: {len(results)}"
    )

    if results.empty:

        return

    print()
    print(
        "HMRC status distribution:"
    )

    print(
        results[
            "hmrc_status"
        ].value_counts(
            dropna=False
        ).to_string()
    )

    print()
    print(
        "Entity result distribution:"
    )

    print(
        results[
            "entity_match"
        ].value_counts(
            dropna=False
        ).to_string()
    )

    # --------------------------------------------------------------
    # Verified companies
    # --------------------------------------------------------------

    verified = results[
        results[
            "entity_match"
        ]
        == "VERIFIED_MATCH"
    ]

    verified_companies = (
        verified[
            "company_number"
        ]
        .astype(str)
        .nunique()
    )

    verified_coverage = (
        verified_companies
        / total_sample_size
    )

    # --------------------------------------------------------------
    # Precision / false-positive metrics
    # --------------------------------------------------------------
    #
    # AMBIGUOUS and technical errors are intentionally excluded
    # from the resolved denominator.
    #
    # Resolved candidate:
    #   VERIFIED_MATCH
    #   VALID_WRONG_ENTITY
    #   INVALID
    #
    # False positive:
    #   VALID_WRONG_ENTITY
    #   INVALID
    # --------------------------------------------------------------

    resolved_labels = {
        "VERIFIED_MATCH",
        "VALID_WRONG_ENTITY",
        "INVALID",
    }

    resolved = results[
        results[
            "entity_match"
        ].isin(
            resolved_labels
        )
    ]

    false_positive = results[
        results[
            "entity_match"
        ].isin(
            {
                "VALID_WRONG_ENTITY",
                "INVALID",
            }
        )
    ]

    if len(resolved) > 0:

        precision = (
            len(
                resolved[
                    resolved[
                        "entity_match"
                    ]
                    == "VERIFIED_MATCH"
                ]
            )
            / len(resolved)
        )

        false_positive_rate = (
            len(false_positive)
            / len(resolved)
        )

    else:

        precision = None
        false_positive_rate = None

    candidate_companies = (
        results[
            "company_number"
        ]
        .astype(str)
        .nunique()
    )

    if candidate_companies:

        candidate_company_success_rate = (
            verified_companies
            / candidate_companies
        )

    else:

        candidate_company_success_rate = 0.0

    print()
    print(
        f"Verified companies: {verified_companies}"
    )

    print(
        "Verified sample coverage: "
        f"{verified_coverage:.2%}"
    )

    print(
        "Companies entering HMRC verification: "
        f"{candidate_companies}"
    )

    print(
        "Verified / candidate-company rate: "
        f"{candidate_company_success_rate:.2%}"
    )

    if precision is not None:

        print(
            "Resolved candidate precision: "
            f"{precision:.2%}"
        )

        print(
            "Resolved candidate false-positive rate: "
            f"{false_positive_rate:.2%}"
        )

    else:

        print(
            "Resolved candidate precision: N/A"
        )

        print(
            "Resolved candidate false-positive rate: N/A"
        )

    ambiguous_count = int(
        (
            results[
                "entity_match"
            ]
            == "AMBIGUOUS"
        ).sum()
    )

    unresolved_count = int(
        (
            results[
                "entity_match"
            ]
            == "UNRESOLVED"
        ).sum()
    )

    print(
        f"Ambiguous candidates requiring review: {ambiguous_count}"
    )

    print(
        f"Technical/unresolved candidates: {unresolved_count}"
    )

    print()
    print(
        "Recall is NOT reported because no complete ground-truth "
        "VAT dataset exists for the sample."
    )


# ============================================================================
# PRODUCTION VERIFICATION
# ============================================================================


def run_production() -> None:
    """
    Validate the real VAT candidate set against HMRC Production.
    """

    candidates = load_candidates()

    company_postcodes = (
        load_company_postcodes()
    )

    company_count = (
        candidates[
            "_company_number"
        ]
        .nunique()
    )

    pair_count = len(
        candidates
    )

    unique_vats = (
        candidates[
            "_candidate_vat_normalized"
        ]
        .nunique()
    )

    print(
        "=" * 70
    )

    print(
        "HMRC VAT VERIFICATION"
    )

    print(
        "=" * 70
    )

    print()

    print(
        "Environment: PRODUCTION"
    )

    print(
        f"Companies with candidates: {company_count}"
    )

    print(
        f"Company/VAT pairs: {pair_count}"
    )

    print(
        f"Unique VAT numbers: {unique_vats}"
    )

    print()

    print(
        "WARNING:"
    )

    print(
        "Production requests query HMRC's real VAT service."
    )

    print(
        "Only run this mode using approved HMRC production credentials."
    )

    print()

    print(
        "Requesting HMRC OAuth token..."
    )

    access_token = get_access_token()

    print(
        "Authentication successful."
    )

    # --------------------------------------------------------------
    # Resume support
    # --------------------------------------------------------------

    existing = (
        load_existing_production_results()
    )

    existing_keys: set[str] = set()

    rows: list[dict[str, Any]] = []

    if not existing.empty:

        rows = existing.to_dict(
            orient="records"
        )

        for _, row in existing.iterrows():

            existing_keys.add(
                result_key(
                    row.get(
                        "company_number",
                        "",
                    ),
                    row.get(
                        "candidate_vat",
                        "",
                    ),
                )
            )

        print(
            f"Resume: loaded {len(existing)} existing "
            "production results."
        )

    print()

    for index, (_, row) in enumerate(
        candidates.iterrows(),
        start=1,
    ):

        company_number = safe_string(
            row[
                "_company_number"
            ]
        )

        company_name = safe_string(
            row[
                "_company_name"
            ]
        )

        sample_id = safe_string(
            row[
                "_sample_id"
            ]
        )

        vat = normalize_vat(
            row[
                "_candidate_vat_normalized"
            ]
        )

        key = result_key(
            company_number,
            vat,
        )

        if key in existing_keys:

            print(
                f"[{index}/{pair_count}] "
                f"GB{vat} - already verified in PRODUCTION"
            )

            continue

        postcode = (
            company_postcodes.get(
                company_number.upper(),
                "",
            )
        )

        print(
            f"[{index}/{pair_count}] {company_name}"
        )

        print(
            f"  Company number: {company_number}"
        )

        print(
            f"  Candidate VAT:  GB{vat}"
        )

        hmrc_result = (
            verify_vat_with_hmrc(
                vat,
                access_token,
            )
        )

        (
            entity_match,
            name_similarity,
            postcode_match,
        ) = classify_entity_match(
            company_name=company_name,
            company_postcode=postcode,
            hmrc_result=hmrc_result,
        )

        output_row = {
            "environment": "production",
            "sample_id": sample_id,
            "company_number": company_number,
            "company_name": company_name,
            "companies_house_postcode": postcode,
            "candidate_vat": format_vat(
                vat
            ),
            "hmrc_status": hmrc_result[
                "hmrc_status"
            ],
            "hmrc_http_status": hmrc_result[
                "hmrc_http_status"
            ],
            "hmrc_name": hmrc_result[
                "hmrc_name"
            ],
            "hmrc_vat_number": hmrc_result[
                "hmrc_vat_number"
            ],
            "hmrc_address": hmrc_result[
                "hmrc_address"
            ],
            "hmrc_postcode": hmrc_result[
                "hmrc_postcode"
            ],
            "hmrc_country_code": hmrc_result[
                "hmrc_country_code"
            ],
            "hmrc_processing_date": hmrc_result[
                "hmrc_processing_date"
            ],
            "name_similarity": round(
                name_similarity,
                4,
            ),
            "postcode_match": (
                ""
                if postcode_match is None
                else postcode_match
            ),
            "entity_match": entity_match,
            "hmrc_error": hmrc_result[
                "hmrc_error"
            ],
        }

        rows.append(
            output_row
        )

        print(
            "  HMRC status: ",
            hmrc_result[
                "hmrc_status"
            ],
        )

        if hmrc_result[
            "hmrc_name"
        ]:

            print(
                "  HMRC name:    ",
                hmrc_result[
                    "hmrc_name"
                ],
            )

        if hmrc_result[
            "hmrc_postcode"
        ]:

            print(
                "  HMRC postcode:",
                hmrc_result[
                    "hmrc_postcode"
                ],
            )

        if (
            hmrc_result[
                "hmrc_status"
            ]
            == "VALID"
        ):

            print(
                "  Name score:   ",
                f"{name_similarity:.3f}",
            )

        print(
            "  Entity result:",
            entity_match,
        )

        if hmrc_result[
            "hmrc_error"
        ]:

            print(
                "  Error:",
                hmrc_result[
                    "hmrc_error"
                ][:300],
            )

        print()

        # ----------------------------------------------------------
        # Save after every request.
        #
        # If execution is interrupted, already checked candidates
        # will not need to be queried again.
        # ----------------------------------------------------------

        output_df = pd.DataFrame(
            rows
        )

        output_df.to_csv(
            PRODUCTION_OUTPUT_FILE,
            index=False,
        )

        existing_keys.add(
            key
        )

        # A small delay keeps this PoC deliberately conservative.
        time.sleep(
            0.25
        )

    results = pd.DataFrame(
        rows
    )

    print_production_metrics(
        results=results,
        total_sample_size=200,
    )

    print()
    print(
        "Results saved to:"
    )

    print(
        PRODUCTION_OUTPUT_FILE
    )

    print()

    print(
        "IMPORTANT:"
    )

    print(
        "Review all AMBIGUOUS rows manually before publishing "
        "the final verified dataset."
    )


# ============================================================================
# MAIN
# ============================================================================


def main() -> None:

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if HMRC_ENV == "sandbox":

        run_sandbox()

        return

    if HMRC_ENV == "production":

        run_production()

        return

    raise RuntimeError(
        f"Unsupported HMRC_ENV: {HMRC_ENV}"
    )


if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "\nExecution interrupted by user."
        )

        sys.exit(
            130
        )

    except Exception as exc:

        print()
        print(
            "=" * 70
        )

        print(
            "ERROR"
        )

        print(
            "=" * 70
        )

        print(
            str(exc)
        )

        sys.exit(
            1
        )