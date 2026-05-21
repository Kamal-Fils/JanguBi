# Charge les variables du .env comme variables Make (le '-' ignore l'erreur si .env absent)
-include .env
export

.PHONY: up down restart build logs shell dbshell makemigrations migrate check test \
       init-data create-admin init-all createsuperuser import-aelf clear-cache \
	   down-v rebuild \
       flush-redis flush-db check-embeddings seed-embeddings \
	celery-logs celery-restart rabbitmq-stats clean-audio collectstatic reinit-bible reinit-bible-aelf import-bible-aelf init-tv-categories

# ==============================================================================
# COMMANDES DOCKER
# ==============================================================================
up:
	docker compose up -d

down:
	docker compose down

down-v:
	docker compose down -v

rebuild:
	docker compose down
	docker compose build
	docker compose up -d

restart:
	docker compose restart

build:
	docker compose build

logs:
	docker compose logs -f django


# ==============================================================================
# COMMANDES DJANGO (exécutées dans le container)
# ==============================================================================
shell:
	docker compose exec django python manage.py shell

dbshell:
	docker compose exec db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

makemigrations:
	docker compose exec django python manage.py makemigrations

migrate:
	docker compose exec django python manage.py migrate

check:
	docker compose exec django python manage.py check

collectstatic:
	docker compose exec django python manage.py collectstatic --noinput

test:
	docker compose exec django pytest

createsuperuser:
	docker compose exec django python manage.py createsuperuser

import-aelf:
	docker compose exec django python manage.py import_aelf --start "$$(date +%Y-%m-%d)" --end "$$(python3 -c 'from datetime import datetime, timedelta; print((datetime.now() + timedelta(days=(6 - datetime.now().weekday()))).date())')"

clear-cache:
	docker compose exec django python manage.py shell -c "from django.core.cache import cache; cache.clear()"

flush-redis:
	docker compose exec redis redis-cli FLUSHALL

flush-db:
	docker compose exec django python manage.py flush --no-input

init-tv-categories:
	docker compose exec django python manage.py init_tv_categories

# ==============================================================================
# BIBLE & RAG UTILS
# ==============================================================================
check-embeddings:
	docker compose exec django python manage.py check_embeddings

seed-embeddings:
	docker compose exec django python manage.py shell -c "from apps.bible.models import Book; from apps.bible.tasks import compute_embeddings_task; [compute_embeddings_task.delay(b.id) for b in Book.objects.all()]; print('Dispatched embedding tasks for all books.')"

import-bible-aelf:
	docker compose exec django python manage.py import_bible init/bibles/format/json/bible-fr-aelf.json --source AELF

reinit-bible:
	docker compose exec django python manage.py shell -c "from apps.bible.models import Verse, Chapter, Book, DailyText; Verse.objects.all().delete(); Chapter.objects.all().delete(); Book.objects.all().delete(); DailyText.objects.all().delete(); print('Bible data cleared.')"
	docker compose exec django python manage.py import_bible init/bibles/format/json/bible-fr-aelf.json --source AELF
	docker compose exec django python manage.py import_aelf --start "$$(date +%Y-%m-%d)" --end "$$(python3 -c 'from datetime import datetime, timedelta; print((datetime.now() + timedelta(days=(6 - datetime.now().weekday()))).date())')"
	docker compose exec django python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared.')"

reinit-bible-aelf:
	docker compose exec django python manage.py shell -c "from apps.bible.models import Verse, Chapter, Book, DailyText; Verse.objects.all().delete(); Chapter.objects.all().delete(); Book.objects.all().delete(); DailyText.objects.all().delete(); print('Bible data cleared.')"
	docker compose exec django python manage.py import_bible init/bibles/format/json/bible-fr-aelf.json --source AELF
	docker compose exec django python manage.py import_aelf --start "$$(date +%Y-%m-%d)" --end "$$(python3 -c 'from datetime import datetime, timedelta; print((datetime.now() + timedelta(days=(6 - datetime.now().weekday()))).date())')"
	docker compose exec django python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared.')"

# ==============================================================================
# INFRASTRUCTURE & MAINTENANCE
# ==============================================================================
celery-logs:
	docker compose logs -f celery

celery-restart:
	docker compose restart celery

rabbitmq-stats:
	docker compose exec rabbitmq rabbitmqctl list_queues

clean-audio:
	docker compose exec django python manage.py shell -c "import os; from django.conf import settings; path = os.path.join(settings.MEDIA_ROOT, 'rosary'); [os.remove(os.path.join(path, f)) for f in os.listdir(path) if f.endswith('.mp3')]; print('Local audio cache cleaned.')"

# ==============================================================================
# INITIALISATION DU PROJET (cross-platform, ne requiert pas bash sur l'hôte)
# ==============================================================================
init-data:
	@echo "==========================================================="
	@echo "   Initialisation de la base de donnees Bible"
	@echo "==========================================================="
	@echo "1. Application des migrations Django..."
	docker compose exec django python manage.py migrate
	@echo "2. Importation du format A (bible-fr-aelf.json)..."
	docker compose exec django python manage.py import_bible init/bibles/format/json/bible-fr-aelf.json --source AELF
	@echo "3. Execution du script conditionnel pgvector..."
	docker compose exec -T db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) < init/postgresql/pgvector_conditional.sql
	@echo "4. Creation et configuration du bucket MinIO..."
	docker compose exec minio sh -c "mc alias set local $(AWS_S3_ENDPOINT_URL) $(MINIO_ROOT_USER) $(MINIO_ROOT_PASSWORD) && mc mb local/rosary-audio || true && mc anonymous set public local/rosary-audio"
	@echo "5. Importation des donnees du Rosaire..."
	docker compose exec django python manage.py seed_rosary
	@echo "6. Importation de la liturgie du jour (AELF)..."
	docker compose exec django python manage.py import_aelf --start "$$(date +%Y-%m-%d)" --end "$$(python3 -c 'from datetime import datetime, timedelta; print((datetime.now() + timedelta(days=(6 - datetime.now().weekday()))).date())')"
	@echo "==========================================================="
	@echo "   Importation et Indexation terminees !"
	@echo "==========================================================="

create-admin:
	@echo "==========================================================="
	@echo "   Creation du Super Administrateur"
	@echo "==========================================================="
	docker compose exec django python manage.py init_admin

init-all: init-data

