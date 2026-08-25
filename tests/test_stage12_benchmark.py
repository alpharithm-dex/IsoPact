from scripts.run_stage12_benchmark import make_cases, observe, property_tests, wilson


def test_stage12_ground_truth_is_balanced_versioned_and_held_out():
    cases = make_cases()
    assert len(cases) == 130
    assert sum(case.expected_validity == "VALID" for case in cases) == 66
    assert sum(case.expected_validity == "INVALID" for case in cases) == 64
    assert sum(case.split == "HELD_OUT" for case in cases) == 39
    assert all(case.seed and case.policy_version and case.rule_version for case in cases)


def test_stage12_observation_agrees_without_mutating_truth():
    cases = make_cases()
    truth_before = tuple(case.expected_validity for case in cases)
    observed = [observe(case) for case in cases]
    assert tuple(case.expected_validity for case in cases) == truth_before
    assert all(result["observed_validity"] == case.expected_validity for case, result in zip(cases, observed))


def test_stage12_minor_unit_properties_and_wilson_interval():
    result = property_tests(500)
    assert result["failures"] == []
    assert result["floating_point_failures"] == 0
    interval = wilson(64, 64)
    assert 0.94 < interval["low"] < interval["high"] <= 1.0
