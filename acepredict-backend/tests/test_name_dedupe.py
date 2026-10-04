"""Doublons de joueurs (ex. "Alex de Minaur" affiché deux fois)."""
from app.services.name_utils import name_key


def test_name_variants_share_a_key():
    base = name_key("Alex de Minaur")
    for variant in ("Alex De Minaur", "De Minaur Alex", "Alex Minaur", "alex de-minaur"):
        assert name_key(variant) == base


def test_different_players_have_different_keys():
    assert name_key("Alex de Minaur") != name_key("Alexander Zverev")
    assert name_key("Jannik Sinner") != name_key("Carlos Alcaraz")
