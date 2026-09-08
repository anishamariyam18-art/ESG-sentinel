from app.claims.splitter import split_candidate


def test_compound_sentence_with_three_metrics_is_split():
    text = (
        "We reduced emissions by 20%, increased renewable energy to 80%, "
        "and recycled 95% of operational waste."
    )
    result = split_candidate(text)
    assert len(result) == 3
    assert any("20%" in r for r in result)
    assert any("80%" in r for r in result)
    assert any("95%" in r for r in result)


def test_single_connected_claim_is_not_split():
    text = "We reduced Scope 1 and 2 emissions by 20% from the 2020 baseline."
    assert split_candidate(text) == [text]


def test_claim_with_only_one_number_is_not_split():
    text = "The company has committed to achieving net zero emissions by 2050."
    assert split_candidate(text) == [text]


def test_two_independent_metrics_joined_by_and_are_split():
    text = "Scope 1 emissions decreased by 12%, and Scope 2 emissions were 45,000 tCO2e in 2025."
    result = split_candidate(text)
    assert len(result) == 2


def test_split_never_produces_empty_fragments():
    text = "We reduced emissions by 20%, increased renewable energy to 80%, and recycled 95% of waste."
    result = split_candidate(text)
    assert all(piece.strip() for piece in result)
