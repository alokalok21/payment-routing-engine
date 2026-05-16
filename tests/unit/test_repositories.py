"""Tests for the repository layer — uses moto to mock DynamoDB."""

from src.repository import auth_rate_stats_repository, bin_repository, scheme_config_repository


def test_bin_lookup_dual_brand(mocked_dynamodb):
    info = bin_repository.lookup_bin("476173")
    assert info is not None
    assert info.bin_prefix == "476173"
    assert set(info.eligible_schemes) == {"VISA", "CB"}
    assert info.dual_brand is True
    assert info.domestic_scheme == "CB"
    assert info.issuer_country == "FR"


def test_bin_lookup_longest_prefix_falls_back(mocked_dynamodb):
    """BIN 4761739999 is not in the table at 8 digits, but 476173 is. Lookup
    should walk down to 6 digits and find it."""
    info = bin_repository.lookup_bin("4761739999")
    assert info is not None
    assert info.bin_prefix == "476173"


def test_bin_lookup_missing(mocked_dynamodb):
    assert bin_repository.lookup_bin("000000") is None


def test_scheme_config_lookup(mocked_dynamodb):
    cfg = scheme_config_repository.get_scheme_config("CB")
    assert cfg is not None
    assert cfg.scheme_id == "CB"
    assert cfg.enabled is True
    assert cfg.display_name == "Cartes Bancaires"


def test_scheme_config_missing(mocked_dynamodb):
    assert scheme_config_repository.get_scheme_config("NOPE") is None


def test_auth_rate_stats_lookup(mocked_dynamodb):
    stats = auth_rate_stats_repository.get_auth_rate_stats(
        scheme_id="CB", bin_bucket="4761", mcc="5411",
        currency="EUR", amount_bucket="50-200",
    )
    assert stats is not None
    assert stats.auth_rate_7d == 0.948
    assert stats.sample_count == 28640


def test_auth_rate_stats_missing(mocked_dynamodb):
    assert auth_rate_stats_repository.get_auth_rate_stats(
        scheme_id="VISA", bin_bucket="9999", mcc="0000",
        currency="EUR", amount_bucket="0-50",
    ) is None
