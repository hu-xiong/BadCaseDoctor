from unittest.mock import MagicMock, patch

from agents.tools.grep_assignee import AssigneeResolveResult, resolve_assignee_user_ids


def test_resolve_empty_hint():
    r = resolve_assignee_user_ids("")
    assert r == AssigneeResolveResult(hint="")
    assert r.user_ids == []


def test_resolve_returns_dataclass_fields():
    with patch("app.User") as User:
        User.query.filter.return_value.limit.return_value.all.return_value = []
        r = resolve_assignee_user_ids("nonexistent_user_xyz_abc")
    assert r.hint == "nonexistent_user_xyz_abc"
    assert isinstance(r.user_ids, list)
    assert isinstance(r.matched_users, list)
