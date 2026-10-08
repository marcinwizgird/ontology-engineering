"""The maturity and SIP-stage groupings cover the catalogue and respect its ordering rules."""

from validation_agent.engine.registry import describe
from validation_agent.spec import check_catalogue as cat

LEVELS = [m.code for m in cat.MATURITY_LEVELS]
STAGES = [s.code for s in cat.SIP_STAGES]


def test_every_check_has_one_level_and_one_stage():
    ids = {c.id for c in cat.CHECKS}
    assert set(cat.MATURITY_OF) == ids
    assert set(cat.SIP_STAGE_OF) == ids


def test_instance_data_checks_start_at_populate_or_later():
    for c in cat.CHECKS:
        if "abox" in c.applies:
            assert STAGES.index(c.sip_stage) >= STAGES.index("populate"), c.id


def test_dl_reasoner_checks_are_not_enabled_below_m4():
    for c in cat.CHECKS:
        if c.stage == "S1c":
            assert LEVELS.index(c.maturity) >= LEVELS.index("M4"), c.id


def test_gate_is_derived_from_stage_and_severity():
    assert cat.CHECK_BY_ID["SYN-01"].gate == "review"
    assert cat.CHECK_BY_ID["ABOX-04"].gate == "publish"
    assert cat.CHECK_BY_ID["METRIC-02"].gate == "advisory"


def test_domain_ontology_track_starts_the_ladder():
    assert all(c.track == "domain" for c in cat.CHECKS if c.maturity == "M1")


def test_describe_exposes_groupings():
    d = describe("RSN-02")
    assert (d["maturity"], d["sip_stage"], d["gate"], d["track"]) == ("M4", "model", "review", "domain")
