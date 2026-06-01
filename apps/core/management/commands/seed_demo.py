"""
Management command: seed_demo

Peuple la base de données avec des données de démonstration réalistes pour
la plateforme Jàngu Bi (communauté catholique sénégalaise).

Prérequis : exécuter `seed_senegal` d'abord pour créer Province/Diocese/Parish.

Usage :
    docker compose exec django python manage.py seed_senegal
    docker compose exec django python manage.py seed_demo
    docker compose exec django python manage.py seed_demo --reset

Idempotent : peut être exécuté plusieurs fois sans dupliquer les données.
"""

import datetime
import uuid

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify


# ─── Identifiants de test ─────────────────────────────────────────────────────

DEMO_PASSWORD = "Jangu2024!"

# Emails référencés dans le reste du fichier
EMAIL_SUPER_ADMIN = "admin@jangubidev.sn"
EMAIL_ARCHEVEQUE = "archeveque.dakar@jangubidev.sn"
EMAIL_EVEQUE = "eveque.thies@jangubidev.sn"
EMAIL_PRETRE = "pere.senghor@jangubidev.sn"
EMAIL_DIACRE = "diacre.diop@jangubidev.sn"
EMAIL_FIDELE1 = "aminata.fall@jangubidev.sn"
EMAIL_FIDELE2 = "moussa.ndiaye@jangubidev.sn"
EMAIL_RELIGIEUX = "soeur.marguerite@jangubidev.sn"

DEMO_USERS = [
    {
        "email": EMAIL_SUPER_ADMIN,
        "phone_number": "+221770000001",
        "role": "super_admin",
        "pastoral_role": None,
        "is_staff": True,
        "is_admin": True,
        "first_name": "Mamadou",
        "last_name": "Sy",
        "title": "MR",
        "parish_name": None,
    },
    {
        "email": EMAIL_ARCHEVEQUE,
        "phone_number": "+221770000002",
        "role": "province_admin",
        "pastoral_role": "archeveque",
        "is_staff": True,
        "is_admin": True,
        "first_name": "Jean-Baptiste",
        "last_name": "Faye",
        "title": "MR",
        "parish_name": None,
    },
    {
        "email": EMAIL_EVEQUE,
        "phone_number": "+221770000003",
        "role": "diocese_admin",
        "pastoral_role": "eveque",
        "is_staff": True,
        "is_admin": True,
        "first_name": "Thomas",
        "last_name": "Mendy",
        "title": "MR",
        "parish_name": None,
    },
    {
        "email": EMAIL_PRETRE,
        "phone_number": "+221770000004",
        "role": "parish_admin",
        "pastoral_role": "pretre",
        "is_staff": True,
        "is_admin": True,
        "first_name": "Pierre",
        "last_name": "Senghor",
        "title": "MR",
        "parish_name": "Cathédrale du Souvenir Africain",
    },
    {
        "email": EMAIL_DIACRE,
        "phone_number": "+221770000005",
        "role": "church_admin",
        "pastoral_role": "diacre",
        "is_staff": False,
        "is_admin": True,
        "first_name": "Joseph",
        "last_name": "Diop",
        "title": "MR",
        "parish_name": "Cathédrale du Souvenir Africain",
    },
    {
        "email": EMAIL_FIDELE1,
        "phone_number": "+221770000006",
        "role": "fidele",
        "pastoral_role": "fidele",
        "is_staff": False,
        "is_admin": False,
        "first_name": "Aminata",
        "last_name": "Fall",
        "title": "MRS",
        "parish_name": "Cathédrale du Souvenir Africain",
    },
    {
        "email": EMAIL_FIDELE2,
        "phone_number": "+221770000007",
        "role": "fidele",
        "pastoral_role": "fidele",
        "is_staff": False,
        "is_admin": False,
        "first_name": "Moussa",
        "last_name": "Ndiaye",
        "title": "MR",
        "parish_name": "Cathédrale Saint-Joseph de Thiès",
    },
    {
        "email": EMAIL_RELIGIEUX,
        "phone_number": "+221770000008",
        "role": "fidele",
        "pastoral_role": "religieux",
        "is_staff": False,
        "is_admin": False,
        "first_name": "Marguerite",
        "last_name": "Coly",
        "title": "MRS",
        "parish_name": None,
    },
]

TV_CATEGORIES = [
    {"name": "Messes",     "slug": "messes",      "order": 1, "is_clergy_only": False},
    {"name": "Homélies",   "slug": "homelies",    "order": 2, "is_clergy_only": False},
    {"name": "Catéchèse",  "slug": "catechese",   "order": 3, "is_clergy_only": False},
    {"name": "Événements", "slug": "evenements",  "order": 4, "is_clergy_only": False},
    {"name": "Témoignages","slug": "temoignages", "order": 5, "is_clergy_only": False},
    {"name": "Formation",  "slug": "formation",   "order": 6, "is_clergy_only": True},
]

TV_VIDEOS = [
    {
        "title": "Messe dominicale — Cathédrale du Souvenir Africain, Dakar",
        "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "category_slug": "messes",
        "is_live": False,
    },
    {
        "title": "Homélie — 3e Dimanche de l'Avent",
        "youtube_url": "https://www.youtube.com/watch?v=9bZkp7q19f0",
        "category_slug": "homelies",
        "is_live": False,
    },
    {
        "title": "Catéchisme pour adultes — Le sacrement du baptême",
        "youtube_url": "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
        "category_slug": "catechese",
        "is_live": False,
    },
    {
        "title": "Pèlerinage de Popenguine 2024 — Journée des Familles",
        "youtube_url": "https://www.youtube.com/watch?v=L_jWHffIx5E",
        "category_slug": "evenements",
        "is_live": False,
    },
    {
        "title": "Témoignage : ma conversion au cœur de la banlieue dakaroise",
        "youtube_url": "https://www.youtube.com/watch?v=oHg5SJYRHA0",
        "category_slug": "temoignages",
        "is_live": False,
    },
    {
        "title": "Formation des servants de messe — Module 1 : l'autel",
        "youtube_url": "https://www.youtube.com/watch?v=fJ9rUzIMcZQ",
        "category_slug": "formation",
        "is_live": False,
    },
]

ARTICLE_CATEGORIES = [
    {"name": "Vie paroissiale", "slug": "vie-paroissiale", "icon": "church",    "color": "#70CBFF", "display_order": 1},
    {"name": "Liturgie",        "slug": "liturgie",        "icon": "book-open", "color": "#8B5CF6", "display_order": 2},
    {"name": "Actualités",      "slug": "actualites",      "icon": "newspaper", "color": "#F59E0B", "display_order": 3},
    {"name": "Formation",       "slug": "formation-actu",  "icon": "book",      "color": "#10B981", "display_order": 4},
]

ARTICLES = [
    {
        "title": "Message de Carême 2024 — Archevêché de Dakar",
        "category_slug": "actualites",
        "scope_type": "global",
        "author_email": EMAIL_ARCHEVEQUE,
        "status": "published",
        "excerpt": "En ce temps de Carême, l'Archevêché de Dakar vous invite à un retour sincère vers Dieu.",
        "content": """<h2>Message de Carême 2024</h2>
<p>Frères et sœurs dans le Christ,</p>
<p>En ce temps de Carême, nous sommes invités à renouveler notre engagement baptismal et à approfondir notre relation avec Dieu. Le jeûne, la prière et l'aumône restent les piliers de cette démarche de conversion.</p>
<h3>Intentions de prière</h3>
<ul>
<li>Pour la paix au Sénégal et dans le monde</li>
<li>Pour les familles éprouvées par la pauvreté</li>
<li>Pour nos prêtres et nos religieuses</li>
</ul>
<p>Que le Seigneur vous bénisse et vous garde dans Sa paix.</p>
<p><em>† Jean-Baptiste Faye, Archevêque de Dakar</em></p>""",
    },
    {
        "title": "Lettre pastorale — Diocèse de Thiès : L'Église en sortie",
        "category_slug": "actualites",
        "scope_type": "global",
        "author_email": EMAIL_EVEQUE,
        "status": "published",
        "excerpt": "L'évêque de Thiès appelle les fidèles à porter l'Évangile dans les périphéries.",
        "content": """<h2>Lettre pastorale du Diocèse de Thiès</h2>
<p>Chers fidèles du Diocèse de Thiès,</p>
<p>Le Pape François nous appelle à être une Église en sortie. Cela signifie aller vers les périphéries géographiques et existentielles, rejoindre ceux qui sont loin de l'Église ou de la foi.</p>
<p>Dans notre diocèse, cette mission prend la forme de visites aux familles, de catéchèse dans les quartiers, et d'accompagnement des jeunes en situation de vulnérabilité.</p>
<p>Je compte sur chacun d'entre vous pour porter ce témoignage avec joie et humilité.</p>
<p><em>† Thomas Mendy, Évêque de Thiès</em></p>""",
    },
    {
        "title": "Annonce : Retraite paroissiale — Cathédrale du Souvenir Africain",
        "category_slug": "vie-paroissiale",
        "scope_type": "parish",
        "author_email": EMAIL_PRETRE,
        "status": "published",
        "excerpt": "Du 14 au 16 mars 2024, rejoignez-nous pour notre retraite paroissiale annuelle.",
        "content": """<h2>Retraite paroissiale 2024</h2>
<p>La paroisse Cathédrale du Souvenir Africain organise sa retraite spirituelle annuelle :</p>
<ul>
<li><strong>Date</strong> : Du vendredi 14 au dimanche 16 mars 2024</li>
<li><strong>Lieu</strong> : Centre spirituel de Keur Moussa, Thiès</li>
<li><strong>Animateur</strong> : Père Pierre Senghor</li>
</ul>
<h3>Thème : «Laisse-toi réconcilier avec Dieu» (2Co 5,20)</h3>
<p>Programme : méditations, confessions, Eucharistie quotidienne, chemin de croix.</p>
<p>Inscription au secrétariat paroissial avant le 5 mars. Places limitées.</p>""",
    },
    {
        "title": "Calendrier liturgique — Semaine Sainte 2024",
        "category_slug": "liturgie",
        "scope_type": "parish",
        "author_email": EMAIL_PRETRE,
        "status": "published",
        "excerpt": "Retrouvez le programme complet des célébrations de la Semaine Sainte à la Cathédrale.",
        "content": """<h2>Semaine Sainte 2024 — Programme</h2>
<table>
<tr><th>Jour</th><th>Célébration</th><th>Heure</th></tr>
<tr><td>Dimanche des Rameaux</td><td>Procession et messe</td><td>9h30</td></tr>
<tr><td>Jeudi Saint</td><td>Messe de la Cène du Seigneur</td><td>18h30</td></tr>
<tr><td>Vendredi Saint</td><td>Chemin de Croix (rue)</td><td>8h00</td></tr>
<tr><td>Vendredi Saint</td><td>Célébration de la Passion</td><td>15h00</td></tr>
<tr><td>Veillée Pascale</td><td>Vigile et baptêmes</td><td>21h00</td></tr>
<tr><td>Dimanche de Pâques</td><td>Messe solennelle</td><td>9h30</td></tr>
</table>
<p>Les enfants catéchumènes seront baptisés lors de la Vigile Pascale. Merci de les accompagner dans votre prière.</p>""",
    },
    {
        "title": "Formation : Comprendre la liturgie des Heures",
        "category_slug": "formation-actu",
        "scope_type": "global",
        "author_email": EMAIL_SUPER_ADMIN,
        "status": "published",
        "excerpt": "L'Office Divin, prière de l'Église universelle, rythme la journée de 7 heures canoniales.",
        "content": """<h2>La Liturgie des Heures</h2>
<p>La Liturgie des Heures est la prière officielle de l'Église catholique. Elle sanctifie les différents moments de la journée et de la nuit.</p>
<h3>Les 7 offices</h3>
<ol>
<li><strong>Matines (Lectures)</strong> — prière nocturne ou matinale</li>
<li><strong>Laudes</strong> — au lever du soleil</li>
<li><strong>Tierce</strong> — 9h00</li>
<li><strong>Sexte</strong> — midi</li>
<li><strong>None</strong> — 15h00</li>
<li><strong>Vêpres</strong> — au coucher du soleil</li>
<li><strong>Complies</strong> — fin de journée</li>
</ol>
<p>Sur Jàngu Bi, les 7 offices de l'AELF sont accessibles aux membres du clergé et aux religieux.</p>""",
    },
    {
        "title": "Brouillon — Témoignage de foi : l'Eucharistie au cœur de ma vie",
        "category_slug": "vie-paroissiale",
        "scope_type": "parish",
        "author_email": EMAIL_DIACRE,
        "status": "draft",
        "excerpt": "Un témoignage personnel sur la place de l'Eucharistie dans le quotidien d'un diacre.",
        "content": """<h2>L'Eucharistie, source et sommet</h2>
<p>Depuis mon ordination diaconale, l'Eucharistie a pris une nouvelle dimension dans ma vie. Chaque célébration est une rencontre personnelle avec le Christ ressuscité.</p>
<p>[Témoignage en cours de rédaction — à compléter avant publication]</p>""",
    },
]

DOCUMENT_REQUESTS = [
    {
        "requester_email": EMAIL_FIDELE1,
        "document_type": "baptism",
        "reason": "personal",
        "status": "submitted",
        "reference_suffix": "DEMO001",
        "requester_last_name": "Fall",
        "requester_first_names": "Aminata Fatou",
        "date_of_birth": datetime.date(1993, 6, 15),
        "place_of_birth": "Dakar",
        "contact_phone": "+221770000006",
        "father_last_name": "Fall",
        "mother_last_name": "Diop",
        "parish_name": "Cathédrale du Souvenir Africain",
        "diocese": "Archidiocèse de Dakar",
        "sacrament_approximate_date": "1993",
        "sacrament_location": "Cathédrale du Souvenir Africain, Dakar",
    },
    {
        "requester_email": EMAIL_FIDELE1,
        "document_type": "confirmation",
        "reason": "religious_marriage",
        "status": "under_verification",
        "reference_suffix": "DEMO002",
        "requester_last_name": "Fall",
        "requester_first_names": "Aminata Fatou",
        "date_of_birth": datetime.date(1993, 6, 15),
        "place_of_birth": "Dakar",
        "contact_phone": "+221770000006",
        "father_last_name": "Fall",
        "mother_last_name": "Diop",
        "parish_name": "Paroisse Saint-Joseph de Medina",
        "diocese": "Archidiocèse de Dakar",
        "sacrament_approximate_date": "2008",
        "sacrament_location": "Paroisse Saint-Joseph de Medina, Dakar",
    },
    {
        "requester_email": EMAIL_FIDELE2,
        "document_type": "first_communion",
        "reason": "catechism",
        "status": "validated",
        "reference_suffix": "DEMO003",
        "requester_last_name": "Ndiaye",
        "requester_first_names": "Moussa Ousmane",
        "date_of_birth": datetime.date(1990, 3, 22),
        "place_of_birth": "Thiès",
        "contact_phone": "+221770000007",
        "father_last_name": "Ndiaye",
        "mother_last_name": "Seck",
        "parish_name": "Cathédrale Saint-Joseph de Thiès",
        "diocese": "Diocèse de Thiès",
        "sacrament_approximate_date": "2001",
        "sacrament_location": "Cathédrale Saint-Joseph de Thiès",
    },
    {
        "requester_email": EMAIL_FIDELE2,
        "document_type": "religious_marriage",
        "reason": "religious_marriage",
        "status": "document_deposited",
        "reference_suffix": "DEMO004",
        "requester_last_name": "Ndiaye",
        "requester_first_names": "Moussa Ousmane",
        "date_of_birth": datetime.date(1990, 3, 22),
        "place_of_birth": "Thiès",
        "contact_phone": "+221770000007",
        "father_last_name": "Ndiaye",
        "mother_last_name": "Seck",
        "parish_name": "Cathédrale Saint-Joseph de Thiès",
        "diocese": "Diocèse de Thiès",
        "sacrament_approximate_date": "2018",
        "sacrament_location": "Cathédrale Saint-Joseph de Thiès",
    },
    {
        "requester_email": EMAIL_FIDELE1,
        "document_type": "baptism",
        "reason": "godparent",
        "status": "info_requested",
        "reference_suffix": "DEMO005",
        "info_request_message": "Les informations de parrainage fournies sont incomplètes. Merci de préciser la date exacte du baptême et le nom du parrain/marraine.",
        "requester_last_name": "Fall",
        "requester_first_names": "Aminata Fatou",
        "date_of_birth": datetime.date(1993, 6, 15),
        "place_of_birth": "Dakar",
        "contact_phone": "+221770000006",
        "father_last_name": "Fall",
        "mother_last_name": "Diop",
        "parish_name": "Paroisse Sainte-Marie de la Mer",
        "diocese": "Archidiocèse de Dakar",
        "sacrament_approximate_date": "1995",
        "sacrament_location": "Paroisse Sainte-Marie de la Mer, Dakar",
    },
    {
        "requester_email": EMAIL_DIACRE,
        "document_type": "confirmation",
        "reason": "personal",
        "status": "rejected",
        "reference_suffix": "DEMO006",
        "rejection_reason": "Le dossier soumis ne correspond pas aux registres de la paroisse indiquée. Veuillez contacter directement l'archevêché pour les cas de confirmation antérieurs à 1990.",
        "requester_last_name": "Diop",
        "requester_first_names": "Joseph Marie",
        "date_of_birth": datetime.date(1975, 11, 8),
        "place_of_birth": "Saint-Louis",
        "contact_phone": "+221770000005",
        "father_last_name": "Diop",
        "mother_last_name": "Gaye",
        "parish_name": "Cathédrale du Souvenir Africain",
        "diocese": "Archidiocèse de Dakar",
        "sacrament_approximate_date": "1989",
        "sacrament_location": "Église Saint-Louis du Sénégal",
    },
]

# (sender_key, text) — sender_key matches keys in sender_map built at runtime
CONVERSATION_MESSAGES_1 = [
    ("fidele", "Bonjour Père Senghor, j'aurais besoin de vos conseils pour une situation familiale délicate."),
    ("priest", "Bonjour Aminata, je vous lis. Je suis disponible. Racontez-moi ce qui se passe."),
    ("fidele", "Mon mari souhaite que nous nous réconciliions après une longue séparation, mais j'ai du mal à pardonner. Comment faire ?"),
    ("priest", "Le pardon est un chemin, pas un acte ponctuel. Saint Paul dit : «Supportez-vous les uns les autres et pardonnez-vous mutuellement» (Col 3,13). Commencez par prier pour lui chaque jour, même si le cœur n'y est pas encore. Je vous propose une rencontre en paroisse samedi à 10h si vous êtes disponible."),
]

CONVERSATION_MESSAGES_2 = [
    ("fidele", "Bonjour Père, pouvez-vous m'aider à comprendre comment participer à l'Office Divin ? Je suis intéressé."),
    ("priest", "Bonjour Moussa ! C'est une belle démarche. L'Office Divin, c'est la prière de l'Église tout au long de la journée. Sur Jàngu Bi, vous pouvez y accéder depuis la section Liturgie. Commencez par les Laudes le matin et les Vêpres le soir. Que le Seigneur bénisse votre démarche !"),
]


class Command(BaseCommand):
    help = "Peuple la base de données avec des données de démonstration réalistes (contexte sénégalais)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Supprime les données de démo existantes avant de les recréer",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self._reset()

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Jàngu Bi — Seed Demo ===\n"))

        with transaction.atomic():
            users = self._create_users()
            self._create_priest_profiles(users)
            self._create_tv_content()
            self._create_news_content(users)
            self._create_document_requests(users)
            self._create_conversations(users)

        self._print_summary()

    # ─── Users ────────────────────────────────────────────────────────────────

    def _create_users(self):
        from apps.org.models import Parish
        from apps.users.enums import PastoralRole, UserOnboardingState
        from apps.users.models import BaseUser, Profile

        self.stdout.write(self.style.MIGRATE_HEADING("\n  — Utilisateurs"))

        # Pre-fetch parishes by name (seed_senegal must have been run first)
        parishes = {p.name: p for p in Parish.objects.all()}

        created_users = {}
        for data in DEMO_USERS:
            pastoral_role = data["pastoral_role"]
            parish_name = data["parish_name"]
            parish = parishes.get(parish_name) if parish_name else None

            user, is_new = BaseUser.objects.get_or_create(
                email=data["email"],
                defaults={
                    "phone_number": data["phone_number"],
                    "role": data["role"],
                    "is_staff": data.get("is_staff", False),
                    "is_admin": data.get("is_admin", False),
                    "is_active": True,
                    "is_verified": True,
                    "pastoral_role": pastoral_role or "",
                    "onboarding_state": UserOnboardingState.COMPLETED,
                },
            )
            if is_new:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])

            Profile.objects.get_or_create(
                user=user,
                defaults={
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "title": data["title"],
                    "primary_parish": parish,
                },
            )

            label = "créé" if is_new else "existant"
            parish_label = f" → {parish_name}" if parish_name else ""
            self.stdout.write(
                f"  {'[+]' if is_new else '[=]'} {data['email']} [{data['role']}]{parish_label} ({label})"
            )

            created_users[data["email"]] = user

        return created_users

    # ─── Priest / Deacon profiles ─────────────────────────────────────────────

    def _create_priest_profiles(self, users):
        from apps.messaging.models import PriestProfile

        self.stdout.write(self.style.MIGRATE_HEADING("\n  — Profils clergé"))

        clergy = [
            (
                users[EMAIL_PRETRE],
                2010,
                "Père Pierre Senghor, ordonné prêtre en 2010 pour l'Archidiocèse de Dakar. "
                "Spécialisé en accompagnement spirituel des familles et des jeunes. "
                "Disponible pour la messagerie pastorale.",
            ),
            (
                users[EMAIL_DIACRE],
                2018,
                "Diacre Joseph Diop, ordonné en 2018. Responsable de la catéchèse des adultes "
                "et de l'accompagnement des familles en difficulté à la Cathédrale.",
            ),
        ]

        for user, ordination_year, bio in clergy:
            profile, is_new = PriestProfile.objects.get_or_create(
                user=user,
                defaults={
                    "accepts_pastoral_chat": True,
                    "cgu_accepted_at": timezone.now(),
                    "ordination_year": ordination_year,
                    "bio": bio,
                },
            )
            label = "créé" if is_new else "existant"
            self.stdout.write(f"  {'[+]' if is_new else '[=]'} PriestProfile {user.email} ({label})")

    # ─── TV content ───────────────────────────────────────────────────────────

    def _create_tv_content(self):
        from apps.tv.models import Category, Video

        self.stdout.write(self.style.MIGRATE_HEADING("\n  — JanguBi TV"))
        cat_map = {}
        for data in TV_CATEGORIES:
            cat, is_new = Category.objects.get_or_create(
                slug=data["slug"],
                defaults={
                    "name": data["name"],
                    "order": data["order"],
                    "is_clergy_only": data["is_clergy_only"],
                },
            )
            cat_map[data["slug"]] = cat
            label = "créée" if is_new else "existante"
            clergy_tag = " [clergé]" if data["is_clergy_only"] else ""
            self.stdout.write(f"  {'[+]' if is_new else '[=]'} Catégorie TV : {data['name']}{clergy_tag} ({label})")

        for data in TV_VIDEOS:
            cat = cat_map[data["category_slug"]]
            _, is_new = Video.objects.get_or_create(
                youtube_url=data["youtube_url"],
                defaults={
                    "title": data["title"],
                    "category": cat,
                    "is_live": data.get("is_live", False),
                },
            )
            label = "créée" if is_new else "existante"
            self.stdout.write(f"  {'[+]' if is_new else '[=]'} Vidéo : {data['title'][:55]} ({label})")

    # ─── News content ─────────────────────────────────────────────────────────

    def _create_news_content(self, users):
        from apps.news.models import Article, ArticleCategory

        self.stdout.write(self.style.MIGRATE_HEADING("\n  — Actualités"))
        cat_map = {}
        for data in ARTICLE_CATEGORIES:
            cat, is_new = ArticleCategory.objects.get_or_create(
                slug=data["slug"],
                defaults={
                    "name": data["name"],
                    "icon": data["icon"],
                    "color": data["color"],
                    "display_order": data["display_order"],
                    "is_active": True,
                },
            )
            cat_map[data["slug"]] = cat
            label = "créée" if is_new else "existante"
            self.stdout.write(f"  {'[+]' if is_new else '[=]'} Catégorie : {data['name']} ({label})")

        for data in ARTICLES:
            cat = cat_map[data["category_slug"]]
            author = users[data["author_email"]]
            slug = slugify(data["title"])
            _, is_new = Article.objects.get_or_create(
                slug=slug,
                defaults={
                    "title": data["title"],
                    "excerpt": data.get("excerpt", ""),
                    "content": data["content"],
                    "category": cat,
                    "author": author,
                    "scope_type": data.get("scope_type", "global"),
                    "status": data.get("status", "published"),
                    "published_at": timezone.now() if data.get("status") == "published" else None,
                },
            )
            label = "créé" if is_new else "existant"
            scope_tag = f"[{data['scope_type']}]"
            status_tag = f"[{data.get('status', 'published')}]"
            self.stdout.write(f"  {'[+]' if is_new else '[=]'} Article {scope_tag}{status_tag} : {data['title'][:45]} ({label})")

    # ─── Document requests ────────────────────────────────────────────────────

    def _create_document_requests(self, users):
        from apps.documents.models import DocumentRequest

        self.stdout.write(self.style.MIGRATE_HEADING("\n  — Demandes de documents"))

        for data in DOCUMENT_REQUESTS:
            reference = f"DOC-{data['reference_suffix']}"
            requester = users[data["requester_email"]]

            if DocumentRequest.objects.filter(reference=reference).exists():
                self.stdout.write(f"  [=] Demande {reference} (existante)")
                continue

            DocumentRequest.objects.create(
                requester=requester,
                reference=reference,
                document_type=data["document_type"],
                reason=data["reason"],
                status=data["status"],
                rejection_reason=data.get("rejection_reason", ""),
                additional_info=data.get("info_request_message", ""),
                requester_last_name=data["requester_last_name"],
                requester_first_names=data["requester_first_names"],
                date_of_birth=data["date_of_birth"],
                place_of_birth=data["place_of_birth"],
                contact_phone=data["contact_phone"],
                contact_email=requester.email,
                father_last_name=data.get("father_last_name", ""),
                mother_last_name=data.get("mother_last_name", ""),
                parish_name=data["parish_name"],
                diocese=data["diocese"],
                sacrament_approximate_date=data.get("sacrament_approximate_date", ""),
                sacrament_location=data.get("sacrament_location", ""),
                consent_given=True,
            )

            type_label = data["document_type"].replace("_", " ").title()
            self.stdout.write(f"  [+] {reference} — {type_label} [{data['status']}]")

    # ─── Conversations ────────────────────────────────────────────────────────

    def _create_conversations(self, users):
        from apps.messaging.models import Conversation, Message

        self.stdout.write(self.style.MIGRATE_HEADING("\n  — Messagerie"))

        threads = [
            (users[EMAIL_FIDELE1], users[EMAIL_PRETRE], CONVERSATION_MESSAGES_1),
            (users[EMAIL_FIDELE2], users[EMAIL_PRETRE], CONVERSATION_MESSAGES_2),
        ]

        for fidele, priest, messages in threads:
            a, b = (fidele, priest) if str(fidele.id) < str(priest.id) else (priest, fidele)
            conv, is_new = Conversation.objects.get_or_create(
                participant_a=a,
                participant_b=b,
                defaults={
                    "cgu_accepted_by_a": timezone.now(),
                    "cgu_accepted_by_b": timezone.now(),
                },
            )
            label = "créée" if is_new else "existante"
            self.stdout.write(f"  {'[+]' if is_new else '[=]'} Conversation {fidele.email} ↔ {priest.email} ({label})")

            if not is_new:
                continue

            now = timezone.now()
            sender_map = {"fidele": fidele, "priest": priest}
            for i, (sender_key, text) in enumerate(messages):
                msg = Message.objects.create(
                    conversation=conv,
                    sender=sender_map[sender_key],
                    content=text,
                    client_message_id=uuid.uuid4(),
                    content_type="text",
                )
                msg_time = now - datetime.timedelta(hours=len(messages) - i)
                Message.objects.filter(pk=msg.pk).update(created_at=msg_time)
                preview = text[:55] + "…" if len(text) > 55 else text
                self.stdout.write(f"    [+] {sender_map[sender_key].email[:25]}: {preview}")

            Conversation.objects.filter(pk=conv.pk).update(last_message_at=now)

    # ─── Reset ────────────────────────────────────────────────────────────────

    def _reset(self):
        from apps.documents.models import DocumentRequest
        from apps.messaging.models import Conversation
        from apps.news.models import Article, ArticleCategory
        from apps.tv.models import Category as TvCategory
        from apps.users.models import BaseUser

        self.stdout.write(self.style.WARNING("\n  Suppression des données de démo existantes..."))

        emails = [u["email"] for u in DEMO_USERS]
        # Also clean up legacy seed users from earlier naming convention
        legacy_emails = [
            "admin@jangubiapp.com", "pretre@jangubiapp.com",
            "fidele1@jangubiapp.com", "fidele2@jangubiapp.com",
        ]
        users = BaseUser.objects.filter(email__in=emails + legacy_emails)

        # Delete all user-linked data first (FK PROTECT prevents user deletion otherwise)
        Conversation.objects.filter(participant_a__in=users).delete()
        Conversation.objects.filter(participant_b__in=users).delete()
        DocumentRequest.objects.filter(requester__in=users).delete()
        Article.objects.filter(author__in=users).delete()

        # Delete demo TV categories and their videos
        from apps.tv.models import Video
        demo_tv_slugs = [c["slug"] for c in TV_CATEGORIES]
        Video.objects.filter(category__slug__in=demo_tv_slugs).delete()
        TvCategory.objects.filter(slug__in=demo_tv_slugs).delete()

        # Delete demo article categories (articles already deleted above)
        ArticleCategory.objects.filter(slug__in=[c["slug"] for c in ARTICLE_CATEGORIES]).delete()

        users.delete()
        self.stdout.write(self.style.SUCCESS("  Données supprimées.\n"))

    # ─── Summary ──────────────────────────────────────────────────────────────

    def _print_summary(self):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✓ Données de démonstration créées avec succès !"))
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("─── Comptes de test ────────────────────────────────────"))
        self.stdout.write(f"  Mot de passe commun : {self.style.WARNING(DEMO_PASSWORD)}")
        self.stdout.write("")
        for u in DEMO_USERS:
            role_label = u["role"].replace("_", " ").title()
            pastoral = f" / {u['pastoral_role']}" if u.get("pastoral_role") else ""
            self.stdout.write(f"  {u['email']:<42} [{role_label}{pastoral}]")
        self.stdout.write(self.style.MIGRATE_HEADING("────────────────────────────────────────────────────────"))
        self.stdout.write("")
