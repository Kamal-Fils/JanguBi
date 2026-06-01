# Audit métier & refonte — Plateforme Jàngu Bi

**Objet** : correction du modèle hiérarchique ecclésial, refonte des process, dashboards par rôle et fonctionnalités manquantes.
**Méthode** : audit du code source (`apps/`), confrontation au SRS v2.4, et vérification de la réalité canonique (Code de droit canonique, cann. 515-552 et 537) et de la structure réelle de l'Église au Sénégal.
**Date** : mai 2026

---

## 1. Verdict en une page

Le problème central n'est pas un bug isolé : c'est une **fondation manquante**. Toute la logique métier (dons, documents, contenus, permissions) a été construite **avant** le modèle territorial, qui est explicitement marqué *« P1 BLOQUANT — pas encore implémenté »* dans `CLAUDE.md`. Résultat : les modules existants « flottent » sans rattachement réel à une paroisse.

Les trois erreurs structurantes :

1. **Le modèle territorial `Province → Diocèse → Paroisse → Église` n'existe pas en base.** Les apps qui devraient s'y rattacher utilisent des substituts (`scope_id` entier, `parish_name` en texte libre, `primary_parish` placeholder). Conséquence directe : votre remarque *« une paroisse doit avoir au moins une église, et ce n'est pas le cas ici »* est exacte — la règle RG-ORG-04 du SRS n'est appliquée nulle part car l'entité `Church` n'existe pas.

2. **Confusion entre rôle pastoral et rôle administratif.** Le code mélange « qui est le prêtre » (réalité canonique) et « qui a quels droits dans le logiciel » (RBAC). Or ce sont deux dimensions distinctes. C'est la source de votre confusion sur « le curé, le curé principal, son supérieur ».

3. **Absence de scoping territorial des permissions.** `IsAnyAdmin` autorise *tout* admin sur *toutes* les données. Un curé de la paroisse A peut techniquement voir les dons et documents de la paroisse B. Le `RoleAssignment` scopé du SRS n'est pas implémenté.

Une refonte est donc justifiée, mais elle est **séquentielle** : on pose d'abord le socle territorial, puis on rebranche dons / documents / contenus dessus.

---

## 2. La hiérarchie canonique réelle (corrigée et sourcée)

Votre intuition métier est presque juste, avec une correction importante sur le curé.

### 2.1 Ce que dit le droit canonique

- **La paroisse** est *« la communauté précise de fidèles… dont la charge pastorale est confiée au curé, comme à son pasteur propre, sous l'autorité de l'Évêque diocésain »* (canon 515 §1).
- **Il y a UN seul curé par paroisse** (le « pasteur propre »), pas un curé par église. C'est le point à corriger dans votre modèle mental.
- **Le curé peut être assisté de un ou plusieurs vicaires** (canon : *« selon l'importance de la charge, le curé peut être assisté par un ou plusieurs prêtres appelés vicaires »*). Dans les grandes paroisses rurales, un vicaire est souvent placé **à la tête d'une église annexe / succursale**, mais il **reste sous l'autorité du curé**.
- **Le supérieur du curé est l'Évêque diocésain** (canon 515 §1). C'est l'évêque qui érige, modifie ou supprime les paroisses (canon 515 §2) et qui nomme le curé (canon 523).
- **Chaque paroisse doit avoir un Conseil pour les affaires économiques** qui assiste le curé dans la gestion des biens (canon 537). C'est directement pertinent pour vos dashboards financiers.

### 2.2 Traduction correcte pour votre modèle

| Réalité canonique | Ce que vous appeliez | Dans le modèle de données |
|---|---|---|
| Curé (pasteur propre, 1 par paroisse) | « curé principal » | Rôle **au niveau Paroisse** |
| Vicaire desservant une église annexe | « le curé de chaque église » | Rôle **au niveau Église**, rattaché au curé |
| Évêque diocésain | « son supérieur » | Autorité **au niveau Diocèse** |
| Église principale + annexes (succursales) | « plusieurs églises » | `Church` (1..N) dont une `is_main=True` |

**Conclusion clé** : le « curé principal » est une autorité **de paroisse**, pas d'église. Le total des fidèles et le flux de dons qu'il veut voir s'agrègent donc **au niveau paroisse, toutes églises confondues**. C'est ce qui pilote la conception du dashboard.

### 2.3 Structure réelle au Sénégal (à utiliser pour le seed)

- **1 seule province ecclésiastique** : Dakar (couvre tout le pays).
- **7 diocèses** : l'archidiocèse métropolitain de Dakar + 6 suffragants (Thiès, Kaolack, Saint-Louis, Ziguinchor, Tambacounda, Kolda). Conforme au SRS.
- Ordre de grandeur pour dimensionner : l'archidiocèse de Dakar compte ~38 paroisses, ~151 prêtres, 330 000+ fidèles.

> ⚠️ **Donnée volatile à ne jamais coder en dur** : l'archevêque de Dakar est désormais **Mgr André Guèye** (installé en mai 2025, en remplacement de Mgr Benjamin Ndiaye). Les évêques changent : le champ `bishop_name` doit rester éditable et ne jamais servir de clé. Idem pour les noms de curés.

---

## 3. Erreurs métier détectées dans le code (preuves)

| # | Constat dans le code | Pourquoi c'est un problème | Gravité |
|---|---|---|---|
| E1 | `apps/org/` (Province/Diocèse/Paroisse/Église) **n'existe pas**. | Aucune entité à rattacher. Toute la logique de scope est fictive. | 🔴 Bloquant |
| E2 | `Profile.primary_parish` est décrit comme `IntegerField` (placeholder) dans le SRS, mais une version du code le déclare en `ForeignKey("org.Parish")`. | Incohérence entre doc et code : soit la FK pointe vers une app inexistante (migration cassée), soit le SRS est périmé. **À réconcilier en priorité.** | 🔴 Bloquant |
| E3 | Aucune entité `Church` → la règle « une paroisse a ≥ 1 église, dont 1 principale » (RG-ORG-03/04) n'est appliquée nulle part. | Exactement le problème que vous signalez. | 🔴 Bloquant |
| E4 | Deux systèmes de dons incompatibles coexistent : le SRS décrit `Payment` + `ParishDonationConfig` (PayDunya, scopé paroisse, dons anonymes ≤ 25 000 FCFA), mais le code réel (`apps/donations/`) implémente `Donation` + `DonationCampaign` avec `scope_type` / `scope_id` (entier). | `donation_dashboard_for_parish(parish_id)` agrège sur un `scope_id` entier qui ne référence aucune vraie paroisse. Le « flux de dons par paroisse » que veut le curé n'est pas fiable. | 🔴 Critique |
| E5 | `DocumentRequest` n'a **aucune FK vers une paroisse** ; le back-office filtre par `parish_name` (texte libre). | Impossible de router une demande vers la bonne paroisse/curé. Risque d'homonymie et de fuite inter-paroisses. | 🔴 Critique |
| E6 | `IsAnyAdmin` autorise tout rôle admin sans vérifier le scope territorial. Le `RoleAssignment` scopé du SRS n'est pas implémenté. | Un curé de A voit les données de B. Le cloisonnement RG-RBAC du SRS n'existe pas. | 🔴 Critique |
| E7 | `PastoralRole` (archevêque/évêque/prêtre/diacre/religieux/fidèle) listé comme « à implémenter ». Seul `UserRole` (admin) existe. | Le logiciel ne sait pas distinguer un curé d'un vicaire d'un sacristain laïc. | 🟠 Majeur |
| E8 | `apps/availability/` (CRUD ministre) non branché dans `api/urls.py` ; `apps/news` n'a qu'un seul type de contenu au lieu des 3 prévus (Annonce / Article / Lettre pastorale). | Fonctionnalités à moitié livrées. | 🟡 Moyen |

---

## 4. Modèle de données cible (le socle à poser d'abord)

### 4.1 Deux dimensions de rôle, à séparer proprement

C'est la clé pour lever la confusion. **Ne jamais fusionner ces deux axes.**

**Dimension A — Identité pastorale** (qui est la personne dans l'Église) :
`PastoralRole` = archevêque · évêque · curé · vicaire · diacre · religieux · fidèle.

**Dimension B — Capacités dans le logiciel** (ce que le compte peut faire), via `RoleAssignment` scopé :
`super_admin · province_admin · diocese_admin · parish_admin · church_admin · fidele`.

Une même personne combine les deux. Exemples concrets :

| Personne | Identité pastorale | RoleAssignment (capacité + scope) |
|---|---|---|
| L'abbé X, curé de Saint-Pierre | curé | `parish_admin` scopé à *Paroisse Saint-Pierre* |
| L'abbé Y, vicaire à l'annexe Sainte-Anne | vicaire | `church_admin` scopé à *Église Sainte-Anne* |
| Mgr l'évêque de Thiès | évêque | `diocese_admin` scopé à *Diocèse de Thiès* |
| Un sacristain laïc | fidèle | `church_admin` scopé à une église (purement opérationnel) |

→ Le « curé principal » = `parish_admin`. Le « curé de chaque église » = `church_admin` (vicaire ou laïc). Le « supérieur » = `diocese_admin` (évêque). La hiérarchie informatique colle enfin à la hiérarchie canonique.

### 4.2 Entités à créer dans `apps/org/`

```
EcclesiasticalProvince
  └─ Diocese (is_metropolitan, bishop_name éditable)
       └─ [Doyenné / Décanat]   ← optionnel mais recommandé (cf. §4.3)
            └─ Parish (le curé est ici ; juridiquement « propriétaire » des dons)
                 └─ Church (is_main unique par paroisse ; annexes = succursales)
                      └─ MassTime
```

Règles à implémenter **au niveau base** (pas seulement applicatif) :

- **RG-ORG-03** : une paroisse a exactement une `Church` avec `is_main=True` (index partiel unique).
- **RG-ORG-04** : une paroisse n'est `is_active=True` que si elle a ≥ 1 église principale. À vérifier dans le service de création **et** par contrainte.
- **RG-ORG-01** : un seul diocèse `is_metropolitan=True` par province (index partiel).
- Le diocèse d'une église se **déduit** (`church.parish.diocese`) — pas de FK redondante.

### 4.3 Recommandation d'ajout : le Doyenné (décanat)

Le SRS s'arrête au diocèse. Mais entre l'évêque et 38 paroisses, il existe canoniquement le **doyenné** (groupe de paroisses voisines, dirigé par un *vicaire forain / doyen*, cf. canon 524). Sans lui, le `diocese_admin` doit gérer 38 paroisses à plat. Ajouter une entité `Deanery` optionnelle (une paroisse appartient à 0 ou 1 doyenné) prépare la délégation V2 et un futur dashboard de doyen. À discuter avec l'archevêché — ce n'est pas bloquant pour la V1.

### 4.4 Conseil pour les affaires économiques (canon 537)

Prévoir une notion de **membres du conseil économique** par paroisse (rôle de lecture financière sans droit de configuration). Cela évite de tout faire reposer sur le seul compte du curé et reflète l'obligation canonique.

---

## 5. Dashboards par rôle (cœur de la demande)

Principe directeur : **chaque dashboard ne montre que le scope de l'utilisateur**, agrège au bon niveau, et met en avant 3-5 indicateurs actionnables, pas un mur de chiffres.

### 5.1 Fidèle (Espace Membre)
Objectif : rester relié à sa paroisse et contribuer simplement.
- Prochaines messes de **sa** paroisse (toutes les églises) + horaires.
- Bouton « Faire un don » pré-rempli sur sa paroisse, avec ses types de dons actifs.
- Mon historique de dons (reçus téléchargeables).
- Mes demandes de documents : statut en temps réel (Soumise → Vérification → Validée → Déposé).
- Mes documents déposés (PDF).
- Annonces/actualités de sa paroisse et de son diocèse.
- Messagerie avec un prêtre de sa paroisse.

### 5.2 Curé — `parish_admin` (le dashboard que vous décrivez)
Objectif : piloter la vie pastorale et financière de **toute la paroisse**, toutes églises confondues.
- **Fidèles** : nombre total rattachés (`primary_parish` = sa paroisse), évolution sur 12 mois, nouveaux inscrits ce mois.
- **Flux de dons** (le « flux de don » demandé) : total du mois et de l'année, **ventilé par type** (quête, denier du culte, cierge, intention) **et par église**, courbe mensuelle, comparaison N-1.
- **Denier du culte** : nombre de contributeurs, taux de couverture vs nombre de fidèles, montant moyen.
- **Demandes de documents** : file par statut, **nombre en retard de SLA** (à traiter en priorité), demandes non assignées.
- **Contenus** : brouillons à publier, dernières annonces, contenus de ses vicaires à modérer.
- **Églises de la paroisse** : liste, église principale, vicaire/responsable assigné à chacune.
- **Intentions de messe** à venir (si module activé).
- **Messages pastoraux** non lus.
- Accès à la **gestion des comptes `church_admin`** de ses propres églises (V2).

### 5.3 Vicaire / responsable d'église — `church_admin`
Objectif : gérer le quotidien d'**une seule** église annexe. Vue volontairement restreinte.
- Horaires de messe de **son** église (CRUD).
- Dons rattachés à son église (lecture seule — la consolidation reste au curé).
- Demandes de documents concernant son église (traitement, mais **pas** de dépublication d'annonces — déjà prévu au SRS).
- Rédaction d'annonces au scope de son église (publication directe, modérable a posteriori par le curé).

### 5.4 Évêque / chancellerie — `diocese_admin`
Objectif : vue consolidée du diocèse, pas de micro-gestion.
- Carte/liste des paroisses du diocèse avec : nb fidèles, total dons du mois, paroisses inactives ou sans église principale (**alerte qualité de données**).
- Classement des paroisses par volume de dons et par activité.
- Demandes de documents : vue consolidée + paroisses en retard de SLA.
- Lettres pastorales diocésaines (scope=diocese).
- Gestion des comptes `parish_admin` du diocèse (V2, délégation descendante stricte).
- Journal d'audit limité à son scope.

### 5.5 Province / archevêché — `province_admin`
Objectif : coordination, surtout lecture.
- KPI agrégés par diocèse (fidèles, dons, paroisses actives).
- Communication au scope province.
- Gestion des comptes `diocese_admin` (V2).

### 5.6 Super admin
Objectif : exploitation technique, pas pastorale.
- Santé plateforme (uptime, paiements en échec, webhooks PayDunya non réconciliés).
- Gestion globale des utilisateurs et des `RoleAssignment`.
- Qualité des données : paroisses sans église principale, comptes admin expirés, demandes orphelines.
- Journal d'audit complet.

---

## 6. Process « demande de documents » — corrigé

Le module est bien implémenté côté workflow (6 statuts, journal de statut, escalade SLA), mais il lui manque **le rattachement territorial**, ce qui le rend non scopable. Corrections :

1. **Ajouter une cible paroisse explicite.** La demande doit porter une FK `target_parish` (la paroisse qui détient les registres où le sacrement a été célébré). Le fidèle choisit cette paroisse dans une liste (pas un texte libre), idéalement pré-filtrée par lieu du sacrement. C'est ce qui permet le routage et le cloisonnement.
2. **Scoper les permissions.** Remplacer `IsAnyAdmin` (qui voit tout) par une permission qui filtre sur `target_parish ∈ scope de l'admin`. Un curé ne voit que les demandes de sa paroisse.
3. **Conserver le parcours en 4 écrans** (déjà bien conçu) : (1) type de document + motif, (2) identité, (3) infos de recherche en registres + champs dynamiques, (4) consentement + pièce jointe + envoi. Ne jamais demander folio/tome/n° d'acte au fidèle (REQ-DOC-04).
4. **Dépôt du PDF final** dans l'espace du fidèle + notification email/SMS, accès restreint au seul demandeur authentifié (et au curé destinataire si renseigné).
5. **Gate économique** : laisser le module désactivable tant que l'archevêque n'a pas tranché le modèle (gratuit / don libre / payant) — REQ-DOC-00. Le « don libre » post-soumission doit être **sans impact** sur le traitement.

Flux cible : `Fidèle soumet (→ target_parish)` → file de la paroisse → `Curé/agent : Vérification → (Complément ?) → Validée/Rejetée → PDF déposé` → notification fidèle. Chaque transition journalisée et scopée.

---

## 7. Fonctionnalités manquantes / à corriger — priorisées

| Priorité | Action | Justification |
|---|---|---|
| 🔴 P0 | Réconcilier `Profile.primary_parish` (Integer vs FK) et trancher l'état réel de `apps/org`. | On ne peut rien construire de fiable tant que c'est ambigu. |
| 🔴 P0 | Créer `apps/org` : Province → Diocèse → Paroisse → Église, avec RG-ORG-01/03/04 en contraintes BD. | Socle de tout le reste. |
| 🔴 P0 | Implémenter `PastoralRole` + `RoleAssignment` scopé + permissions territoriales (remplacer `IsAnyAdmin` flat). | Lève la confusion curé/vicaire/évêque et cloisonne réellement les données. |
| 🔴 P1 | Unifier le système de dons : abandonner `DonationCampaign.scope_id` au profit de `Payment` + FK `parish`/`church` + `ParishDonationConfig`. Migration des données existantes. | Sans ça, le « flux de dons par paroisse » du curé est faux. |
| 🔴 P1 | Ajouter `target_parish` (FK) au `DocumentRequest` + scoping des demandes. | Routage et confidentialité. |
| 🟠 P2 | Onboarding fidèle : sélection obligatoire de la `primary_parish` à l'inscription. | Sinon les compteurs « nb fidèles par paroisse » sont vides. |
| 🟠 P2 | Dashboards par rôle (section 5), en commençant par le curé. | Valeur métier la plus visible. |
| 🟠 P2 | `news` : 3 formats (Annonce / Article / Lettre pastorale) + scope cohérent. | Aligner sur le SRS. |
| 🟡 P3 | Entité `Deanery` (doyenné) optionnelle + rôle de doyen. | Prépare la délégation et soulage l'évêque. |
| 🟡 P3 | Conseil économique paroissial (rôle lecture financière). | Conformité canon 537 + ne pas tout faire reposer sur le curé. |
| 🟡 P3 | Brancher `apps/availability` dans `api/urls.py` ; finaliser `MassIntention`. | Dette technique / features à moitié livrées. |

---

## 8. Plan de refactorisation séquencé

**Étape 1 — Geler et clarifier.** Auditer l'état réel de `apps/org` et de `primary_parish` en base (les docs se contredisent). Décider : repart-on du SRS v2.4 comme source de vérité ? (recommandé).

**Étape 2 — Poser le socle territorial.** Créer `apps/org`, contraintes BD, seed (1 province, 7 diocèses, noms d'évêques éditables), migration de `primary_parish` vers FK réelle.

**Étape 3 — Refondre les rôles.** `PastoralRole` + `RoleAssignment` scopé + permissions territoriales. C'est ici que la hiérarchie devient correcte.

**Étape 4 — Rebrancher les dons.** Migrer vers `Payment` scopé paroisse/église. Réconcilier l'historique.

**Étape 5 — Rebrancher les documents.** `target_parish` + scoping.

**Étape 6 — Dashboards.** D'abord le curé (le plus attendu), puis évêque, puis les autres.

**Étape 7 — Compléter.** Doyenné, conseil économique, 3 formats de news, intentions de messe.

Chaque étape débloque la suivante. Tenter les dashboards ou les dons avant l'étape 2 reviendrait à reconstruire sur du sable.

---

## 9. Questions à trancher avec le métier (archevêché)

1. Un fidèle peut-il être rattaché à **plusieurs** paroisses, ou strictement une `primary_parish` ? (impacte les compteurs et le scoping)
2. Les dons « cierge / intention » sont-ils rattachés à **une église précise** ou à la paroisse ? (le modèle prévoit `church` nullable — à confirmer)
3. Veut-on le niveau **doyenné** dès la V1 ?
4. Modèle économique des documents : gratuit / don libre / payant ? (gate REQ-DOC-00)
5. Qui, hors le curé, a le droit de **lire** les finances d'une paroisse (conseil économique) ?