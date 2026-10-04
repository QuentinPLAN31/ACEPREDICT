"""Reset des quotas : refresh_quota_period (app/deps.py) remet analyses_used à 0
quand la période du plan est écoulée, sans toucher aux packs bonus."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.deps import refresh_quota_period


class _FakeDb:
    def commit(self): pass
    def refresh(self, _): pass


def _quota(used, started_ago, bonus=2):
    return SimpleNamespace(
        analyses_used=used, analyses_limit=3, bonus_analyses=bonus,
        period_start=datetime.utcnow() - started_ago,
    )


def test_paid_plan_resets_after_24h():
    q = _quota(3, timedelta(hours=25))
    assert refresh_quota_period(q, "starter", _FakeDb()) is True
    assert q.analyses_used == 0
    assert q.bonus_analyses == 2  # le pack survit au reset


def test_paid_plan_not_reset_before_24h():
    q = _quota(3, timedelta(hours=23))
    assert refresh_quota_period(q, "pro", _FakeDb()) is False
    assert q.analyses_used == 3


def test_free_plan_is_monthly():
    q = _quota(3, timedelta(days=10))
    assert refresh_quota_period(q, "free", _FakeDb()) is False
    q2 = _quota(3, timedelta(days=31))
    assert refresh_quota_period(q2, "free", _FakeDb()) is True
    assert q2.analyses_used == 0
