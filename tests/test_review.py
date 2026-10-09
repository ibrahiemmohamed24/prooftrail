import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from prooftrail import cli
from prooftrail.config import FROZEN_DIR
from prooftrail.freeze import CASE_FILE, LABELS_FILE, sha256_file
from prooftrail.review import (
    ReviewValidationError,
    build_review_manifest,
    canonical_json_sha256,
    create_decision,
    decision_path,
    load_decision,
    resolve_reviewed_truth,
    review_material_for_case,
    validate_decision,
    write_decision,
    write_review_pack,
)
from prooftrail.schemas import LabelAmendment, ReviewAction


CASE_ID = "F02-s00"
REVIEWED_AT = "2026-08-29T20:00:00Z"


def _approve(**overrides):
    kwargs = {
        "action": ReviewAction.APPROVE,
        "reviewer_id": "github:independent-reviewer",
        "reviewer_name": "Independent Reviewer",
        "rationale": "Checked the final report against every relevant ledger transition.",
        "attested": True,
        "reviewed_at": REVIEWED_AT,
    }
    kwargs.update(overrides)
    return create_decision(CASE_ID, **kwargs)


def _copy_one_case(tmp_path: Path) -> Path:
    frozen = tmp_path / "frozen"
    shutil.copytree(FROZEN_DIR / CASE_ID, frozen / CASE_ID)
    shutil.copy2(FROZEN_DIR / "manifest.json", frozen / "manifest.json")
    return frozen


def test_review_material_is_deterministic_and_excludes_auditor_outputs(tmp_path):
    material, source = review_material_for_case(CASE_ID)
    text = json.dumps(material, sort_keys=True)
    assert material["evidence"]["final_report"]
    assert material["evidence"]["ledger"]
    assert "family_id" not in material["machine_preannotation_not_evidence"]
    assert "expected_verdict" not in text
    assert "certificate" not in text
    assert "audit.json" not in text
    assert canonical_json_sha256(material) == source.review_material_sha256

    written = write_review_pack([CASE_ID], output_dir=tmp_path / "pack")
    assert written[CASE_ID]["markdown"].exists()
    assert written[CASE_ID]["json"].exists()
    assert not (tmp_path / "pack" / "decisions").exists()
    assert "machine pre-annotation" in written[CASE_ID]["markdown"].read_text(encoding="utf-8").lower()


def test_explicit_approve_resolves_only_in_memory_and_preserves_frozen_files(tmp_path):
    case_path = FROZEN_DIR / CASE_ID / CASE_FILE
    labels_path = FROZEN_DIR / CASE_ID / LABELS_FILE
    before = (sha256_file(case_path), sha256_file(labels_path))

    decision = _approve()
    path = write_decision(decision, review_dir=tmp_path / "reviews")
    loaded = load_decision(path)
    truth = resolve_reviewed_truth(loaded)
    assert truth is not None and truth.verified_by_human is True
    assert truth.verdict == "SUPPORTED"
    assert before == (sha256_file(case_path), sha256_file(labels_path))

    manifest = build_review_manifest(expected=[CASE_ID], review_dir=tmp_path / "reviews")
    assert manifest["counts"]["approved"] == 1
    assert manifest["review_complete"] is True
    assert manifest["headline_eligible"] is True


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("attested", False, "explicitly accept"),
        ("reviewer_id", "", "reviewer id"),
        ("rationale", "", "rationale"),
        ("reviewed_at", "yesterday", "UTC timestamp"),
    ],
)
def test_approval_requires_identity_rationale_timestamp_and_attestation(field, value, message):
    with pytest.raises(ReviewValidationError, match=message):
        _approve(**{field: value})


def test_source_or_decision_tampering_is_detected(tmp_path):
    frozen = _copy_one_case(tmp_path)
    decision = create_decision(
        CASE_ID,
        action=ReviewAction.APPROVE,
        reviewer_id="github:reviewer",
        reviewer_name="Reviewer",
        rationale="Compared claims with raw ledger and state transitions.",
        attested=True,
        reviewed_at=REVIEWED_AT,
        frozen_dir=frozen,
    )
    case_path = frozen / CASE_ID / CASE_FILE
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["trace"]["final_report"] += " "
    case_path.write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert any(
        "case hash does not match the frozen dataset manifest" in problem
        for problem in validate_decision(decision, frozen_dir=frozen)
    )

    original = _approve()
    tampered = replace(original, rationale="Different rationale")
    assert any("decision_sha256 does not match" in problem for problem in validate_decision(tampered))


def test_amendment_is_validated_and_resolved_without_changing_ledger_facts():
    amendment = LabelAmendment(
        verdict="CONTRADICTED",
        first_bad_event_seq=5,
        expected_claims=[
            {
                "claim_type": "count",
                "status": "CONTRADICTED",
                "evidence_seqs": [5],
                "note": "Human reviewer found a contradicted count claim at the cited transition.",
            }
        ],
        notes="Corrected the claim-level interpretation after reading the raw state transition.",
    )
    decision = create_decision(
        CASE_ID,
        action=ReviewAction.AMEND,
        amendment=amendment,
        reviewer_id="github:reviewer",
        reviewer_name="Reviewer",
        rationale="The provisional claim typing omitted a material count claim.",
        attested=True,
        reviewed_at=REVIEWED_AT,
    )
    truth = resolve_reviewed_truth(decision)
    assert truth is not None and truth.verdict == "CONTRADICTED"
    assert truth.first_bad_event_seq == 5
    assert truth.ledger_facts["state_change_seqs"] == [5]

    invalid = replace(amendment, verdict="SUPPORTED")
    with pytest.raises(ReviewValidationError, match="aggregate"):
        create_decision(
            CASE_ID,
            action=ReviewAction.AMEND,
            amendment=invalid,
            reviewer_id="github:reviewer",
            reviewer_name="Reviewer",
            rationale="Testing an invalid mismatch.",
            attested=True,
            reviewed_at=REVIEWED_AT,
        )


def test_abstain_is_a_complete_review_but_not_headline_eligible(tmp_path):
    decision = create_decision(
        CASE_ID,
        action=ReviewAction.ABSTAIN,
        reviewer_id="github:reviewer",
        reviewer_name="Reviewer",
        rationale="The available ledger cannot resolve this label confidently.",
        attested=True,
        reviewed_at=REVIEWED_AT,
    )
    write_decision(decision, review_dir=tmp_path / "reviews")
    assert resolve_reviewed_truth(decision) is None
    manifest = build_review_manifest(expected=[CASE_ID], review_dir=tmp_path / "reviews")
    assert manifest["review_complete"] is True
    assert manifest["headline_eligible"] is False
    assert manifest["counts"]["abstained"] == 1


def test_replacement_requires_exact_superseded_hash(tmp_path):
    review_dir = tmp_path / "reviews"
    first = _approve()
    write_decision(first, review_dir=review_dir)
    with pytest.raises(FileExistsError):
        write_decision(first, review_dir=review_dir)

    replacement = _approve(
        rationale="Second review after a documented re-check of every ledger event.",
        supersedes_decision_sha256=first.decision_sha256,
        reviewed_at="2026-08-29T21:00:00Z",
    )
    write_decision(replacement, review_dir=review_dir, replace_existing=True)
    assert load_decision(decision_path(review_dir, CASE_ID)).decision_sha256 == replacement.decision_sha256


def test_review_cli_pack_and_explicit_single_case_decision(tmp_path, capsys):
    pack = tmp_path / "pack"
    reviews = tmp_path / "reviews"
    assert cli.main(["review", "pack", "--case", CASE_ID, "--output", str(pack), "--json"]) == 0
    packed = json.loads(capsys.readouterr().out)
    assert packed["case_count"] == 1 and packed["decisions_created"] == 0

    common = [
        "review",
        "decide",
        "--case",
        CASE_ID,
        "--approve",
        "--reviewer-id",
        "github:reviewer",
        "--reviewer-name",
        "Reviewer",
        "--rationale",
        "Personally checked the raw claims against the complete ledger.",
        "--review-dir",
        str(reviews),
        "--json",
    ]
    assert cli.main(common) == 2
    assert "--attest-reviewed is required" in capsys.readouterr().err
    assert cli.main(common + ["--attest-reviewed"]) == 0
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["action"] == "APPROVE"
    assert decision_path(reviews, CASE_ID).exists()
