"""
Tests de apps/liturgy/tasks.py — synchronisation AELF nocturne.
Pattern AAA (Arrange / Act / Assert).

Verrouille la régression `asyncio.run` : sous un worker gevent/eventlet (le cas
avec Channels), une boucle d'événements tourne déjà dans le thread et
`asyncio.run` lève `RuntimeError: This event loop is already running` — la
synchro échoue et les fidèles n'ont pas les lectures du lendemain.
"""

from unittest.mock import AsyncMock, patch

import pytest

from apps.liturgy.tasks import daily_sync_task

_SYNC_TARGET = "apps.liturgy.services.AelfService.sync_daily_data"


@pytest.mark.django_db
def test_daily_sync_calls_the_service_for_the_default_zone():
    # Arrange / Act
    with patch(_SYNC_TARGET, new_callable=AsyncMock) as mock_sync:
        daily_sync_task("2026-01-15")

    # Assert — zone par défaut "afrique" (doit correspondre à celle lue par les APIs)
    mock_sync.assert_called_once_with("2026-01-15", "afrique")


def test_daily_sync_does_not_call_asyncio_run_directly():
    """RÉGRESSION : `asyncio.run` est incompatible avec un worker gevent/eventlet.

    Garde au niveau de la SOURCE : `asgiref.async_to_sync` appelle lui-même
    `asyncio.run` dans son propre thread, donc patcher `asyncio.run` ne
    distinguerait pas les deux implémentations.
    """
    # Arrange
    import inspect

    from apps.liturgy import tasks

    # Act
    source = inspect.getsource(tasks)

    # Assert
    assert "asyncio.run(" not in source, "utiliser async_to_sync, pas asyncio.run"
    assert "async_to_sync" in source


@pytest.mark.django_db
def test_daily_sync_syncs_every_requested_zone():
    # Arrange / Act
    with patch(_SYNC_TARGET, new_callable=AsyncMock) as mock_sync:
        daily_sync_task("2026-01-15", ["romain", "afrique"])

    # Assert
    assert mock_sync.call_count == 2


@pytest.mark.django_db
def test_daily_sync_continues_when_one_zone_fails():
    """Une zone en erreur ne doit pas empêcher les autres de se synchroniser."""
    # Arrange
    calls: list[str] = []

    async def _fail_on_romain(date_str, zone):
        calls.append(zone)
        if zone == "romain":
            raise RuntimeError("AELF indisponible")

    # Act — appel direct du corps de la tâche (pas de machinerie de retry ici).
    # L'échec final est attendu, mais APRÈS avoir tenté toutes les zones.
    with patch(_SYNC_TARGET, side_effect=_fail_on_romain):
        with pytest.raises(RuntimeError):
            daily_sync_task("2026-01-15", ["romain", "afrique"])

    # Assert
    assert calls == ["romain", "afrique"]


@pytest.mark.django_db
def test_daily_sync_fails_when_a_zone_fails_so_celery_retries():
    """RÉGRESSION : l'échec était avalé dans un log — aucun retry n'était possible
    et les lectures du lendemain étaient perdues sans alerte."""
    # Arrange / Act & Assert — la tâche LÈVE au lieu d'avaler l'erreur,
    # ce qui permet à `autoretry_for` de rejouer la synchro.
    with patch(_SYNC_TARGET, new_callable=AsyncMock) as mock_sync:
        mock_sync.side_effect = RuntimeError("AELF indisponible")
        with pytest.raises(RuntimeError):
            daily_sync_task("2026-01-15")


def test_daily_sync_has_bounded_retries():
    # Arrange / Act / Assert
    assert daily_sync_task.max_retries is not None
    assert daily_sync_task.max_retries > 0
