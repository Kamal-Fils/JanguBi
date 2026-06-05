"""Extraction d'intention RULE-BASED (sans LLM) — RAG gratuit.

Avant : l'extraction passait par Gemini (coût + clé requise). Désormais 100 %
locale (mots-clés + dates relatives)."""

import datetime

import pytest

from apps.rag.extractor import IntentExtractor


@pytest.mark.asyncio
async def test_bible_keyword_routes_to_bible():
    result = await IntentExtractor().extract("Je cherche un verset sur la miséricorde")
    assert "BIBLE" in result["domains"]
    assert result["intent"] == "BIBLE"
    assert result["entities"]["topic"] == "Je cherche un verset sur la miséricorde"


@pytest.mark.asyncio
async def test_rosary_keyword_routes_to_rosary_with_today_date():
    result = await IntentExtractor().extract("Quel est le mystère du chapelet aujourd'hui ?")
    assert "ROSARY" in result["domains"]
    assert result["entities"]["date"] == datetime.date.today().isoformat()


@pytest.mark.asyncio
async def test_mixed_domains_when_both_keywords_present():
    result = await IntentExtractor().extract("un verset et le chapelet du jour")
    assert set(result["domains"]) == {"BIBLE", "ROSARY"}
    assert result["intent"] == "MIXED"


@pytest.mark.asyncio
async def test_defaults_to_bible_when_ambiguous():
    result = await IntentExtractor().extract("Parle-moi de l'amour")
    assert result["domains"] == ["BIBLE"]
    assert result["entities"]["date"] is None


@pytest.mark.asyncio
async def test_weekday_resolves_to_iso_date():
    result = await IntentExtractor().extract("le chapelet de lundi")
    # une date ISO (aujourd'hui ou future) tombant un lundi
    d = datetime.date.fromisoformat(result["entities"]["date"])
    assert d.weekday() == 0
