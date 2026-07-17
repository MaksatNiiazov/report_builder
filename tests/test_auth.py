from report_builder.auth import has_permission


def test_global_permission_is_accepted() -> None:
    assert has_permission({"permissions": ["report_builder.reports.read"]}, "report_builder.reports.read")


def test_branch_permission_by_numeric_id_is_accepted() -> None:
    claims = {
        "branch_id": 2,
        "branch_permissions_by_id": {"2": ["report_builder.reports.read"]},
    }
    assert has_permission(claims, "report_builder.reports.read")


def test_unrelated_permission_is_rejected() -> None:
    assert not has_permission({"permissions": ["report_builder.reports.read"]}, "report_builder.reports.manage")

