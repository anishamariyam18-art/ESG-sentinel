"""Evaluation harnesses (Phase 10 sections 27-31).

Two gold-standard classification test sets:

- `gold_verification`: claim/evidence pairs with an expected
  `VerificationStatus`, evaluated against Phase 6's deterministic
  consistency-checking core (no LLM call -- see that module's docstring for
  exactly what is and isn't exercised).
- `gold_greenwashing`: claims with an expected primary `GreenwashingType`,
  evaluated against Phase 7's actual, already-100%-deterministic
  classification logic directly.

`metrics` computes accuracy/precision/recall/F1/confusion-matrix for
either. Every reported number is an ordinary classification metric over a
small, hand-labeled SYNTHETIC dataset -- never a claim of real-world
accuracy, scientific validity, or "guaranteed" detection (section 47).
"""
