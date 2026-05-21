from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from apps.bible.models import DailyText
from apps.bible.services.aelf_service import AELFService


@pytest.mark.django_db(transaction=True)
async def test_fetch_daily_readings_handles_null_titre():
    """
    Regression: AELF returns psalm lectures with "titre": null.

    dict.get("titre", "") only falls back to "" when the key is absent — a
    present-but-null key returns None, which violated the NOT NULL constraint
    on DailyText.title and crashed the fetch_aelf_daily Celery task.
    """
    # Arrange
    target = date(2026, 5, 21)
    payload = {
        "messes": [
            {
                "lectures": [
                    {
                        "type": "psaume",
                        "titre": None,
                        "contenu": "<p>Garde-moi, mon Dieu</p>",
                    }
                ]
            }
        ]
    }
    service = AELFService()

    # Act
    with patch.object(service, "_fetch_with_retries", new=AsyncMock(return_value=payload)):
        records = await service.fetch_daily_readings(target)

    # Assert
    assert len(records) == 1
    dt = await DailyText.objects.aget(date=target, category="psaume")
    assert dt.title == ""
    assert dt.content


@pytest.mark.django_db(transaction=True)
async def test_fetch_daily_readings_handles_null_type_and_content():
    """A lecture with every optional key null must still persist with safe defaults."""
    # Arrange
    target = date(2026, 5, 22)
    payload = {
        "messes": [
            {"lectures": [{"type": None, "titre": None, "contenu": None}]}
        ]
    }
    service = AELFService()

    # Act
    with patch.object(service, "_fetch_with_retries", new=AsyncMock(return_value=payload)):
        records = await service.fetch_daily_readings(target)

    # Assert
    assert len(records) == 1
    dt = await DailyText.objects.aget(date=target)
    assert dt.category == "lecture"
    assert dt.title == ""
    assert dt.content == ""


@pytest.mark.django_db(transaction=True)
async def test_fetch_daily_readings_returns_empty_when_api_unavailable():
    """A failed AELF fetch returns no records instead of raising."""
    # Arrange
    service = AELFService()

    # Act
    with patch.object(service, "_fetch_with_retries", new=AsyncMock(return_value=None)):
        records = await service.fetch_daily_readings(date(2026, 5, 21))

    # Assert
    assert records == []
