"""
Throttle classes pour les endpoints sensibles.
"""

from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    Rate limiting sur l'endpoint de login : 10 tentatives / minute par IP.

    Le taux vient de settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['login']
    (lui-même surchargeable par la variable d'environnement LOGIN_THROTTLE_RATE).
    La classe redéfinissait auparavant THROTTLE_RATES en dur, ce qui rendait le
    réglage annoncé par cette docstring inopérant : changer les settings n'avait
    aucun effet.

    L'identité de l'appelant dépend de NUM_PROXIES (voir config/django/base.py) :
    sans ce réglage, la limite est contournable en faisant varier X-Forwarded-For.
    """

    scope = "login"
