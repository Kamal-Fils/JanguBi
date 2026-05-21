import pytest
from unittest.mock import patch, AsyncMock
from apps.rag.router import QueryRouter

@pytest.mark.asyncio
async def test_router_bible_only():
    router = QueryRouter()

    intent_data = {
        "intent": "BIBLE",
        "domains": ["BIBLE"],
        "entities": {"topic": "Jesus"}
    }

    with patch("apps.rag.bible_engine.BibleEngine.search", new_callable=AsyncMock) as mock_bible, \
         patch("apps.rag.rosary_engine.RosaryEngine.search", new_callable=AsyncMock) as mock_rosary:

        mock_bible.return_value = "Bible Verse 1:1"

        results = await router.route_to_engines(intent_data)

        assert "bible" in results
        assert results["bible"] == "Bible Verse 1:1"
        assert "rosary" not in results

        mock_bible.assert_called_once_with({"topic": "Jesus"})
        mock_rosary.assert_not_called()

@pytest.mark.asyncio
async def test_router_rosary_only():
    router = QueryRouter()

    intent_data = {
        "intent": "ROSARY",
        "domains": ["ROSARY"],
        "entities": {"date": "2026-03-02"}
    }

    with patch("apps.rag.bible_engine.BibleEngine.search", new_callable=AsyncMock) as mock_bible, \
         patch("apps.rag.rosary_engine.RosaryEngine.search", new_callable=AsyncMock) as mock_rosary:

        mock_rosary.return_value = "Rosary ctx"

        results = await router.route_to_engines(intent_data)

        assert "rosary" in results
        assert "bible" not in results

        mock_rosary.assert_called_once()
        mock_bible.assert_not_called()
