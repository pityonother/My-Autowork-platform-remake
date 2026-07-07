from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.booking.body_validation_fields import BookingBodyField, FIELDS_BY_CODE


@dataclass
class BookingBodyIssue:
    row_number: int | None
    field_code: str
    field_label: str
    message: str
    suggestion: str = ""
    correction_options: tuple[str, ...] = ()
    correction_kind: str = ""


@dataclass(frozen=True)
class BookingBodyFix:
    value: str
    suggestion: str = ""
    kind: str = ""
    options: tuple[str, ...] = ()


@dataclass
class BookingBodyRow:
    excel_row: int
    values: dict[str, str]
    source_values: dict[str, str] = field(default_factory=dict)
    cell_formats: dict[str, str] = field(default_factory=dict)
    date_cells: set[str] = field(default_factory=set)
    issue_fields: set[str] = field(default_factory=set)
    fixed_fields: set[str] = field(default_factory=set)
    source_issue_fields: set[str] = field(default_factory=set)
    issue_messages: dict[str, list[str]] = field(default_factory=dict)
    source_issue_messages: dict[str, list[str]] = field(default_factory=dict)
    correction_options: dict[str, tuple[str, ...]] = field(default_factory=dict)
    correction_kinds: dict[str, str] = field(default_factory=dict)
    delivery_match_status: str = ""
    delivery_match_message: str = ""
    delivery_match_options: tuple[str, ...] = ()

    def issue_text(self, field_code: str) -> str:
        return "；".join(self.issue_messages.get(field_code, []))

    def source_issue_text(self, field_code: str) -> str:
        return "；".join(self.source_issue_messages.get(field_code, []))

    def correction_options_for(self, field_code: str) -> tuple[str, ...]:
        return self.correction_options.get(field_code, ())

    def correction_kind_for(self, field_code: str) -> str:
        return self.correction_kinds.get(field_code, "")


@dataclass
class BookingBodyValidationPreview:
    filename: str
    rows: list[BookingBodyRow]
    issues: list[BookingBodyIssue]
    fields: list[BookingBodyField]
    applied_fixes: bool = False
    fix_count: int = 0
    purchaser: str = ""
    warnings: list[str] = field(default_factory=list)
    source_issues: list[BookingBodyIssue] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def source_issue_count(self) -> int:
        return len(self.source_issues)

    @property
    def display_issues(self) -> list[BookingBodyIssue]:
        def issue_priority(issue: BookingBodyIssue) -> tuple[int, int, str]:
            if issue.correction_kind == "date_choice":
                priority = 0
            elif not issue.correction_kind:
                priority = 1
            else:
                priority = 2
            return (priority, issue.row_number or 999999, issue.field_code)

        issues = self.source_issues if self.applied_fixes and self.source_issues else self.issues
        return sorted(issues, key=issue_priority)

    @property
    def display_issue_count(self) -> int:
        return len(self.display_issues)

    @property
    def blocking_row_count(self) -> int:
        return len({issue.row_number for issue in self.issues if issue.row_number is not None})

    @property
    def display_blocking_row_count(self) -> int:
        return len({issue.row_number for issue in self.display_issues if issue.row_number is not None})


def _field_label(field_code: str) -> str:
    field = FIELDS_BY_CODE.get(field_code)
    return field.label if field else field_code


def _issue(
    row: BookingBodyRow | None,
    field_code: str,
    message: str,
    suggestion: str = "",
    *,
    correction_options: tuple[str, ...] = (),
    correction_kind: str = "",
) -> BookingBodyIssue:
    if row is not None and field_code:
        row.issue_fields.add(field_code)
        row.issue_messages.setdefault(field_code, []).append(message)
    return BookingBodyIssue(
        row_number=row.excel_row if row is not None else None,
        field_code=field_code,
        field_label=_field_label(field_code),
        message=message,
        suggestion=suggestion,
        correction_options=correction_options,
        correction_kind=correction_kind,
    )


def _source_issue(
    row: BookingBodyRow,
    field_code: str,
    message: str,
    suggestion: str = "",
    *,
    correction_options: tuple[str, ...] = (),
    correction_kind: str = "",
) -> BookingBodyIssue:
    row.source_issue_fields.add(field_code)
    row.source_issue_messages.setdefault(field_code, []).append(message)
    return BookingBodyIssue(
        row_number=row.excel_row,
        field_code=field_code,
        field_label=_field_label(field_code),
        message=message,
        suggestion=suggestion,
        correction_options=correction_options,
        correction_kind=correction_kind,
    )
