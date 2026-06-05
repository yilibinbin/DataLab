from __future__ import annotations

from tools.audit_ui_schema_bindings import AuditFinding, audit_source_text, format_findings


def test_audit_reports_manual_tooltip_after_schema_binding() -> None:
    source = '''
def _bind_root_schema_fields(self):
    bind_field(field=root_field, widget=self.root_equations_edit, lang=lang)
    self.root_equations_edit.setToolTip("manual")
'''

    findings = audit_source_text(source, filename="app_desktop/panels.py")

    assert findings == [
        AuditFinding(
            filename="app_desktop/panels.py",
            line=4,
            code="manual-tooltip-after-schema-bind",
            detail='self.root_equations_edit.setToolTip("manual")',
        )
    ]


def test_audit_allows_schema_refresh_helper() -> None:
    source = '''
def _bind_error_schema_fields(self):
    bind_field(field=formula_field, widget=self.formula_edit, lang=lang)
    register_schema_text_refresh(self, formula_field, widget=self.formula_edit)
'''

    assert audit_source_text(source, filename="app_desktop/panels.py") == []


def test_audit_ignores_manual_tooltips_outside_migrated_schema_blocks() -> None:
    source = '''
def _build_unrelated_panel(self):
    self.dynamic_button.setToolTip("runtime state")
'''

    assert audit_source_text(source, filename="app_desktop/panels.py") == []


def test_audit_resets_after_migrated_schema_block() -> None:
    source = '''
def _bind_root_schema_fields(self):
    bind_field(field=root_field, widget=self.root_equations_edit, lang=lang)

def _refresh_runtime_help(self):
    self.dynamic_button.setToolTip("runtime state")
'''

    assert audit_source_text(source, filename="app_desktop/panels.py") == []


def test_audit_respects_allowlist_entries() -> None:
    source = '''
def _bind_root_schema_fields(self):
    bind_field(field=root_field, widget=self.root_equations_edit, lang=lang)
    self.root_equations_edit.setToolTip("dynamic runtime tooltip")
'''

    findings = audit_source_text(
        source,
        filename="app_desktop/panels.py",
        allowlist={"app_desktop/panels.py:4:manual-tooltip-after-schema-bind"},
    )

    assert findings == []


def test_format_findings_is_stable() -> None:
    findings = [
        AuditFinding("b.py", 2, "c", "second"),
        AuditFinding("a.py", 1, "b", "first"),
    ]

    assert format_findings(findings) == (
        "a.py:1: b: first\n"
        "b.py:2: c: second"
    )
