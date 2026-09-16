# UK VAT Identifier Discovery

Take-home assignment for the Data Assets Internship.

The goal of this project was to see whether UK VAT numbers can be discovered reliably from public web sources when the starting point is a Companies House company.

The main constraint is that HMRC's VAT checker works in one direction: if you already have a VAT number, you can check it, but you cannot search for a VAT number using a company name. This means that discovery has to happen somewhere else, while HMRC can be used as the final verification step.

I tested this on a random sample of 200 active Companies House entities.

## Results

The final pipeline looked like this:

```text
200 sampled companies
        |
        v
open-web discovery
        |
        v
101 VAT candidates
        |
        v
local evidence filtering
        |
        v
33 candidates
        |
        v
HMRC verification
        |
        +---- 21 correct company/VAT matches
        +---- 11 valid VATs, but wrong company
        +----  1 invalid VAT
```

| Metric                                     | Result |
| ------------------------------------------ | -----: |
| Companies sampled                          |    200 |
| Companies with a candidate after filtering |     24 |
| VAT candidates checked                     |     33 |
| Valid VAT numbers                          |     32 |
| Correct company/VAT matches                |     21 |
| Valid VATs belonging to another company    |     11 |
| Invalid VATs                               |      1 |
| Candidate precision                        | 63.64% |
| Candidate false-positive proportion        | 36.36% |
| Verified sample coverage                   | 10.50% |

The result I found most interesting was that **32 of the 33 candidates were real VAT numbers, but only 21 actually belonged to the company I was looking for**.

So checking whether a VAT number is valid is not enough. The harder part is deciding whether that VAT number belongs to the correct legal entity.

---

## Sources I looked at

### HMRC VAT checker

https://www.gov.uk/check-uk-vat-number

This is the authoritative source I used for final verification.

It can tell whether a supplied VAT number is registered and provides information about the registered business. It cannot be used to search by company name, so I did not use it for discovery.

### Companies House

https://download.companieshouse.gov.uk/en_output.html

I used Companies House as the starting point for company identity and sampling.

The basic company dataset contains company number, legal name, status, address, incorporation date, SIC codes and other company information, but it does not contain a structured VAT-number field.

### HMRC non-financial VAT registration data

https://www.gov.uk/guidance/apply-to-receive-non-financial-vat-registration-data-from-hmrc

HMRC has a much more interesting dataset for a production version of this project. It includes VAT registration information and company identifiers.

I did not use it for the PoC because access is restricted and it is not an open-web dataset.

### Company websites and public documents

I searched company websites, PDFs and public documents for patterns such as:

```text
VAT No
VAT Number
VAT Reg No
VAT Registration Number
GB123456789
```

Pages such as contact, terms, legal and privacy pages were useful places to look.

Public procurement documents can also contain company names, company numbers and VAT numbers in the same document, which makes them useful candidate sources.

### Datalog

https://www.datalog.co.uk/vat_numbers.php

Datalog was useful because some pages contain a company name, company number and VAT number.

I treated these as candidates rather than verified mappings. I could not establish enough about provenance, completeness and freshness to use Datalog as ground truth.

### VAT Lookup

https://www.vat-lookup.co.uk/

This was another useful discovery source. However, the site says that it cross-checks information with Datalog, so I did not count agreement between the two sites as independent confirmation.

---

## Building the sample

I used:

```text
BasicCompanyDataAsOneFile-2026-09-01.zip
```

from Companies House.

The sampling steps were:

1. keep companies with `CompanyStatus == Active`;
2. exclude records explicitly categorised as dormant;
3. randomly sample 200 companies;
4. use seed `20260914`;
5. freeze the sample before doing any VAT searches.

After filtering, the sampling population contained 4,605,858 Companies House entities.

I froze the sample before discovery because I did not want search results to influence which companies ended up in the PoC.

The sample is intended to represent active, non-explicitly-dormant Companies House entities. It should not be treated as a representative sample of the client's actual supplier population. Suppliers may differ in turnover, industry, age, VAT-registration rate and web presence.

### Quick sample check

I compared some characteristics of the sample with the full eligible population.

| Attribute       | Population | Sample |
| --------------- | ---------: | -----: |
| Private Limited |     91.91% | 91.50% |
| MICRO accounts  |     36.23% | 34.50% |
| No accounts     |     29.26% | 32.00% |
| Age 3–10 years  |     32.85% | 33.00% |
| Age <1 year     |     16.68% | 19.00% |

I did not reroll the sample after looking at these results.

### One Companies House data issue

While reading the bulk CSV I found at least one malformed row: it contained 56 fields while the expected schema contained 55.

I chose to skip structurally malformed rows instead of trying to repair them automatically. A guessed repair could shift fields and, more importantly, corrupt the company number used for entity matching.

---

## VAT discovery

For each company I ran several search variations using:

* company number;
* company name;
* company name + postcode;
* Datalog-specific searches;
* VAT Lookup-specific searches.

The full discovery run produced:

| Metric                              | Result |
| ----------------------------------- | -----: |
| Companies processed                 |    200 |
| Queries executed                    |  1,398 |
| Queries with results                |    686 |
| Queries with no results             |    296 |
| Technical failures                  |    416 |
| Search results seen                 |  2,402 |
| Documents fetched                   |  1,015 |
| Companies with an initial candidate |     26 |
| Unique VAT candidates               |    101 |
| Candidate evidence rows             |    105 |

One thing I kept separate was `NO_RESULTS` from technical failures.

416 of the 1,398 searches failed technically, around 29.8%. A failed search obviously should not be interpreted as evidence that a VAT number does not exist.

---

## A mistake in the first version

My first entity-matching rule was too loose.

If a page contained the target company and also contained a VAT number, I initially treated that VAT as a possible match.

That works reasonably on a company-specific page, but fails badly on directory and postcode pages containing many companies.

For example:

| Company                            | VAT candidates produced |
| ---------------------------------- | ----------------------: |
| MADE REAL LTD                      |                      22 |
| BIRCHWOOD CLADDING SYSTEMS LIMITED |                      21 |
| EARLY RISE SCAFFOLDING LIMITED     |                      11 |
| FRESHBUILD LIMITED                 |                      11 |
| JUST DESIGNER BRANDS LIMITED       |                      11 |
| M & A BRANDS LTD                   |                       6 |

These six companies alone generated 82 of the 101 VAT candidates.

So I changed the rule.

Instead of checking whether the company appeared somewhere on the page, I checked whether the company number or company name appeared in the local text around the VAT number.

That changed the results from:

```text
101 unique VAT candidates
105 evidence rows
```

to:

```text
33 unique VAT candidates
36 evidence rows
24 companies
```

69 of 105 evidence rows were rejected.

I kept both the original and filtered candidate files in the repository because this failure was useful: it showed why page-level co-occurrence is not enough for entity matching.

---

## HMRC verification

I manually checked all 33 remaining candidates using the production HMRC VAT checker.

For every candidate I recorded:

* whether the VAT was registered;
* the business name returned by HMRC;
* whether that business matched the Companies House entity.

I used four statuses:

```text
VERIFIED_MATCH
VALID_WRONG_ENTITY
INVALID
AMBIGUOUS
```

The result was:

| Status             | Count |
| ------------------ | ----: |
| VERIFIED_MATCH     |    21 |
| VALID_WRONG_ENTITY |    11 |
| INVALID            |     1 |
| AMBIGUOUS          |     0 |

This gives:

```text
VAT validity:        32 / 33 = 96.97%
Candidate precision: 21 / 33 = 63.64%
Wrong entity:        11 / 32 = 34.38% of valid VATs
```

For this PoC I define the candidate false-positive proportion as candidates that were either invalid or belonged to another company:

```text
(11 + 1) / 33 = 36.36%
```

I call this a candidate false-positive proportion rather than a strict statistical false-positive rate because I do not have a known population of true negatives.

---

## Examples of wrong matches

These were useful for understanding where the remaining errors came from.

### JUST DESIGNER BRANDS LIMITED

| Candidate   | HMRC business            | Result  |
| ----------- | ------------------------ | ------- |
| GB117513828 | JANAN LTD                | Wrong   |
| GB324864588 | CAFE JANAN LIMITED       | Wrong   |
| GB325056719 | JUST DESIGNER BRANDS LTD | Correct |

### M & A BRANDS LTD

| Candidate   | HMRC business               | Result  |
| ----------- | --------------------------- | ------- |
| GB160418335 | E1 PRINTING LIMITED         | Wrong   |
| GB175765957 | LASTMINUTEPRINT.COM LIMITED | Wrong   |
| GB360448307 | M & A BRANDS LTD            | Correct |

Another interesting case was:

```text
Target:
D & R BUILDING LIMITED

Candidate:
GB128383111

HMRC business:
D & R BUILDING MAINTENANCE LTD
```

The names look related, but they are not the same legal entity.

This is why I would not use fuzzy company-name similarity alone to accept a VAT mapping.

---

## Coverage

21 of the 200 sampled companies ended with a verified VAT mapping:

```text
21 / 200 = 10.5%
```

24 companies had at least one candidate after filtering:

```text
24 / 200 = 12.0%
```

And 21 of those 24 companies eventually produced a verified mapping:

```text
21 / 24 = 87.5%
```

The **10.5% figure is coverage, not recall**.

I do not know how many of the other 179 companies are actually VAT registered. There is no complete public ground-truth dataset against which I can measure that.

For the same reason, I would store a failed discovery as:

```text
NOT_FOUND
```

not:

```text
NOT_VAT_REGISTERED
```

---

## What did not work well

A few approaches were useful experiments but would not be good final solutions.

| Approach                               | What happened                                  |
| -------------------------------------- | ---------------------------------------------- |
| HMRC for discovery                     | Requires the VAT number first                  |
| Companies House VAT lookup             | No structured VAT field                        |
| General search                         | Useful, but unstable                           |
| Page-level matching                    | Produced heavy cross-company contamination     |
| Name-only matching                     | Similar company names caused wrong matches     |
| Datalog as ground truth                | Provenance/freshness not strong enough         |
| VAT Lookup as independent confirmation | It references Datalog                          |
| HMRC Sandbox for real VAT checks       | Sandbox uses mock data                         |
| Checking only VAT validity             | Real VAT can still belong to the wrong company |

### HMRC Sandbox

I initially tried the real candidates against the HMRC API Sandbox and all of them appeared invalid.

That looked suspicious, so I checked the API documentation and test data. The Sandbox uses mock VAT records and is intended for integration testing.

I discarded those results.

The Sandbox code remains useful for testing authentication/API integration, but none of the final PoC quality metrics are based on Sandbox responses.

---

# What I would build with real resources

I would not scale the PoC by simply running seven web searches for every UK company.

At the PoC rate:

```text
1,398 / 200 = ~6.99 queries/company
```

Across 4.2 million companies this would mean roughly:

```text
~29.4 million searches
```

before retries.

Instead, I would use a waterfall:

```text
existing client data
        |
        v
structured / licensed sources
        |
        v
Companies House entity normalisation
        |
        v
official company website
        |
        v
legal / contact / terms pages
        |
        v
public PDFs and documents
        |
        v
web search for unresolved companies
        |
        v
candidate extraction
        |
        v
HMRC verification
        |
        v
entity matching
        |
        +--> accept
        +--> review
        +--> reject
```

Search would be a fallback rather than the first step.

For entity matching I would roughly prioritise evidence in this order:

```text
exact company number
        >
legal name + postcode/address
        >
strong legal-name match + address
        >
company name only
```

The PoC showed that name-only evidence is too weak for automatic acceptance.

---

## Scaling estimates

If the observed 10.5% verified coverage were mechanically applied to 4.2 million companies:

```text
4,200,000 * 10.5% = ~441,000 mappings
```

I would **not** treat this as a forecast. It is only useful as a workload/scenario calculation because the 200-company sample is small and does not represent the client's supplier population.

The more useful commercial starting point is the client's 40,000 suppliers.

If around one third already have VAT numbers:

```text
~13,333 already known
~26,667 unresolved
```

Applying 10.5% only as an illustrative scenario would give:

```text
~2,800 additional mappings
```

Again, this is not an expected production result. Procurement suppliers could have very different VAT-registration and web-presence characteristics from the Companies House sample.

I would test the production approach on these 26,667 unresolved suppliers before considering a national dataset.

---

## Production data model

I would keep more than just:

```text
company_number, vat_number
```

A verified mapping should also have enough information to explain where it came from:

```text
company_number
vat_number
source_url
source_type
evidence_text
source_retrieved_at
hmrc_registered_name
hmrc_registered_address
hmrc_checked_at
verification_status
confidence
first_seen
last_seen
last_verified
```

This matters because VAT mappings can become stale and web sources can disappear or change.

---

## Human review

I would automatically accept only strong matches.

For example:

**High confidence**

```text
exact company number close to VAT
+
HMRC entity matches target
```

→ auto-accept

**Medium confidence**

```text
strong legal name
+
matching postcode/address
+
HMRC approximately matches
```

→ review

**Low confidence**

```text
name only
multiple candidates
directory page
HMRC conflict
```

→ reject or review

This is preferable to trying to maximise coverage at the expense of incorrect company/VAT relationships.

---

# Freshness and monitoring

A mapping that was correct today should not automatically be considered correct forever.

I would store at least:

```text
first_seen
last_seen
source_retrieved_at
hmrc_checked_at
companies_house_checked_at
last_verified
```

and periodically reverify mappings.

If a previously verified VAT later becomes invalid, I would not immediately delete it. I would move it through something like:

```text
VERIFIED
   |
   v
SUSPECTED_STALE
   |
   v
RETRY
   |
   +--> VERIFIED
   +--> REMOVED / INACTIVE
```

This also avoids treating temporary HMRC/service issues as permanent changes.

---

## How I would detect bad data without a benchmark

There is no complete public benchmark, so I would monitor the behaviour of the pipeline itself.

Some useful metrics are:

```text
HMRC validity rate
entity-match precision
wrong-entity rate
candidates/company
precision by source
search/fetch failure rate
age since last verification
manual review rate
```

The PoC gives useful initial baselines:

| Metric                        |    PoC |
| ----------------------------- | -----: |
| HMRC validity                 | 96.97% |
| Candidate precision           | 63.64% |
| Wrong entity among valid VATs | 34.38% |
| Search technical failure      | 29.76% |

For example, if one source suddenly starts producing ten VAT candidates per company instead of one, I would suspect a parser or directory-page problem before publishing those mappings.

I would also manually check a small random sample of published mappings on a regular basis. It should be random rather than consisting only of suspicious records, otherwise the precision estimate would be biased.

---

# Checksum and brute force

A UK VAT checksum is useful as a cheap plausibility check, but not much more.

Passing a checksum does not tell me:

* whether the VAT is registered;
* whether it is still active;
* which company owns it.

The PoC is a good example of this problem. Almost every candidate was a real VAT number, but 11 valid numbers belonged to another company.

I would therefore use checksum validation only as an optional filter before HMRC verification.

I would not try to discover VAT numbers by generating possible numbers and brute-forcing the HMRC checker. Apart from the volume and rate-limit/acceptable-use problems, finding a valid number still would not tell me which company it belongs to.

---

# Sources I would be uncomfortable relying on commercially

There are some approaches that might improve short-term coverage but that I would avoid building a product around:

* scraping search engines aggressively;
* rotating proxies mainly to evade blocking;
* CAPTCHA bypass;
* datasets with unclear reuse rights;
* sources with unknown provenance;
* directories where I cannot establish how the VAT data was obtained.

I would rather accept slightly lower coverage and use official sources, company websites, licensed search/data products and evidence that can be traced back to its origin.

For this type of dataset, provenance is part of data quality.

---

# Optional comparison: Germany

The same general pipeline could be used in Germany.

The relevant VAT identifier is the **Umsatzsteuer-Identifikationsnummer (USt-IdNr.)**, normally:

```text
DE + 9 digits
```

The legal-entity side is different from Companies House and would use the Unternehmensregister/commercial registers.

For discovery, I would prioritise:

```text
official company website
Impressum
legal/contact pages
company reports
Unternehmensregister documents
targeted search
```

Search terms would include:

```text
USt-IdNr.
USt-ID
Umsatzsteuer-ID
Umsatzsteuer-Identifikationsnummer
```

For verification, VIES/BZSt can be used.

The main lesson from the UK PoC still applies: checking that a VAT identifier is valid and checking that it belongs to the intended legal entity are two different steps.

So the German version would still look roughly like:

```text
company
   |
   v
VAT discovery
   |
   v
DE candidate
   |
   v
VIES / BZSt
   |
   v
entity match
   |
   +--> verified
   +--> review/reject
```

---

# Repository

```text
vat-identifier-discovery/
|
├── README.md
├── requirements.txt
├── .gitignore
|
├── data/
│   ├── raw/
│   │   └── README.md
│   │
│   └── processed/
│       ├── sample_companies.csv
│       ├── sampling_stats.txt
│       ├── sample_validation.txt
│       ├── vat_candidates.csv
│       ├── discovery_log.csv
│       ├── candidate_audit_summary.csv
│       ├── candidate_audit_detail.csv
│       ├── vat_candidates_filtered.csv
│       ├── vat_candidates_rejected.csv
│       ├── hmrc_manual_verification.csv
│       ├── verified_company_vat.csv
│       └── evaluation_metrics.json
|
├── evidence/
│   └── README.md
|
└── src/
    ├── 01_build_sample.py
    ├── 02_validate_sample.py
    ├── 03_discover_vat.py
    ├── 035_audit_candidates.py
    ├── 036_filter_local_evidence.py
    ├── 04_hmrc_verify.py
    ├── 041_save_manual_hmrc.py
    └── 05_evaluate_results.py
```

The raw Companies House snapshot is not committed because of its size.

Intermediate files are intentionally kept. In particular, I kept the original 101 candidates instead of only keeping the final successful mappings because they show how and why the entity-matching approach changed.

---

# Running it

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Download the Companies House snapshot and place it under `data/raw/`.

Build and validate the sample:

```bash
python src/01_build_sample.py
python src/02_validate_sample.py
```

Run discovery:

```bash
python src/03_discover_vat.py
```

Audit and filter the candidates:

```bash
python src/035_audit_candidates.py
python src/036_filter_local_evidence.py
```

Save the manually checked HMRC results and calculate the final metrics:

```bash
python src/041_save_manual_hmrc.py
python src/05_evaluate_results.py
```

`04_hmrc_verify.py` contains the HMRC API integration/testing work. Sandbox responses are not used for the final PoC metrics.

The final verified mappings are in:

```text
data/processed/verified_company_vat.csv
```

The complete HMRC verification trail, including rejected candidates, is in:

```text
data/processed/hmrc_manual_verification.csv
```

---

# Limitations

There are several limitations to keep in mind:

* the sample contains only 200 companies;
* it is a Companies House sample, not a sample of the client's actual suppliers;
* sole traders are outside the sampling frame;
* web discovery is incomplete and non-deterministic;
* search failures affected discovery;
* no result does not mean the company is not VAT registered;
* there is no complete public benchmark, so I cannot measure recall;
* the 33 final candidates were checked manually against the production HMRC checker;
* websites, source data and VAT registrations change over time.

For these reasons, the 10.5% verified coverage is a result of this PoC, not an estimate of the percentage of UK companies with VAT numbers.

---

# Conclusion

The PoC started with 200 companies and ended with 21 verified company-to-VAT mappings.

The useful part was what happened in between:

```text
200 companies
    ↓
101 raw candidates
    ↓
33 after local evidence filtering
    ↓
32 real VAT registrations
    ↓
21 belonging to the correct company
```

My initial assumption was that finding valid VAT numbers would be the difficult part. The results suggest otherwise.

Almost all of the final candidates were valid VAT numbers. The bigger problem was deciding whether a valid VAT number actually belonged to the company I was trying to identify.

That changes how I would build the production system.

I would favour a smaller number of high-confidence mappings over a larger dataset containing uncertain company/VAT relationships. Companies House would provide the entity backbone, open-web sources would generate candidates, and HMRC plus entity matching would act as the final gate before a mapping is published.

For the original procurement use case, I would first run this pipeline against the approximately 26,700 suppliers currently missing VAT numbers and measure its performance there before attempting to build a complete UK-wide dataset.
