# BUG-TESTS-001 — Résorber les 12 échecs de tests baseline pré-existants

- **Statut** : À FAIRE
- **Priorité** : 🟡 P3 (pré-existant, non bloquant pour Lot 1)
- **Créé le** : 2026-06-01 (audit Lot 1 / Phase B)

## Contexte

La suite backend complète présente **12 échecs pré-existants**, **antérieurs à Lot 1**
et **reproduits à l'identique sur `feat/hierarchie-refonte`** (2 runs base : mêmes
tests). Lot 1 ne les introduit pas. Ils doivent être corrigés indépendamment.

## Set exact (noms)

**bible (5)** — `apps/bible/tests/services/test_import_service.py` :
- `ImportServiceTests::test_ensure_testaments_created`
- `ImportServiceTests::test_import_format_a`
- `ImportServiceTests::test_import_format_b_skips_empty_verses`
- `ImportServiceTests::test_resolve_book_info_psalms_heuristic`
- `apps/bible/tests/tasks/test_tasks.py::TaskTests::test_compute_embeddings_task_with_stub`

**messaging (6, dont 1 flaky)** :
- `test_apis.py::test_conversation_delete_returns_204`
- `test_apis.py::test_conversation_delete_requires_authentication`
- `test_apis.py::test_conversation_delete_returns_403_for_non_participant`
- `test_selectors.py::test_message_list_cursor_pagination_with_before_id` *(flaky : passe ~50% des runs)*
- `test_services.py::test_conversation_export_generate_sets_completed_at`
- `test_services.py::test_conversation_export_generate_without_export_id_creates_new_export`

**errors (1)** :
- `apps/errors/tests/test_apis.py::test_trigger_exception_raises_for_super_admin`

## Critère d'acceptation
- [ ] Suite backend complète verte (hors flakiness traitée par BUG-TESTS-002).
- [ ] `pytest --reuse-db` stable sur 3 runs consécutifs.
