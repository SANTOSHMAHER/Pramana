# Pramana Dataset Guide

This document describes the chatbot's FAQ data, how the application consumes
it, and how to update it without introducing unsupported answers.

## Dataset files

| File | Purpose | Runtime behavior |
|---|---|---|
| `database/test.json` | Curated FAQ used by the current chatbot | Used for exact answers and semantic retrieval, including curated local information |
| `database/data_address.json` | Older FAQ collection plus the verified local directory | General FAQ intents may be retrieved. Legacy local intents remain excluded; only entries in `verified_local_listings` with official source metadata are used for local answers |

Despite its name, `test.json` is the current curated runtime FAQ, not a test
results file. `data_address.json` also contains general technology, Python,
chatbot, and AI topics; it is not just an address list.

The FAQ datasets contain duplicate or overlapping tags and question wording.
Several entries may intentionally share a tag while having different questions
or answers. Do not remove or merge records based on tag or wording alone:
review their meaning and answers first. Exact identical answers are de-duplicated
for semantic retrieval.

## Verified local listings

`database/data_address.json` has a top-level `verified_local_listings` array.
Each item records a name, category, address, publicly listed phone number,
official source URL, and the date checked; BAMU department entries also
preserve the email address as displayed on BAMU's site. The application only
loads entries whose required fields are present and whose source URL is under
the official district public-utilities site or BAMU's official site. It
converts these records into exact-match and semantic-retrieval entries at
startup. Older local FAQ intents in the same file remain excluded.

The current data has 55 distinct listings from the official district
portal's hospitals, colleges/universities, municipalities, postal,
sub-divisional-office, and tahsil-office directories. Listings without a
published phone number were not included; repeated hospitals/colleges were
deduplicated. It also includes all 33 departments in the department table on
BAMU's official contact page, with the shared campus address and the phone
and email values listed there. The BAMU email spellings are preserved as
published (for example, `(AT)` and `(DOT)` obfuscations are not rewritten).
The directory pages may be updated by their publishers, so recheck the
sources before relying on time-sensitive contact details.

## Record format

Each dataset is a JSON object with an `intents` array. An intent record contains
these fields:

```json
{
  "tag": ["cloud_computing_intro"],
  "patterns": [
    "What is cloud computing?",
    "Explain cloud computing in simple terms."
  ],
  "responses": [
    "Cloud computing provides computing services over the internet."
  ],
  "context": [""]
}
```

- `tag`: one or more category labels. Tags are descriptive; they are not
  unique identifiers.
- `patterns`: example questions users might ask.
- `responses`: one or more candidate answers. The current app returns all
  distinct answers for ambiguous exact matches. During semantic generation,
  up to three responses from a retrieved entry may be supplied as context.
- `context`: legacy metadata. The current chatbot does not use this field for
  response generation.

Verified local directory entries use this separate top-level schema. `email`
is optional:

```json
{
  "name": "Example Public Hospital",
  "category": "hospital",
  "address": "Street address, Chhatrapati Sambhajinagar",
  "phone": "02400000000",
  "email": "office@example.org",
  "source_url": "https://chhatrapatisambhajinagar.maharashtra.gov.in/en/public-utility-category/hospitals/",
  "verified_on": "2026-11-05"
}
```

Keep the phone, address, source URL, and verification date together. Do not
add a record unless its official source lists an address and phone. For
department contacts, a shared campus address may apply to all departments;
retain it as such rather than implying separate street addresses. The runtime
generates question patterns and grounded answers from these fields and can
answer the explicit BAMU department-list query from all department records;
it does not treat the older local FAQ entries as verified.

Some older records in `data_address.json` use the singular key `response`
instead of `responses`. The app accepts either key. Prefer `responses` for new
or edited records.

## Writing and reviewing records

1. Add each new record to the `intents` array in `database/test.json`.
2. Use clear, natural question patterns with distinct phrasings. Avoid copying
   an existing pattern unless the new record is meant to provide an additional
   verified answer for that exact question.
3. Keep each answer self-contained and factual. Do not put an unresolved
   template such as `[office_name]` in a response; template responses are
   excluded from exact answers.
4. For local directory facts, add a record to `verified_local_listings` only
   after confirming the address and phone on an official source. Keep its
   source URL and verification date with the record. Do not add unverified
   local facts to legacy FAQ intents and expect the runtime to answer them.
5. Use JSON double quotes, escape embedded quotes, and check commas and closing
   brackets carefully. Keep the UTF-8 encoding.
6. Restart `python app.py` after saving changes. The in-memory answer and
   embedding indexes are built when the app starts.
7. Run the test suite:

   ```bat
   python -m unittest discover -s tests -v
   ```

## Runtime answer flow

1. The browser keeps the current chat in tab-scoped session storage and restores
   it after a page refresh. Starting a new chat clears that transcript. Each
   answer request includes up to the 40 most recent messages (20 exchanges),
   within a 7,500-character budget; the server validates their roles, order,
   and size before using them.
2. The input and stored patterns are normalized for Unicode, letter case, and
   punctuation. Exact curated matches return their stored, non-template
   responses.
3. If there is no exact answer, the app embeds the question with Ollama's
   `all-minilm` model, ranks stored question patterns by cosine similarity, and
   selects up to four entries. For a short follow-up, recent user questions
   are combined with it for retrieval so unresolved references remain attached
   to the current topic.
4. The selected questions and answers, plus validated conversation history,
   are passed to Ollama's
   `qwen2.5:1.5b` model as FAQ context for a composed answer. Duplicate
   responses are consolidated when selecting retrieval results.
5. Verified local listings in `data_address.json` are available for exact and
   semantic matching, with their official source and verification date
   included in the retrieved context. Unverified legacy local intents remain
   excluded. When a local-information question has no sufficiently relevant
   verified match, the app abstains.
6. General educational questions can still be answered from the language
   model's general knowledge. Those answers are generated, not verified by
   the FAQ.

Changing the FAQ updates what is retrieved; it does not train or fine-tune the
Qwen model. The first semantic request after a server restart builds the
in-memory vectors for question patterns. A missing Ollama service or model is
reported as a service error rather than silently returning an unrelated
answer.

## Current data observations

The counts below describe the dataset files inspected on 2026-11-05; they
change when records are added or removed.

| Dataset | Intent records | Question patterns | Answer texts | Response-key format |
|---|---:|---:|---:|---|
| `test.json` | 228 | 617 | 284 | All records use `responses` |
| `data_address.json` | 576 | 1,202 | 984 | 501 records use `responses`; 75 use legacy `response` |
| `data_address.json` verified local directory | 88 | Generated at startup | Generated at startup | 55 district listings plus 33 BAMU departments, all with official source and phone |

In the current loaded retrieval corpus, duplicate records are consolidated to
479 entries with 1,058 question patterns. The live runtime can also answer
exact patterns from the general, non-local entries in `data_address.json`.

These are structural counts, not a measure of factual accuracy or coverage.
Local information in particular should be rechecked before it is treated as
current.
