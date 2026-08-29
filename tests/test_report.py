from prooftrail.eval.report import render_metrics_markdown


def test_render_metrics_markdown_contains_headline_and_family_rows():
    report = render_metrics_markdown({
        "case_count": 2,
        "verified_only": False,
        "overall_accuracy": 0.5,
        "family_mean_accuracy": 0.75,
        "macro_f1": 0.4,
        "first_bad_event": {"hit_rate": 1.0, "hits": 1, "eligible": 1},
        "evidence_coverage": {"rate": 0.5, "cited": 1, "total": 2},
        "per_family": {"F01": {"accuracy": 0.5, "correct": 1, "total": 2}},
    })
    assert "Family-mean accuracy | 75.0%" in report
    assert "First-bad-event hit rate | 100.0% (1/1)" in report
    assert "| F01 | 50.0% | 1 | 2 |" in report
