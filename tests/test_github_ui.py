import re

from prooftrail.ui import build_ui, render
from prooftrail.ui.build import ASSET_DIR

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def test_new_audit_offers_github_next_to_the_unchanged_refund_workflow():
    page = render.render_new_audit()
    assert 'data-audit-domain' in page
    assert '<option value="refund" selected>' in page
    assert '<option value="github">' in page
    assert 'data-domain-panel="refund"' in page
    assert 'data-domain-panel="github"' in page
    assert 'data-audit-submit' in page and 'data-audit-example' in page
    assert 'data-github-form' in page and 'data-github-submit' in page


def test_github_form_offers_the_supported_claims_and_no_token_field():
    page = render.render_new_audit()
    for claim in ("pr_exists", "base_branch", "head_sha", "pr_merged", "required_checks_passed"):
        assert f'name="claim" value="{claim}"' in page
    assert 'type="password"' not in page
    assert 'name="token"' not in page


def test_result_rendering_never_uses_html_injection():
    script = (ASSET_DIR / "github-audit.js").read_text(encoding="utf-8")
    for forbidden in ("innerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert forbidden not in script


def test_github_styles_use_tokens_only():
    css = (ASSET_DIR / "github-audit.css").read_text(encoding="utf-8")
    assert not HEX_COLOR.search(css)
    assert not re.search(r"rgba?\(", css)


def test_static_build_ships_the_github_form_and_assets(tmp_path):
    build_ui(tmp_path)
    page = (tmp_path / "audit.html").read_text(encoding="utf-8")
    assert "data-github-form" in page
    assert (tmp_path / "assets" / "github-audit.js").is_file()
    assert (tmp_path / "assets" / "github-audit.css").is_file()
