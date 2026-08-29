import json

from prooftrail.cli import main


def test_demo_cli_writes_certificate_and_machine_summary(tmp_path, capsys):
    assert main(["demo", "--output", str(tmp_path), "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["actual_refunded_cents"] == 9400
    assert printed["first_bad_event_seq"] == 6
    assert (tmp_path / "certificate.md").exists()


def test_cases_cli_lists_all_ten_families(capsys):
    assert main(["cases", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 10
    assert rows[1]["family_id"] == "F02"
