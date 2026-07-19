"""
Tests de non-régression sur le rate limiting du login.

Contexte — la faille corrigée : DRF construit l'identité de l'appelant dans
`BaseThrottle.get_ident()`. Quand `NUM_PROXIES` vaut `None` (le défaut), il
concatène TOUT l'en-tête `X-Forwarded-For`, que le client contrôle. Il suffisait
donc de faire varier cet en-tête à chaque requête pour tomber dans un seau
différent : le quota annoncé de 10 tentatives/minute ne s'appliquait jamais, et
la force brute sur le login passait outre.

Avec `NUM_PROXIES = 1`, DRF ne retient que la DERNIÈRE adresse de la chaîne —
celle écrite par notre propre Traefik, qu'un client ne peut pas forger.
"""

import pytest
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory

from apps.core.throttling import LoginRateThrottle


@pytest.fixture
def throttle():
    return LoginRateThrottle()


@pytest.fixture
def factory():
    return APIRequestFactory()


def test_num_proxies_is_configured():
    """Sans ce réglage, tous les autres tests de ce fichier deviennent faux :
    DRF retomberait sur l'en-tête brut, contrôlé par le client."""
    assert api_settings.NUM_PROXIES is not None, (
        "NUM_PROXIES doit être défini : à None, l'identité de throttling est "
        "dérivée de l'intégralité de X-Forwarded-For, donc forgeable."
    )


def test_forged_forwarded_for_does_not_change_identity(throttle, factory):
    """Le cœur de la faille : deux requêtes venant du MÊME client, qui mentent
    différemment sur X-Forwarded-For, doivent rester dans le même seau."""
    # Arrange — même proxy réel (dernière adresse), préfixe forgé différent.
    first = factory.post(
        "/api/auth/login/",
        HTTP_X_FORWARDED_FOR="1.1.1.1, 203.0.113.7",
        REMOTE_ADDR="203.0.113.7",
    )
    second = factory.post(
        "/api/auth/login/",
        HTTP_X_FORWARDED_FOR="2.2.2.2, 203.0.113.7",
        REMOTE_ADDR="203.0.113.7",
    )

    # Act
    first_ident = throttle.get_ident(first)
    second_ident = throttle.get_ident(second)

    # Assert
    assert first_ident == second_ident == "203.0.113.7"


def test_distinct_clients_keep_distinct_identities(throttle, factory):
    """Le revers : le cloisonnement doit rester réel entre deux clients
    différents, sinon on limiterait tout le monde d'un coup."""
    # Arrange
    alice = factory.post(
        "/api/auth/login/",
        HTTP_X_FORWARDED_FOR="198.51.100.4",
        REMOTE_ADDR="10.0.0.1",
    )
    bob = factory.post(
        "/api/auth/login/",
        HTTP_X_FORWARDED_FOR="198.51.100.9",
        REMOTE_ADDR="10.0.0.1",
    )

    # Act & Assert
    assert throttle.get_ident(alice) != throttle.get_ident(bob)


def test_login_rate_comes_from_settings(throttle):
    """La classe redéfinissait THROTTLE_RATES en dur, ce qui rendait le réglage
    par settings inopérant alors que la docstring l'annonçait."""
    # Arrange & Act
    rate = throttle.get_rate()

    # Assert
    assert rate == api_settings.DEFAULT_THROTTLE_RATES["login"]
    assert "LoginRateThrottle" not in LoginRateThrottle.__dict__.get(
        "THROTTLE_RATES", {}
    ), "THROTTLE_RATES ne doit plus être redéfini localement."
