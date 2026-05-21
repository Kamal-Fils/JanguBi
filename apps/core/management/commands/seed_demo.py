"""
Management command: seed_demo

Peuple la base de données avec des données de démonstration pour tester
l'application Jàngu Bi.

Usage :
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

DEMO_PASSWORD = "JanguBi@2025!"

DEMO_USERS = [
    {
        "email": "admin@jangubiapp.com",
        "phone_number": "+221770000001",
        "role": "super_admin",
        "is_staff": True,
        "is_admin": True,
        "first_name": "Mamadou",
        "last_name": "Sy",
        "title": "MR",
    },
    {
        "email": "pretre@jangubiapp.com",
        "phone_number": "+221770000002",
        "role": "parish_admin",
        "is_staff": True,
        "is_admin": True,
        "first_name": "Pierre",
        "last_name": "Diouf",
        "title": "MR",
        "is_priest": True,
    },
    {
        "email": "fidele1@jangubiapp.com",
        "phone_number": "+221770000003",
        "role": "fidele",
        "first_name": "Aminata",
        "last_name": "Diallo",
        "title": "MRS",
    },
    {
        "email": "fidele2@jangubiapp.com",
        "phone_number": "+221770000004",
        "role": "fidele",
        "first_name": "Ibrahima",
        "last_name": "Ndiaye",
        "title": "MR",
    },
]

TV_CATEGORIES = [
    {"name": "Messes en direct", "slug": "messes-direct", "order": 1},
    {"name": "Homélies", "slug": "homelies", "order": 2},
    {"name": "Enseignements", "slug": "enseignements", "order": 3},
    {"name": "Louange & Adoration", "slug": "louange-adoration", "order": 4},
]

TV_VIDEOS = [
    {
        "title": "Messe du Dimanche — Cathédrale de Dakar",
        "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "category_slug": "messes-direct",
        "is_live": False,
    },
    {
        "title": "Homélie — 3e Dimanche de l'Avent",
        "youtube_url": "https://www.youtube.com/watch?v=9bZkp7q19f0",
        "category_slug": "homelies",
        "is_live": False,
    },
    {
        "title": "Enseignement : La prière du Rosaire",
        "youtube_url": "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
        "category_slug": "enseignements",
        "is_live": False,
    },
    {
        "title": "Louange — Chants liturgiques en wolof",
        "youtube_url": "https://www.youtube.com/watch?v=L_jWHffIx5E",
        "category_slug": "louange-adoration",
        "is_live": False,
    },
]

ARTICLE_CATEGORIES = [
    {"name": "Vie paroissiale", "slug": "vie-paroissiale", "icon": "church", "color": "#70CBFF", "display_order": 1},
    {"name": "Annonces", "slug": "annonces", "icon": "megaphone", "color": "#F59E0B", "display_order": 2},
    {"name": "Événements", "slug": "evenements", "icon": "calendar", "color": "#10B981", "display_order": 3},
    {"name": "Formation", "slug": "formation", "icon": "book", "color": "#8B5CF6", "display_order": 4},
]

ARTICLES = [
    {
        "title": "Bienvenue dans la communauté Jàngu Bi",
        "category_slug": "vie-paroissiale",
        "scope_type": "global",
        "excerpt": "Découvrez comment rejoindre et participer à la vie de votre communauté catholique.",
        "content": """<h2>Bienvenue dans Jàngu Bi</h2>
<p>Jàngu Bi est la plateforme communautaire catholique du Sénégal. Elle vous permet de rester connecté à votre paroisse, d'accéder aux textes liturgiques, au rosaire et de communiquer avec vos prêtres.</p>
<h3>Comment commencer ?</h3>
<ul>
<li>Complétez votre profil dans la section "Profil"</li>
<li>Accédez aux lectures du jour depuis l'accueil</li>
<li>Demandez vos documents ecclésiaux en quelques clics</li>
<li>Dialoguez avec un prêtre disponible via la messagerie</li>
</ul>
<p>La paix du Seigneur soit avec vous !</p>""",
    },
    {
        "title": "Horaires des messes — Janvier 2026",
        "category_slug": "annonces",
        "scope_type": "global",
        "excerpt": "Retrouvez les horaires des messes pour le mois de janvier 2026.",
        "content": """<h2>Horaires des messes</h2>
<p>Les célébrations eucharistiques se tiennent aux horaires suivants :</p>
<ul>
<li><strong>Dimanche</strong> : 7h00, 9h30, 11h30, 18h00</li>
<li><strong>Jours de semaine</strong> : 6h30 et 18h30</li>
<li><strong>Samedi</strong> : 7h00 et 18h00</li>
</ul>
<p>Des messes spéciales sont prévues pour les grandes fêtes. Consultez le calendrier liturgique pour plus d'informations.</p>""",
    },
    {
        "title": "Retraite spirituelle — Chemin de Croix 2026",
        "category_slug": "evenements",
        "scope_type": "global",
        "excerpt": "Rejoignez-nous pour notre retraite spirituelle annuelle du Carême.",
        "content": """<h2>Retraite spirituelle du Carême</h2>
<p>Cette année, notre retraite se déroulera du <strong>1er au 5 mars 2026</strong> au Centre spirituel de Keur Moussa.</p>
<h3>Programme</h3>
<ul>
<li>Méditations guidées sur la Passion du Christ</li>
<li>Chemin de Croix en plein air</li>
<li>Confessions et accompagnement spirituel</li>
<li>Eucharistie quotidienne</li>
</ul>
<p>Inscription obligatoire auprès du secrétariat paroissial avant le 20 février.</p>""",
    },
    {
        "title": "Formation : Introduction à la lectio divina",
        "category_slug": "formation",
        "scope_type": "global",
        "excerpt": "Apprenez à prier avec la Parole de Dieu grâce à la lectio divina.",
        "content": """<h2>Qu'est-ce que la Lectio Divina ?</h2>
<p>La lectio divina est une méthode de prière chrétienne qui consiste à lire lentement un texte biblique, à le méditer, à prier à partir de lui et à le contempler.</p>
<h3>Les quatre étapes</h3>
<ol>
<li><strong>Lectio</strong> : Lire le texte avec attention</li>
<li><strong>Meditatio</strong> : Méditer sur ce qui nous touche</li>
<li><strong>Oratio</strong> : Prier à partir du texte</li>
<li><strong>Contemplatio</strong> : Se laisser habiter par la Parole</li>
</ol>
<p>Des sessions de formation sont organisées chaque premier samedi du mois à 9h00.</p>""",
    },
]

DOCUMENT_REQUESTS = [
    {
        "document_type": "baptism",
        "reason": "personal",
        "status": "submitted",
        "reference_suffix": "001",
        "requester_last_name": "Diallo",
        "requester_first_names": "Aminata Fatou",
        "date_of_birth": datetime.date(1993, 6, 15),
        "place_of_birth": "Dakar",
        "father_last_name": "Diallo",
        "mother_last_name": "Ndiaye",
        "parish_name": "Cathédrale de Dakar",
        "diocese": "Dakar",
        "sacrament_approximate_date": "1993",
        "sacrament_location": "Cathédrale de Dakar",
    },
    {
        "document_type": "confirmation",
        "reason": "religious_marriage",
        "status": "under_verification",
        "reference_suffix": "002",
        "requester_last_name": "Diallo",
        "requester_first_names": "Aminata Fatou",
        "date_of_birth": datetime.date(1993, 6, 15),
        "place_of_birth": "Dakar",
        "father_last_name": "Diallo",
        "mother_last_name": "Ndiaye",
        "parish_name": "Paroisse Saint-Pierre de Ziguinchor",
        "diocese": "Ziguinchor",
        "sacrament_approximate_date": "2009",
        "sacrament_location": "Ziguinchor",
    },
    {
        "document_type": "first_communion",
        "reason": "catechism",
        "status": "validated",
        "reference_suffix": "003",
        "requester_last_name": "Diallo",
        "requester_first_names": "Aminata Fatou",
        "date_of_birth": datetime.date(1993, 6, 15),
        "place_of_birth": "Dakar",
        "father_last_name": "Diallo",
        "mother_last_name": "Ndiaye",
        "parish_name": "Paroisse Saint-Jean de Thiès",
        "diocese": "Thiès",
        "sacrament_approximate_date": "2003",
        "sacrament_location": "Thiès",
    },
    {
        "document_type": "baptism",
        "reason": "godparent",
        "status": "rejected",
        "reference_suffix": "004",
        "rejection_reason": "Les informations fournies ne correspondent pas aux registres paroissiaux. Veuillez contacter directement la paroisse Saint-Michel.",
        "requester_last_name": "Diallo",
        "requester_first_names": "Aminata Fatou",
        "date_of_birth": datetime.date(1993, 6, 15),
        "place_of_birth": "Dakar",
        "father_last_name": "Diallo",
        "mother_last_name": "Ndiaye",
        "parish_name": "Paroisse Saint-Michel",
        "diocese": "Dakar",
        "sacrament_approximate_date": "1995",
        "sacrament_location": "Dakar",
    },
    {
        "document_type": "religious_marriage",
        "reason": "religious_marriage",
        "status": "document_deposited",
        "reference_suffix": "005",
        "requester_last_name": "Diallo",
        "requester_first_names": "Aminata Fatou",
        "date_of_birth": datetime.date(1993, 6, 15),
        "place_of_birth": "Dakar",
        "father_last_name": "Diallo",
        "mother_last_name": "Ndiaye",
        "parish_name": "Cathédrale de Dakar",
        "diocese": "Dakar",
        "sacrament_approximate_date": "2020",
        "sacrament_location": "Dakar",
    },
]

CONVERSATION_MESSAGES = [
    ("fidele1", "Bonjour Père, j'aurais besoin de votre aide pour une question spirituelle."),
    ("priest", "Bonjour, bien sûr ! Je suis disponible. De quoi s'agit-il ?"),
    ("fidele1", "Je traverse une période difficile et je me demande comment maintenir ma foi dans ces moments de doute."),
    ("priest", "Le doute fait partie du chemin spirituel. Saint Thomas lui-même a douté ! L'important est de continuer à chercher la vérité dans la prière."),
    ("fidele1", "Que me conseillez-vous comme prière ?"),
    ("priest", "Je vous recommande la lectio divina quotidienne, même 10 minutes par jour. Commencez par l'Évangile de Jean. Et n'hésitez pas à venir me voir en confession."),
    ("fidele1", "Merci beaucoup Père. Je vais essayer. Que Dieu vous bénisse !"),
    ("priest", "Que le Seigneur vous accompagne ! N'hésitez pas si vous avez d'autres questions."),
]


class Command(BaseCommand):
    help = "Peuple la base de données avec des données de démonstration"

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
            self._create_priest_profile(users["pretre@jangubiapp.com"])
            self._create_tv_content()
            self._create_news_content(users["admin@jangubiapp.com"])
            self._create_document_requests(users["fidele1@jangubiapp.com"])
            self._create_conversation(
                users["fidele1@jangubiapp.com"],
                users["pretre@jangubiapp.com"],
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✓ Données de démonstration créées avec succès !"))
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("─── Comptes de test ───────────────────────────────"))
        self.stdout.write(f"  Mot de passe commun : {self.style.WARNING(DEMO_PASSWORD)}")
        self.stdout.write("")
        for u in DEMO_USERS:
            role_label = u["role"].replace("_", " ").title()
            self.stdout.write(f"  {u['email']:<35} [{role_label}]")
        self.stdout.write(self.style.MIGRATE_HEADING("───────────────────────────────────────────────────"))
        self.stdout.write("")

    # ─── Users ────────────────────────────────────────────────────────────────

    def _create_users(self):
        from apps.users.models import BaseUser, Profile

        created = {}
        for data in DEMO_USERS:
            is_priest = data.pop("is_priest", False)
            first_name = data.pop("first_name")
            last_name = data.pop("last_name")
            title = data.pop("title")

            user, created_now = BaseUser.objects.get_or_create(
                email=data["email"],
                defaults={
                    "phone_number": data["phone_number"],
                    "role": data["role"],
                    "is_staff": data.get("is_staff", False),
                    "is_admin": data.get("is_admin", False),
                    "is_active": True,
                    "is_verified": True,
                },
            )
            if created_now:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])

            Profile.objects.get_or_create(
                user=user,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "title": title,
                },
            )

            status = "créé" if created_now else "existant"
            self.stdout.write(f"  {'[+]' if created_now else '[=]'} Utilisateur {data['email']} ({status})")

            # restore is_priest for priest detection
            if is_priest:
                data["is_priest"] = True

            created[data["email"]] = user

        return created

    # ─── Priest profile ───────────────────────────────────────────────────────

    def _create_priest_profile(self, priest_user):
        from apps.messaging.models import PriestProfile

        profile, created = PriestProfile.objects.get_or_create(
            user=priest_user,
            defaults={
                "accepts_pastoral_chat": True,
                "cgu_accepted_at": timezone.now(),
                "ordination_year": 2010,
                "bio": (
                    "Père Pierre Diouf, prêtre depuis 2010, spécialisé en accompagnement "
                    "spirituel des jeunes et des familles. Disponible pour tout dialogue pastoral."
                ),
            },
        )
        status = "créé" if created else "existant"
        self.stdout.write(f"  {'[+]' if created else '[=]'} PriestProfile pour {priest_user.email} ({status})")

    # ─── TV content ───────────────────────────────────────────────────────────

    def _create_tv_content(self):
        from apps.tv.models import Category, Video

        self.stdout.write(self.style.MIGRATE_HEADING("\n  — TV"))
        cat_map = {}
        for data in TV_CATEGORIES:
            cat, created = Category.objects.get_or_create(
                slug=data["slug"],
                defaults={"name": data["name"], "order": data["order"]},
            )
            cat_map[data["slug"]] = cat
            status = "créée" if created else "existante"
            self.stdout.write(f"  {'[+]' if created else '[=]'} Catégorie TV : {data['name']} ({status})")

        for data in TV_VIDEOS:
            cat = cat_map[data["category_slug"]]
            _, created = Video.objects.get_or_create(
                youtube_url=data["youtube_url"],
                defaults={
                    "title": data["title"],
                    "category": cat,
                    "is_live": data.get("is_live", False),
                },
            )
            status = "créée" if created else "existante"
            self.stdout.write(f"  {'[+]' if created else '[=]'} Vidéo : {data['title'][:50]} ({status})")

    # ─── News content ─────────────────────────────────────────────────────────

    def _create_news_content(self, author):
        from apps.news.models import Article, ArticleCategory

        self.stdout.write(self.style.MIGRATE_HEADING("\n  — Actualités"))
        cat_map = {}
        for data in ARTICLE_CATEGORIES:
            cat, created = ArticleCategory.objects.get_or_create(
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
            status = "créée" if created else "existante"
            self.stdout.write(f"  {'[+]' if created else '[=]'} Catégorie article : {data['name']} ({status})")

        for data in ARTICLES:
            cat = cat_map[data["category_slug"]]
            slug = slugify(data["title"])
            _, created = Article.objects.get_or_create(
                slug=slug,
                defaults={
                    "title": data["title"],
                    "excerpt": data.get("excerpt", ""),
                    "content": data["content"],
                    "category": cat,
                    "author": author,
                    "scope_type": data.get("scope_type", "global"),
                    "status": "published",
                    "published_at": timezone.now(),
                },
            )
            status = "créé" if created else "existant"
            self.stdout.write(f"  {'[+]' if created else '[=]'} Article : {data['title'][:50]} ({status})")

    # ─── Document requests ────────────────────────────────────────────────────

    def _create_document_requests(self, fidele):
        from apps.documents.models import DocumentRequest

        self.stdout.write(self.style.MIGRATE_HEADING("\n  — Demandes de documents"))
        today_str = timezone.now().strftime("%Y%m%d")

        for data in DOCUMENT_REQUESTS:
            suffix = data.pop("reference_suffix")
            reference = f"DOC-{today_str}-DEMO{suffix}"

            if DocumentRequest.objects.filter(reference=reference).exists():
                self.stdout.write(f"  [=] Demande {reference} (existante)")
                data["reference_suffix"] = suffix
                continue

            rejection_reason = data.pop("rejection_reason", "")

            DocumentRequest.objects.create(
                requester=fidele,
                reference=reference,
                document_type=data["document_type"],
                reason=data["reason"],
                status=data["status"],
                rejection_reason=rejection_reason,
                requester_last_name=data["requester_last_name"],
                requester_first_names=data["requester_first_names"],
                date_of_birth=data["date_of_birth"],
                place_of_birth=data["place_of_birth"],
                contact_phone="+221770000003",
                contact_email=fidele.email,
                father_last_name=data.get("father_last_name", ""),
                mother_last_name=data.get("mother_last_name", ""),
                parish_name=data["parish_name"],
                diocese=data["diocese"],
                sacrament_approximate_date=data.get("sacrament_approximate_date", ""),
                sacrament_location=data.get("sacrament_location", ""),
                consent_given=True,
            )

            data["reference_suffix"] = suffix
            type_label = data["document_type"].replace("_", " ").title()
            self.stdout.write(f"  [+] Demande {reference} — {type_label} [{data['status']}]")

    # ─── Conversation ─────────────────────────────────────────────────────────

    def _create_conversation(self, fidele, priest):
        from apps.messaging.models import Conversation, Message

        self.stdout.write(self.style.MIGRATE_HEADING("\n  — Messagerie"))

        # Enforce canonical ordering: participant_a.id < participant_b.id (str comparison)
        a, b = (fidele, priest) if str(fidele.id) < str(priest.id) else (priest, fidele)

        conv, created = Conversation.objects.get_or_create(
            participant_a=a,
            participant_b=b,
            defaults={
                "cgu_accepted_by_a": timezone.now(),
                "cgu_accepted_by_b": timezone.now(),
            },
        )

        status = "créée" if created else "existante"
        self.stdout.write(f"  {'[+]' if created else '[=]'} Conversation {fidele.email} ↔ {priest.email} ({status})")

        if not created:
            return

        now = timezone.now()
        sender_map = {"fidele1": fidele, "priest": priest}

        for i, (sender_key, text) in enumerate(CONVERSATION_MESSAGES):
            sender = sender_map[sender_key]
            msg_time = now - datetime.timedelta(hours=len(CONVERSATION_MESSAGES) - i)
            msg = Message.objects.create(
                conversation=conv,
                sender=sender,
                content=text,
                client_message_id=uuid.uuid4(),
                content_type="text",
            )
            # Backdate created_at for realistic thread ordering
            Message.objects.filter(pk=msg.pk).update(created_at=msg_time)
            self.stdout.write(f"  [+] Message de {sender.email[:25]}: {text[:50]}…" if len(text) > 50 else f"  [+] Message de {sender.email[:25]}: {text}")

        # Update conversation last_message_at
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
        users = BaseUser.objects.filter(email__in=emails)

        Conversation.objects.filter(participant_a__in=users).delete()
        Conversation.objects.filter(participant_b__in=users).delete()

        today_str = timezone.now().strftime("%Y%m%d")
        refs = [f"DOC-{today_str}-DEMO{i['reference_suffix'] if 'reference_suffix' in i else ''}" for i in DOCUMENT_REQUESTS]
        DocumentRequest.objects.filter(reference__startswith=f"DOC-{today_str}-DEMO").delete()

        Article.objects.filter(author__in=users).delete()
        ArticleCategory.objects.filter(slug__in=[c["slug"] for c in ARTICLE_CATEGORIES]).delete()
        TvCategory.objects.filter(slug__in=[c["slug"] for c in TV_CATEGORIES]).delete()

        users.delete()
        self.stdout.write(self.style.SUCCESS("  Données supprimées.\n"))
