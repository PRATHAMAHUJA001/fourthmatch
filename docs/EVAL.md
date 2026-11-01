# Evaluation — policy compiler & decision accuracy

Scores are produced by `backend/tests/test_accuracy.py` over all 12 seeded
cases in `data/ground_truth.json`. A case is correct only if **verdict AND
at_risk_paise** both match the answer key. Two scores are reported:

- **Decision accuracy** — `domain/decision.py` + hand-written reference rules.
  Was 12/12 before this pass and remains **12/12**: the decision function and
  the payable-quantity rule were never the problem.
- **Compiler accuracy** — `domain/decision.py` + rules the model actually
  compiled from the committed policy, read only from the compiler cache
  (populated by `scripts/compile_policy_cache.py`). This is the score below.

## Before this pass: 8/12

Compiled rules in cache: 4 valid (`5.1-2`, `5.2-1`, `5.3`, `6.1`).

Rule-level metrics vs the 7 reference rules:

- matched: REF-5.1, REF-5.2, REF-5.3, REF-6.1
- missing: **REF-4.2-cartons, REF-4.2-bagged, REF-4.2-steel** (all of clause 4.2)
- extra: none

Mismatches (all `approve ₹0` vs expected `partial_pay`): scn2_short (₹1,100),
scn4_mixed (₹1,900), grn_short_beyond_tolerance (₹6,300),
invoice_qty_exceeds_grn (₹12,20,000). Every failure traced to the missing
4.2 rules — no other clause was implicated.

## Finding: clause 4.2 was underspecified in the input

The committed 4.2 stated the tolerances and that shortage beyond tolerance
"shall require review and approval in line with sign-off limits before
closure of the Goods Receipt Note" — a **GRN review consequence only**. It
never stated a **payment consequence**, so the compiler had nothing in the
text to compile a payment rule from. The template's intent (per the
reference rules) is partial payment: pay for what was received, withhold the
shortfall. The model cannot be expected to invent that, and the compiler
prompt was deliberately **not** given any 4.2- or GRN-specific hint.

## Fix (input, not compiler)

- `backend/app/seed/policy_template.py`: canonical 4.2 now states both —
  shortage beyond tolerance requires **Stores Manager review before GRN
  closure**, **and payment is released only for quantity received within
  tolerance, with the shortfall value withheld pending that review**.
  Numbers unchanged (cartons 0.0%, bagged material 2.0%, steel coils 0.0%),
  so no ground-truth verdict or tolerance moved.
- Regenerated only clause 4.2:
  `scripts/generate_policy.py --clause 4.2` (new single-clause mode; all
  other clauses keep their committed prose — the git diff shows only the
  4.2 paragraph). Verified: `check_policy` passes on the whole file and
  4.2's extracted numbers equal the template set `{0.0, 2.0}`.

## Also in this pass: validator-feedback retry

When a compiled rule fails strict Python validation, the compiler now sends
the original clause, the rejected rules and the validator's errors back to
the model **once** (generic prompt, no clause-specific instructions), and
reports the retry count in compile results (`retries` on
`PolicyCompileResult` / `DraftCompileResult` / simulation draft). Both
attempts are ordinary model calls and are logged in `model_calls`. The
offline scorer reconstructs the same retry cache key, so scored rules are
the ones the service would actually use.

In the live re-run (`compiled=3` new calls, `cache_hits=63`, `retries=1`,
`invalid=0`), the retry fired on clause **5.1**, whose first attempt emitted
a `require_signoff` rule with no `signoff_role`; the retry supplied one
(`manager`) and the rule became valid. Clause 4.2 itself compiled cleanly
on the first attempt. `decide_line` also now handles a `require_signoff`
and a `partial_pay` rule firing on the same line (verdict `partial_pay`,
only the disputed portion held, signoff role recorded on the verdict) —
unit-tested; in this run the model compiled 4.2 as three per-category
`partial_pay` rules and did not split out a signoff rule.

## After this pass: 10/12

Compiled rules in cache: 8 valid. Rule-level metrics:

- matched: **all 7 reference rules** (REF-4.2 ×3 now included)
- missing: none
- extra: `5.1-1` (`price_variance_pct <= 2.0 → require_signoff`)

Remaining mismatches, both caused by the extra rule `5.1-1` — the rule the
new retry rescued:

- scn1_clean: `human_review` (held ₹6,600) vs expected `approve` — a
  within-tolerance price variance now triggers signoff on a clean delivery.
- scn4_mixed: `human_review` (held ₹4,100, at_risk ₹1,900 ✓) vs expected
  `partial_pay` — the signoff line outranks the partial-pay line at
  delivery level.

Total at_risk across all 12 cases now equals the reference-rules total
(₹18,42,370); only the verdict on those two cases differs. Recorded as a
finding, not tuned away: clause 5.1's "may be accepted with approval as per
sign-off limits" can legitimately be read either way, and the retry
mechanism correctly reports what the model produced. Ground truth and
expected verdicts were not edited to move this score.
