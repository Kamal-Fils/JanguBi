# LOT2-001 — Reconstruire « Allo-Prêtre » (Availability) en HackSoft

- **Statut** : À FAIRE (Lot 2/3)
- **Priorité** : 🔴 P2
- **Estimation** : ~1 à 1,5 jour
- **Créé le** : 2026-05-31 (audit Lot 1)
- **Origine** : contrat orphelin découvert pendant l'audit Lot 1 (Phase 2 sortie du lot)

## Contexte

Le backend `apps/availability` a été **supprimé** (absent de `apps/`, de
`apps/api/urls.py`, de `LOCAL_APPS`, des migrations). Côté frontend, la feature
`JanguBiUI/src/features/allo-pretre/` et le snapshot OpenAPI
`JanguBiUI/src/types/api.ts` référencent encore `/v1/availability/*` → ces appels
tapent un backend inexistant (**404**). `NEXT_PUBLIC_ENABLE_API_MOCKING=false` par
défaut → la feature ne fonctionne plus qu'avec MSW.

L'ancienne API était un **DRF ModelViewSet** (style non-HackSoft) avec un enum de
rôle anglais (`PRIEST|SISTER|DEACON|RELIGIOUS|BISHOP`) et un modèle `Minister`
**standalone** (lien `user_id` optionnel), incompatible avec le modèle territorial
`apps/org` et les rôles `PastoralRole`/`UserRole` du projet.

## Neutralisation déjà effectuée (Lot 1, Phase 2)

- Feature `allo-pretre` **gated derrière `env.ENABLE_API_MOCKING`** : page fidèle
  (`/app/allo-pretre`), admin (`/app/admin/availability`) et entrée de nav admin
  affichent « en préparation » quand le mocking est off → plus de 404 en prod.
- `api.ts` **non modifié** : la régénération a été reportée ici car (a)
  `openapi-typescript` n'est pas installé, (b) l'endpoint `/api/schema/` renvoie
  500 dans l'environnement courant, et (c) retirer les schémas `availability` à la
  main casserait les imports de types de la feature (`MinisterList`, `Parish`,
  `ServiceType`, `RoleEnum`). À traiter dans la reconstruction ci-dessous.

## Périmètre de reconstruction (HackSoft)

### Backend — nouvelle app `apps/availability`
- `Minister` : **FK vers `users.BaseUser`** (pas standalone) + `org.Parish`.
  Le « rôle » du ministre doit dériver de `PastoralRole` (pas d'enum anglais).
- `ServiceType` : `name`, `slug`, `description`, `duration_minutes`.
- Disponibilités : créneaux **hebdomadaires** + **exceptions** (dates ponctuelles).
- Upload photo via `apps.files` (un fichier valide ssi `upload_finished_at`).
- Couches strictes : `models / services / selectors / serializers / apis /
  permissions`. **Pas de ViewSet** : une `APIView` par action, `@extend_schema`
  sur chaque endpoint, pagination `LimitOffsetPagination`.
- Brancher dans `apps/api/urls.py` (`availability/`) + `LOCAL_APPS`.

### Frontend
- **Régénérer** `JanguBiUI/src/types/api.ts` via `openapi-typescript` contre le
  nouveau schéma (les chemins `/v1/availability/*` actuels disparaissent et sont
  remplacés par le nouveau contrat HackSoft).
- Réaligner `src/features/allo-pretre/api/*` sur les nouveaux types.
- Réactiver la feature (retirer le gate `ENABLE_API_MOCKING` des pages
  `app/allo-pretre/page.tsx`, `app/admin/availability/page.tsx`, et de l'entrée
  de nav `app/admin/page.tsx`).
- Mettre à jour les handlers MSW `src/testing/mocks/handlers/allo-pretre.ts`.

## Contrat actuel attendu par le frontend (référence — à remplacer)
- `GET/POST /v1/availability/ministers/` → `Minister { id, first_name, last_name,
  slug, photo?, role, role_display, parish, parish_id, user_id?, is_active }`
  (POST multipart `File`).
- `GET/POST/PATCH /v1/availability/parishes/` → `Parish { id, name, slug, address?,
  city, country?, latitude?, longitude?, is_active? }` ⚠️ **collision** avec
  `org.Parish` — à réconcilier (réutiliser `org.Parish`).
- `GET/POST/PATCH /v1/availability/services/` → `ServiceType { id, name, slug,
  description?, duration_minutes? }`.
- Actions `{slug}/available/` (créneaux d'une date) et `{slug}/weekly/`.

## Critères d'acceptation
- [ ] `GET /api/v1/availability/ministers/` répond 200 (plus de 404).
- [ ] `Minister` lié à `BaseUser` + `org.Parish` ; rôle dérivé de `PastoralRole`.
- [ ] `api.ts` ne contient plus l'ancien contrat ; la feature `allo-pretre` compile
      et fonctionne sans MSW.
- [ ] Couverture de tests ≥ 80 % sur la nouvelle app (services/selectors/apis).
- [ ] Doc OpenAPI (`@extend_schema`) complète.
