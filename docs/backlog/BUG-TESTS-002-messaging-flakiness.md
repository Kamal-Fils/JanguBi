# BUG-TESTS-002 — Flakiness messaging (async/Redis/Fernet) sous charge — quarantiner avant promotion main

- **Statut** : À FAIRE
- **Priorité** : 🟠 P2 — **bloquant pour toute promotion `develop → main`**
- **Créé le** : 2026-06-01 (audit Lot 1 / Phase B)

## Symptôme

Lors d'une exécution **suite complète** (≈ 750 tests, ~6–10 min), `apps/messaging/tests/test_apis.py`
a produit **un burst de ~20 ERRORs de setup non déterministes** + 2 FAILED, sur des tests
qui passent tous en isolation. Tests concernés (setup ERROR) :
`test_block_create_*`, `test_block_list_returns_200`, `test_block_delete_returns_204`,
`test_message_delete_*`, `test_message_react_post/delete_*`, `test_message_read_*`,
`test_message_send_is_idempotent_*`, `test_message_send_returns_400_when_sender_blocked`.

## Caractérisation (preuve)

**8 runs « suite complète »** ont été comparés (Lot 1 vs base pré-Lot-1) :

| Run | Branche | block/react/read/delete ERRORs |
|---|---|---|
| Baseline (post Phase 1/3/4) | lot1 | 0 |
| Post-Phase5 #1 | lot1 | **~20** ← unique occurrence |
| Post-Phase5 #2 / #3 / #4 | lot1 | 0 / 0 / 0 |
| Base #1 / #2 | refonte | 0 / 0 |
| Verif3 (messaging exécuté EN DERNIER, après news/users) | lot1 | 0 |

- **1 occurrence sur 8 runs**, jamais reproduite (4 runs lot1 suivants + 2 runs base + ordre adverse).
- **Pas une contamination Lot 1** : aucun test des apps touchées (users/clergy_accounts/documents/news)
  ni de messaging n'utilise `TransactionTestCase`/`transaction=True` → tous transactionnels (rollback)
  → fuite d'état DB inter-tests **structurellement impossible**. Lot 1 n'ajoute aucun état module-level/signal/cache.
- **Cause probable** : le stack **async / Redis channel layer / `EncryptedTextField` (Fernet)** de
  `apps/messaging` sous charge pleine (épuisement de connexions / état de boucle async), indépendant de Lot 1.

## Action

- [ ] Reproduire sous charge (boucler la suite complète N fois) et capturer le traceback du setup ERROR.
- [ ] Isoler la ressource fautive (pool de connexions DB, channel layer Redis, ou cipher Fernet).
- [ ] Quarantiner les tests messaging flaky (`pytest.mark.flaky` / `-p no:randomly`) ou corriger la fixture.
- [ ] **Bloquant** : ne pas promouvoir `develop → main` tant que la suite complète n'est pas stable
      sur ≥ 3 runs consécutifs.
