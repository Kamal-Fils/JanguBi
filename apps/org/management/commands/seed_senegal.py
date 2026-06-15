"""
Management command : seed_senegal
Insère la structure territoriale catholique du Sénégal.
Usage : python manage.py seed_senegal
"""

from django.core.management.base import BaseCommand

from apps.org.models import Diocese, Parish, Province

SENEGAL_DATA = {
    "provinces": [
        {"name": "Province de Dakar", "code": "DAKP"},
        {"name": "Province de Thiès", "code": "THIP"},
        {"name": "Province de Ziguinchor", "code": "ZIGP"},
    ],
    "dioceses": [
        {"name": "Archidiocèse de Dakar", "code": "DAK", "province": "DAKP"},
        {"name": "Diocèse de Thiès", "code": "THI", "province": "THIP"},
        {"name": "Diocèse de Diourbel", "code": "DIO", "province": "DAKP"},
        {"name": "Diocèse de Saint-Louis", "code": "SLO", "province": "THIP"},
        {"name": "Diocèse de Ziguinchor", "code": "ZIG", "province": "ZIGP"},
        {"name": "Diocèse de Tambacounda", "code": "TAM", "province": "ZIGP"},
        {"name": "Diocèse de Kaolack", "code": "KAO", "province": "THIP"},
    ],
    "parishes": [
        # Dakar
        {"name": "Cathédrale du Souvenir Africain", "city": "Dakar", "diocese": "DAK"},
        {"name": "Paroisse Saint-Joseph de Medina", "city": "Dakar", "diocese": "DAK"},
        {"name": "Paroisse Sainte-Marie de la Mer", "city": "Dakar", "diocese": "DAK"},
        {"name": "Paroisse Saint-Pierre de Grand-Dakar", "city": "Dakar", "diocese": "DAK"},
        {"name": "Paroisse Sainte-Thérèse de Pikine", "city": "Pikine", "diocese": "DAK"},
        {"name": "Paroisse Saint-François d'Assise de Guédiawaye", "city": "Guédiawaye", "diocese": "DAK"},
        {"name": "Paroisse Sainte-Famille de Grand-Yoff", "city": "Dakar", "diocese": "DAK"},
        {"name": "Paroisse Sainte-Croix de Rufisque", "city": "Rufisque", "diocese": "DAK"},
        # Thiès
        {"name": "Cathédrale Saint-Joseph de Thiès", "city": "Thiès", "diocese": "THI"},
        {"name": "Paroisse Saint-Martin de Porres de Thiès", "city": "Thiès", "diocese": "THI"},
        {"name": "Paroisse Sainte-Marie de Popenguine", "city": "Popenguine", "diocese": "THI"},
        {"name": "Paroisse Saint-Pierre de Mbour", "city": "Mbour", "diocese": "THI"},
        {"name": "Paroisse Sainte-Anne de Tivaouane", "city": "Tivaouane", "diocese": "THI"},
        # Diourbel
        {"name": "Cathédrale de l'Immaculée Conception de Diourbel", "city": "Diourbel", "diocese": "DIO"},
        {"name": "Paroisse Saint-Paul de Bambey", "city": "Bambey", "diocese": "DIO"},
        # Saint-Louis
        {"name": "Cathédrale de Saint-Louis", "city": "Saint-Louis", "diocese": "SLO"},
        {"name": "Paroisse Sainte-Marguerite de Louga", "city": "Louga", "diocese": "SLO"},
        {"name": "Paroisse Saint-Joseph de Richard-Toll", "city": "Richard-Toll", "diocese": "SLO"},
        # Ziguinchor
        {"name": "Cathédrale Saint-Antoine de Ziguinchor", "city": "Ziguinchor", "diocese": "ZIG"},
        {"name": "Paroisse Sainte-Marie de Bignona", "city": "Bignona", "diocese": "ZIG"},
        {"name": "Paroisse Saint-François d'Oussouye", "city": "Oussouye", "diocese": "ZIG"},
        # Tambacounda
        {"name": "Cathédrale de Tambacounda", "city": "Tambacounda", "diocese": "TAM"},
        {"name": "Paroisse Saint-Joseph de Kédougou", "city": "Kédougou", "diocese": "TAM"},
        # Kaolack
        {"name": "Cathédrale de Kaolack", "city": "Kaolack", "diocese": "KAO"},
        {"name": "Paroisse Saint-Pierre de Fatick", "city": "Fatick", "diocese": "KAO"},
    ],
}


class Command(BaseCommand):
    help = "Initialise la structure territoriale catholique du Sénégal (3 provinces, 7 diocèses, ~25 paroisses)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Réimporter même si les données existent déjà",
        )

    def handle(self, *args, **options):
        force = options["force"]

        if Province.objects.exists() and not force:
            self.stdout.write(self.style.WARNING(
                "Des provinces existent déjà. Utilisez --force pour réimporter."
            ))
            return

        self.stdout.write("🌍 Initialisation de la structure territoriale du Sénégal...")

        # Provinces
        province_map: dict[str, Province] = {}
        for p_data in SENEGAL_DATA["provinces"]:
            province, created = Province.objects.get_or_create(
                code=p_data["code"],
                defaults={"name": p_data["name"], "country": "Senegal"},
            )
            province_map[p_data["code"]] = province
            action = "✅ Créé" if created else "⏭️  Existant"
            self.stdout.write(f"  {action} Province : {province.name}")

        # Diocèses
        diocese_map: dict[str, Diocese] = {}
        for d_data in SENEGAL_DATA["dioceses"]:
            province = province_map[d_data["province"]]
            diocese, created = Diocese.objects.get_or_create(
                code=d_data["code"],
                defaults={"name": d_data["name"], "province": province},
            )
            diocese_map[d_data["code"]] = diocese
            action = "✅ Créé" if created else "⏭️  Existant"
            self.stdout.write(f"  {action} Diocèse : {diocese.name}")

        # Paroisses
        parish_count = 0
        parishes = []
        for p_data in SENEGAL_DATA["parishes"]:
            diocese = diocese_map[p_data["diocese"]]
            parish, created = Parish.objects.get_or_create(
                name=p_data["name"],
                diocese=diocese,
                defaults={"city": p_data["city"]},
            )
            parishes.append(parish)
            if created:
                parish_count += 1

        self.stdout.write(f"  ✅ {parish_count} paroisses créées")

        # Église principale par paroisse (RG-ORG-04) — prérequis des appartenances.
        # `get_or_create` direct (et non Parish.objects.create) ne déclenche pas
        # parish_create : on garantit donc ici l'église is_main, idempotente.
        from apps.org.models import Church

        church_count = 0
        for parish in parishes:
            _, created = Church.objects.get_or_create(
                parish=parish,
                is_main=True,
                defaults={
                    "name": parish.name,
                    "church_type": "paroissiale",
                    "city": parish.city,
                    "address": parish.address,
                },
            )
            if created:
                church_count += 1

        self.stdout.write(f"  ✅ {church_count} églises principales créées")
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Structure territoriale initialisée : "
            f"{Province.objects.count()} provinces, "
            f"{Diocese.objects.count()} diocèses, "
            f"{Parish.objects.count()} paroisses, "
            f"{Church.objects.count()} églises"
        ))
