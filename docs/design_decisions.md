# Design Decisions

## Findings are always returned as a list

`deterministic_findings` in the API response is always a list, even when there is only one failure. A deterministic failure produces exactly one entry; an inconclusive result can produce many. Keeping the shape consistent means the API consumer never needs to branch on whether the field is an object or an array.

## Short-circuit on `failed`, collect on `inconclusive`

The rule engine stops immediately on the first `failed` result — one deterministic cause is sufficient and running further rules would be misleading. When a rule returns `inconclusive`, however, the engine continues and collects every unresolved finding before returning. Manual review requires all available signals, not just the first.

## Two levels of failure granularity: `rule_id` and `failure_categories`

Each finding carries a specific `rule_id` (e.g. `CARD_EXPIRY_FORMAT_INVALID`) and is also mapped to a broader `failure_category` (e.g. `ENTITLEMENT_NOT_VALID`). Multiple rule IDs can map to the same category. Callers that only need to route or display at a high level use categories; callers that need to act on a specific failure use `rule_id`.

## `UNCERTAIN` is a synthetic finding, not a special case

When all rules pass on a denied transaction, the engine injects a synthetic `UNKNOWN_FAILURE_REASON` finding rather than returning an empty list. This preserves the invariant that `deterministic_findings` is never empty and ensures the LLM always receives a finding to work from — no special-casing is needed anywhere downstream.

## The LLM is a language layer only

The LLM never determines the failure reason — the rule engine does that deterministically. Gemini only converts the structured findings produced by the engine into human-readable staff guidance and guest explanation. All analytical logic is testable and auditable independently of LLM availability.

## `requires_manual_review` is deterministic

The manual review flag is derived directly from rule results by the engine, not inferred by the LLM. It is identical whether the LLM responds successfully or the fallback fires.

## Card numbers are hashed before storage

`CARD_USAGE` stores SHA-256 hashes of card numbers (salted via `CARD_HASH_SALT`), not raw PANs. Visit limits can be enforced without the usage log ever holding a sensitive card number.

## Masking is independent of rule evaluation

Raw guest data flows through the rule engine untouched. Masking runs as a separate step after all rules complete and shares no state with the rule pipeline. This ensures masking can never affect a rule result.

## Short-circuit naturally limits LLM prompt size

Because the rule engine short-circuits on the first `failed` result, a deterministic failure always produces exactly one finding. The LLM prompt for the common case is therefore always minimal. Token use only scales up for inconclusive transactions, where every unresolved finding is needed for a complete manual review.

## LLM output is constrained to JSON only

The prompt instructs Gemini to respond in JSON only, with a fixed schema (`staff_guidance` and `guest_explanation`). This eliminates filler text, makes the response size predictable, and allows direct `json.loads` parsing without any natural-language post-processing. If either required field is absent, the response is rejected and the fallback fires.
