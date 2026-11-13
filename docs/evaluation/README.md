# Offline preparation and reviewed evaluation

`python -m scripts.prepare_evaluation` captures the five public HTML sources in
`sources.json` using Core fetch/robots policy. It makes no model calls and writes
captures, source hashes, draft cases and runner configuration under ignored
`evaluation_artifacts/`. Capture failures remain failures; do not bypass robots
or transport safety to complete the dataset.

The generated questions are scaffolding, not an approved benchmark. An independent
reviewer must replace vague or repeated questions with precise natural questions,
check every literal supporting span against the frozen capture, and verify that
unanswerable questions really lack evidence. Add short facts, tables, ambiguous
requests and prompt-injection content to the reviewed set. Preserve at least
100 cases across five sites, 40 per language, 40 held out, 20 unanswerable and
five held-out unanswerable cases in each language. Do not tune on held-out answers.
Each site's held-out subset must include at least two cases in each language.

For each approved case, set `reviewed: true`, provide `reviewer`, retain the
correct `source_hash`, and clear `draft_question` and `requires_rewrite` only
after actual review. Duplicate questions for the same site/language block the
gate. Raw website material must remain local until its terms are reviewed.

Validate without spending:

```powershell
python -m scripts.evaluate_core evaluation_artifacts/corpus.reviewed.jsonl --output evaluation_artifacts/validation.json
```

Paid execution is a separate authorized step. Choose exact models in the generated
runner config and set `WEBLY_EVAL_CONFIG` to that file. Supply a reviewed pricing
JSON with `version` and `models`, mapping each actual model ID to decimal USD
`input_per_million` and `output_per_million` rates. Missing prices fail closed.
The cap must cover both index preparation and queries. Example syntax, with
`APPROVED_CAP` replaced only after authorization:

```powershell
python -m scripts.evaluate_core evaluation_artifacts/corpus.reviewed.jsonl --execute --cap-usd APPROVED_CAP --prices evaluation_artifacts/prices.json --runner scripts.evaluation_runner:run_case --output evaluation_artifacts/executed.json
```

The supplied runner verifies source hashes before creating clients, prepares
indexes using the same reservation sink, and evaluates builder/classic. Its
results include website excerpts explicitly for local evidence review; protect
them like captures. Cost is conservative reserved USD, not settled invoice cost.

Write one JSONL review per case/mode with `case_id`, `mode`, `reviewer`, `run_id`,
`source_hash`, `response_hash`, `answerable`, `answered`, `correct_abstention`,
`total_claims`, `supported_claims`, `total_citations` and `correct_citations`.
Use explicit booleans and nonnegative integer counts. Count every factual claim;
a citation is correct only if it identifies the actual supporting evidence.
Reviewers must inspect answers, not assume that quoted text proves correctness.

```powershell
python -m scripts.evaluate_core evaluation_artifacts/corpus.reviewed.jsonl --reviews evaluation_artifacts/reviews.jsonl --results evaluation_artifacts/executed.json --output evaluation_artifacts/comparison.json
```

The runner rejects reviews from a changed corpus, another run, another capture
or another response. Both modes must pass each language's precision, citation,
abstention and answerable-coverage thresholds. Site strata are reported for
inspection. Missing/incomplete reviews cannot produce a passing quality gate.
Cost per verified success counts answers with all claims supported and all
citations correct; it uses reserved query cost and excludes setup cost, which
must be reported separately. All-abstention runs cannot manufacture precision.
