import json

import pytest

from prooftrail import cli
from prooftrail.agent.gemini_client import GeminiModelClient
from prooftrail.agent.interfaces import ModelResponse
from prooftrail.benchmark import (
    MODE_LIVE,
    MODE_REPLAY,
    b1_cache_path,
    run_b1_benchmark,
    write_b1_benchmark_artifacts,
)
from prooftrail.benchmark_report import (
    BenchmarkReportError,
    build_comparison_report,
    build_comparison_report_from_disk,
    write_comparison_report,
)
from prooftrail.baselines.json_client import InvalidJSONCompletion, ModelJSONCompletionClient
from prooftrail.baselines.prompts import B1_JSON_SCHEMA
from prooftrail.eval.spec import build_b1_spec
from prooftrail.schemas import AuditOutput, ClaimVerdict, GroundTruth, Usage


MODEL = "gemini-3.1-flash-lite"


class FakeAuditModel:
    model_name = MODEL
    is_live_model = True

    def __init__(self, text=None):
        self.calls = []
        self.text = text

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        text = self.text or json.dumps(
            {
                "verdict": "SUPPORTED",
                "claims": [
                    {
                        "claim_id": "c1",
                        "claim_text": "The reported refund was processed.",
                        "claim_type": "refund_issued",
                        "status": "SUPPORTED",
                        "evidence_seqs": [5],
                        "reason": "A matching state change exists.",
                    }
                ],
                "first_bad_event_seq": None,
                "explanation": "The action claim matches the ledger.",
            }
        )
        return ModelResponse(
            text=text,
            usage=Usage(input_tokens=200, output_tokens=50, cost_usd=0.0, llm_calls=1),
            stop_reason="end_turn",
        )


def test_strict_json_adapter_pins_model_and_rejects_markdown_fences():
    valid = FakeAuditModel()
    raw, usage = ModelJSONCompletionClient(valid).complete_json(
        system_prompt="system",
        user_prompt="user",
        model=MODEL,
        max_output_tokens=4096,
        effort="high",
    )
    assert raw["verdict"] == "SUPPORTED" and usage.llm_calls == 1
    assert valid.calls[0]["tools"] == ()

    fenced = FakeAuditModel("```json\n{}\n```")
    with pytest.raises(InvalidJSONCompletion, match="plain JSON"):
        ModelJSONCompletionClient(fenced).complete_json(
            system_prompt="system",
            user_prompt="user",
            model=MODEL,
            max_output_tokens=4096,
            effort="high",
        )
    with pytest.raises(ValueError, match="client is pinned"):
        ModelJSONCompletionClient(valid).complete_json(
            system_prompt="system",
            user_prompt="user",
            model="another-model",
            max_output_tokens=4096,
            effort="high",
        )


def test_gemini_no_tool_audit_request_asks_for_json_without_changing_tool_runs():
    client = GeminiModelClient(
        model=MODEL,
        api_key="fake-test-key",
        free_tier_confirmed=True,
        transport=lambda *_args: {},
        min_interval_seconds=0,
    )
    audit = client.build_request(
        messages=({"role": "user", "content": "Return JSON"},),
        tools=(),
        max_output_tokens=4096,
        effort="high",
    )
    assert audit["generationConfig"]["responseMimeType"] == "application/json"
    constrained = GeminiModelClient(
        model=MODEL,
        api_key="fake-test-key",
        free_tier_confirmed=True,
        transport=lambda *_args: {},
        min_interval_seconds=0,
        json_response_schema=B1_JSON_SCHEMA,
    ).build_request(
        messages=({"role": "user", "content": "Return JSON"},),
        tools=(),
        max_output_tokens=4096,
        effort="high",
    )
    assert constrained["generationConfig"]["responseJsonSchema"] == B1_JSON_SCHEMA


def test_b1_live_cache_then_zero_network_replay(tmp_path):
    case_ids = ["F01-s00", "F02-s00"]
    spec = build_b1_spec(provider="gemini", model=MODEL, run_index=0)
    live = FakeAuditModel()
    recorded = run_b1_benchmark(
        case_ids,
        spec,
        mode=MODE_LIVE,
        live_factory=lambda: live,
        cache_dir=tmp_path / "cache",
    )
    assert recorded.complete is True
    assert recorded.cache_hits == 0 and recorded.cache_misses == 2
    assert len(live.calls) == 2
    assert recorded.summary()["usage"]["llm_calls"] == 2
    assert b1_cache_path(tmp_path / "cache", spec, "F01-s00").exists()

    replayed = run_b1_benchmark(
        case_ids,
        spec,
        mode=MODE_REPLAY,
        cache_dir=tmp_path / "cache",
    )
    assert replayed.complete is True
    assert replayed.cache_hits == 2 and replayed.cache_misses == 0
    assert {key: value.to_dict() for key, value in replayed.outputs.items()} == {
        key: value.to_dict() for key, value in recorded.outputs.items()
    }

    paths = write_b1_benchmark_artifacts(replayed, tmp_path / "artifacts")
    assert all(path.exists() for path in paths.values())
    assert json.loads(paths["spec"].read_text(encoding="utf-8"))["model"] == MODEL
    assert json.loads(paths["summary"].read_text(encoding="utf-8"))["complete"] is True


def test_b1_malformed_output_is_recorded_as_failure_not_repaired(tmp_path):
    spec = build_b1_spec(provider="gemini", model=MODEL, run_index=2)
    live = FakeAuditModel('{"verdict":"MAYBE","claims":[]}')
    run = run_b1_benchmark(
        ["F01-s00"],
        spec,
        mode=MODE_LIVE,
        live_factory=lambda: live,
        cache_dir=tmp_path / "cache",
    )
    assert run.complete is False and not run.outputs
    assert run.failures[0]["error_type"] == "InvalidBaselineOutput"
    # The raw response is still frozen, so an offline replay reproduces the
    # same fail-closed result instead of making another provider call.
    replay = run_b1_benchmark(
        ["F01-s00"],
        spec,
        mode=MODE_REPLAY,
        cache_dir=tmp_path / "cache",
    )
    assert replay.failures[0]["error_type"] == "InvalidBaselineOutput"


def test_b1_cli_records_then_replays_one_case_without_building_live_client(
    tmp_path, monkeypatch, capsys
):
    live = FakeAuditModel()
    monkeypatch.setattr(cli, "build_gemini_client", lambda **_kwargs: live)
    cache = tmp_path / "cache"
    output = tmp_path / "live-output"
    common = [
        "benchmark",
        "b1",
        "--case",
        "F01-s00",
        "--model",
        MODEL,
        "--cache-dir",
        str(cache),
        "--output",
        str(output),
        "--json",
    ]
    assert cli.main(common + ["--live"]) == 0
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["summary"]["cache_misses"] == 1
    assert recorded["summary"]["complete"] is True

    monkeypatch.setattr(
        cli,
        "build_gemini_client",
        lambda **_kwargs: pytest.fail("replay must not construct a live provider"),
    )
    assert cli.main(common + ["--replay", "--output", str(tmp_path / "replay-output")]) == 0
    replayed = json.loads(capsys.readouterr().out)
    assert replayed["summary"]["cache_hits"] == 1
    assert replayed["summary"]["cache_misses"] == 0


def _audit_output(case_id, auditor, verdict, *, first_bad=None, calls=0):
    return AuditOutput(
        case_id=case_id,
        auditor=auditor,
        verdict=verdict,
        claims=[
            ClaimVerdict(
                claim_id="c1",
                claim_text="A refund result was reported.",
                claim_type="refund_issued",
                status=verdict,
                evidence_seqs=[1],
                reason="Synthetic comparison fixture.",
            )
        ],
        first_bad_event_seq=first_bad,
        usage={
            "input_tokens": 100 * calls,
            "output_tokens": 25 * calls,
            "cost_usd": 0.0,
            "llm_calls": calls,
        },
    )


def _truth(case_id, family_id, verdict, *, verified=False, first_bad=None):
    return GroundTruth(
        case_id=case_id,
        family_id=family_id,
        verdict=verdict,
        first_bad_event_seq=first_bad,
        expected_claims=[],
        ledger_facts={},
        verified_by_human=verified,
    )


def test_comparison_report_keeps_provisional_metrics_out_of_headline(tmp_path):
    truths = {
        "F01-s00": _truth("F01-s00", "F01", "SUPPORTED"),
        "F02-s00": _truth(
            "F02-s00", "F02", "CONTRADICTED", first_bad=2
        ),
    }
    b1_runs = {
        0: {
            "F01-s00": _audit_output("F01-s00", "B1", "SUPPORTED", calls=1),
            "F02-s00": _audit_output(
                "F02-s00", "B1", "CONTRADICTED", first_bad=2, calls=1
            ),
        },
        1: {
            "F01-s00": _audit_output("F01-s00", "B1", "CONTRADICTED", calls=1),
            "F02-s00": _audit_output(
                "F02-s00", "B1", "CONTRADICTED", first_bad=2, calls=1
            ),
        },
        2: {
            "F01-s00": _audit_output("F01-s00", "B1", "SUPPORTED", calls=1),
            "F02-s00": _audit_output("F02-s00", "B1", "SUPPORTED", calls=1),
        },
    }
    metadata = {
        index: {
            "run_index": index,
            "spec_sha256": str(index) * 64,
            "artifact_sha256": {},
            "summary": {
                "usage": {
                    "llm_calls": 2,
                    "input_tokens": 200,
                    "output_tokens": 50,
                    "cost_usd": 0.0,
                    "list_price_equivalent_usd": 0.01,
                }
            },
        }
        for index in b1_runs
    }
    prooftrail = {
        case_id: _audit_output(
            case_id,
            "prooftrail",
            truth.verdict,
            first_bad=truth.first_bad_event_seq,
        )
        for case_id, truth in truths.items()
    }
    no_temporal = {
        "F01-s00": _audit_output("F01-s00", "prooftrail-no-temporal", "SUPPORTED"),
        "F02-s00": _audit_output("F02-s00", "prooftrail-no-temporal", "SUPPORTED"),
    }
    report = build_comparison_report(
        b1_runs=b1_runs,
        b1_metadata=metadata,
        prooftrail_outputs=prooftrail,
        no_temporal_outputs=no_temporal,
        truths=truths,
        label_mode="provisional",
        dataset_manifest_sha256="a" * 64,
    )
    assert report["headline_eligible"] is False
    assert report["label_mode"] == "provisional"
    assert report["prooftrail"]["metrics"]["family_mean_accuracy"] == 1.0
    assert report["b1"]["stability"]["unanimous_cases"] == 0
    assert report["b1"]["usage"]["accepted_llm_calls"] == 6
    assert report["ablations"]["changed_cases_without_temporal"]

    paths = write_comparison_report(report, tmp_path)
    assert paths["json"].name == "comparison.provisional.json"
    assert "PROVISIONAL DIAGNOSTIC ONLY" in paths["markdown"].read_text(
        encoding="utf-8"
    )


def test_committed_b1_runs_build_a_fail_closed_offline_report(tmp_path):
    report = build_comparison_report_from_disk(
        provider="gemini",
        model=MODEL,
        run_indices=(0, 1, 2),
        allow_provisional=True,
        review_dir=tmp_path / "empty-reviews",
    )
    assert report["dataset"]["case_count"] == 40
    assert report["b1"]["run_count"] == 3
    assert report["b1"]["usage"]["accepted_llm_calls"] == 120
    assert report["headline_eligible"] is False
    assert all(
        row["artifact_dir"].startswith("b1/")
        for row in report["b1"]["runs"]
    )

    with pytest.raises(BenchmarkReportError, match="not headline eligible"):
        build_comparison_report_from_disk(
            provider="gemini",
            model=MODEL,
            run_indices=(0, 1, 2),
            review_dir=tmp_path / "empty-reviews",
        )
