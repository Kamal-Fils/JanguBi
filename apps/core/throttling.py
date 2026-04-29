"""
Throttle classes pour les endpoints sensibles.
"""

from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    Rate limiting sur l'endpoint de login.
    Limite configurable via settings.DEFAULT_THROTTLE_RATES['login'].
    Défaut : 10 tentatives / minute par IP.
    """

    scope = "login"
    THROTTLE_RATES = {"login": "10/min"}
