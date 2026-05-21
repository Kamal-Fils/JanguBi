import pytest
from apps.bible.models import Book, Chapter, Verse, Testament
from apps.liturgy.matcher import CitationMatcher


@pytest.fixture(autouse=True)
def reset_books_cache():
    CitationMatcher._books_cache = None
    yield
    CitationMatcher._books_cache = None


@pytest.fixture
def setup_bible_data():
    t = Testament.objects.create(name="Nouveau Testament", slug="nouveau", order=2)
    b_luc = Book.objects.create(testament=t, name="Luc", slug="luc", order=3, alt_names=["Lc"])
    b_ps = Book.objects.create(testament=t, name="Psaumes", slug="psaumes", order=19, alt_names=["Ps"])

    c_luc_6 = Chapter.objects.create(book=b_luc, number=6)
    Verse.objects.create(chapter=c_luc_6, number=36, text="Soyez miséricordieux")
    Verse.objects.create(chapter=c_luc_6, number=37, text="Ne jugez pas")
    Verse.objects.create(chapter=c_luc_6, number=38, text="Donnez et on vous donnera")

    c_ps_78 = Chapter.objects.create(book=b_ps, number=78)
    Verse.objects.create(chapter=c_ps_78, number=5, text="O Dieu les nations ont envahi")
    Verse.objects.create(chapter=c_ps_78, number=8, text="Ne te souviens plus")
    Verse.objects.create(chapter=c_ps_78, number=9, text="Secours nous")

    return {
        "luc_6": c_luc_6,
        "ps_78": c_ps_78
    }

@pytest.mark.django_db(transaction=True)
def test_matcher_standard_gospel(setup_bible_data):
    # e.g., "Lc 6, 36-38" or "Lc 6,36-38"
    verses = CitationMatcher.match("Lc 6, 36-38")
    assert len(verses) == 3
    assert verses[0].number == 36
    assert verses[2].number == 38

@pytest.mark.django_db(transaction=True)
def test_matcher_psalm_complex(setup_bible_data):
    # e.g., "Ps 78 (79), 5a.8,9" -> it should pick up book=ps, chapter=78, range 5 to 9
    verses = CitationMatcher.match("Ps 78 (79), 5a.8,9")
    assert len(verses) == 3
    assert [v.number for v in verses] == [5, 8, 9]

@pytest.mark.django_db(transaction=True)
def test_matcher_invalid_or_missing():
    verses = CitationMatcher.match("Inconnu 1, 1")
    assert verses == []
    
    verses = CitationMatcher.match("")
    assert verses == []

@pytest.mark.django_db(transaction=True)
def test_matcher_single_verse(setup_bible_data):
    verses = CitationMatcher.match("Luc 6, 37")
    assert len(verses) == 1
    assert verses[0].number == 37
