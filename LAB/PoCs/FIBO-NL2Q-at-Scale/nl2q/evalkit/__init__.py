"""The evaluation framework of ``docs/nl2q_evaluation_specification.md`` (EVAL-SPEC-NL2Q V3).

* ``statistics`` — the analysis plan (§5.5): gold-query cluster bootstrap, repeated runs,
  McNemar on majority outcomes, minimum detectable effect, Holm correction;
* ``slices``     — structural slice tags derived from the gold SPARQL and the schema (§4.4);
* ``scoring``    — Gate 4 metrics: outcome states, utility with floor and components,
  refusal metrics at a stated prevalence, stability, cost per correct answer;
* ``scorecard``  — the per-campaign scorecard (§6) as JSON and Markdown.

Stages and status: specification §8.
"""
