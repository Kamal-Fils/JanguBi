# DESIGN.md — Jàngu Bi · Système de Design & Architecture UI

> Document de référence pour la conception des maquettes client.  
> Fondé sur l'inventaire complet du backend implémenté (v2.4).

---

## 1. Vision & Positionnement

**Jàngu Bi** (« Écoute » en wolof) est la plateforme numérique de l'Église catholique du Sénégal. Elle fédère les fidèles, les paroisses et les diocèses autour de quatre piliers :

| Pilier | Description |
|--------|-------------|
| 🙏 **Spiritualité** | Bible, Rosaire, Liturgie quotidienne |
| 📰 **Information** | Actualités globales, diocésaines et paroissiales |
| 📺 **Média** | TV catholique (YouTube live & replay) |
| 💬 **Communauté** | Messagerie confidentielle fidèle ↔ prêtre, demandes de documents |

**Direction stylistique :** Éditorial / spirituel — chaleur, lisibilité, noblesse sans austérité.  
**Cible :** Mobile-first (smartphone Android bas de gamme au Sénégal) + tablette + desktop web.

---

## 2. Espaces Utilisateur par Rôle

Le système comporte **6 rôles** avec des espaces distincts.

### 2.1 Arborescence des rôles

```
SUPER_ADMIN
└── Accès total + gestion des admins de province/diocèse

PROVINCE_ADMIN
└── Gestion des diocèses de la province

DIOCESE_ADMIN
└── Gestion des paroisses du diocèse + articles diocésains + documents

PARISH_ADMIN
└── Gestion de la paroisse + articles paroissiaux + documents

CHURCH_ADMIN
└── Opérationnel : traitement demandes documents, articles paroissiaux
    (ne peut pas dépublier les articles)

FIDELE (utilisateur final)
└── Lecture, messagerie, demandes de documents
```

### 2.2 Espace FIDÈLE — Application Mobile & Web

```
/ (non connecté)
├── Accueil public           → Articles globaux + Bible du jour + Liturgie du jour
├── Actualités               → Feed global filtrable par catégorie
├── Bible                    → Navigation Testament > Livre > Chapitre > Versets
├── Rosaire                  → Rosaire du jour, mystères, prières
├── TV                       → Live catholique + vidéos par catégorie
└── Connexion / Inscription

/ (connecté — fidèle)
├── Accueil personnalisé     → Articles de ma paroisse + global + liturgie
├── Actualités
│   ├── Globales
│   ├── Ma paroisse          → Requiert paroisse principale dans le profil
│   └── Mon diocèse
├── Bible                    → idem public
├── Rosaire                  → idem public
├── Liturgie                 → Offices du jour (Laudes, Messe, Tierce, Sexte, None, Vêpres, Complies)
├── TV                       → idem public
├── Messagerie               → Conversations privées avec prêtres
│   ├── Liste conversations
│   ├── Fenêtre de chat      → Messages chiffrés, réactions emoji, export
│   └── Notifications
├── Mes Documents            → Demandes de certificats sacramentels
│   ├── Nouvelle demande     → Type (Baptême, 1ère communion, Confirmation, Mariage, Parrain)
│   ├── Suivi en temps réel  → Statuts : Soumis → Vérification → Validé → Déposé
│   └── Détail + compléments
└── Mon Profil
    ├── Mes informations     → Nom, prénom, email, téléphone, paroisse principale
    ├── Sécurité             → Changer mot de passe, changer email
    └── Supprimer mon compte
```

### 2.3 Espace CHURCH_ADMIN / PARISH_ADMIN — Back-office Paroisse

```
/admin/ (parish_admin | church_admin)
├── Tableau de bord
│   ├── Demandes documents en attente (compteur)
│   ├── Articles en brouillon (compteur)
│   └── Messages non lus
├── Actualités
│   ├── Liste articles (tous statuts)
│   ├── Créer article        → Titre, contenu, catégorie, portée, image
│   ├── Modifier / Publier / Dépublier* / Supprimer
│   └── (* church_admin ne peut pas dépublier)
├── Demandes Documents
│   ├── File de traitement   → Filtres : statut, type, date
│   ├── Détail demande       → Infos fidèle + justificatifs + historique
│   └── Actions : Démarrer vérif → Demander info → Valider → Rejeter → Déposer
└── Mon profil
```

### 2.4 Espace DIOCESE_ADMIN — Back-office Diocèse

```
/admin/diocese/
├── Tableau de bord          → Statistiques paroisses du diocèse
├── Actualités diocésaines   → Articles scope=diocese
├── Demandes Documents       → Vue consolidée diocèse
└── Gestion des admins paroissiaux → Créer / activer / désactiver
```

### 2.5 Espace PROVINCE_ADMIN — Back-office Province

```
/admin/province/
├── Tableau de bord          → Statistiques diocèses
└── Admins diocèse           → Créer / gérer
```

### 2.6 Espace SUPER_ADMIN — Console globale

```
/admin/super/
├── Tableau de bord global
├── Gestion utilisateurs     → Liste / Créer / Activer-Désactiver / Supprimer / Logs audit
├── Toutes actualités        → Vue transversale (tous scopes)
├── TV                       → Gestion vidéos et catégories
├── Bible / Rosaire          → Import de contenu
└── Configuration système
```

---

## 3. Design Tokens

### 3.1 Palette de couleurs

```css
/* ── Couleurs de marque ── */
--color-primary:         #8B1A2D;   /* Rouge Cardinal — couleur principale */
--color-primary-light:   #B02035;   /* Hover / états actifs */
--color-primary-dark:    #5E1020;   /* Pressed / emphase */
--color-primary-surface: #FDF0F2;   /* Arrière-plans teintés primaire */

--color-gold:            #C8922A;   /* Or — accents liturgiques, icônes */
--color-gold-light:      #E8B84B;   /* Badges, highlights */
--color-gold-surface:    #FDF8EE;   /* Surfaces dorées légères */

/* ── Neutrals ── */
--color-neutral-900: #1A1614;   /* Texte principal */
--color-neutral-700: #3D3430;   /* Texte secondaire */
--color-neutral-500: #7A706C;   /* Labels, placeholders */
--color-neutral-300: #C4BCB8;   /* Bordures, séparateurs */
--color-neutral-100: #F5F3F2;   /* Surfaces, backgrounds */
--color-neutral-0:   #FFFFFF;   /* Blanc pur */

/* ── Sémantique ── */
--color-success:         #2E7D4F;
--color-success-surface: #EDF7F1;
--color-warning:         #B45309;
--color-warning-surface: #FEF6E7;
--color-error:           #C0392B;
--color-error-surface:   #FDEDEC;
--color-info:            #1A5F8A;
--color-info-surface:    #EBF4FA;

/* ── Overlay ── */
--color-scrim: rgba(26, 22, 20, 0.60);
```

### 3.2 Typographie

**Polices choisies :**

| Usage | Famille | Caractère |
|-------|---------|-----------|
| Titres, headings | **Playfair Display** | Serif élégant, spirituel, autorité |
| Corps de texte | **Inter** | Sans-serif lisible, multilingue (wolof, français) |
| UI labels, boutons | **Inter Medium / SemiBold** | Compact, fonctionnel |
| Citations, versets | **Playfair Display Italic** | Distinction des textes sacrés |

```css
/* Google Fonts : Playfair Display (400, 600, 700, 700i) + Inter (400, 500, 600) */

/* ── Échelle typographique ── */
--text-display: clamp(2rem,    4vw,   3rem);      /* Héros, grand titre */
--text-h1:      clamp(1.75rem, 3vw,   2.25rem);
--text-h2:      clamp(1.375rem,2vw,   1.75rem);
--text-h3:      clamp(1.125rem,1.5vw, 1.375rem);
--text-h4:      1.125rem;
--text-body-lg: 1.0625rem;   /* 17px — confort lecture mobile */
--text-body:    1rem;        /* 16px */
--text-body-sm: 0.875rem;    /* 14px */
--text-caption: 0.75rem;     /* 12px */
--text-label:   0.6875rem;   /* 11px — badges, tags */

/* ── Line heights ── */
--leading-tight:   1.25;
--leading-snug:    1.375;
--leading-normal:  1.5;
--leading-relaxed: 1.625;  /* Corps long — liturgie, articles */
--leading-loose:   2;      /* Versets bibliques */
```

### 3.3 Espacement (grille 4px)

```css
--space-1:  0.25rem;   /*  4px */
--space-2:  0.5rem;    /*  8px */
--space-3:  0.75rem;   /* 12px */
--space-4:  1rem;      /* 16px */
--space-5:  1.25rem;   /* 20px */
--space-6:  1.5rem;    /* 24px */
--space-8:  2rem;      /* 32px */
--space-10: 2.5rem;    /* 40px */
--space-12: 3rem;      /* 48px */
--space-16: 4rem;      /* 64px */
--space-section: clamp(3rem, 6vw, 6rem);
```

### 3.4 Border Radius

```css
--radius-sm:   0.25rem;   /*  4px — tags, badges */
--radius-md:   0.5rem;    /*  8px — cartes compactes */
--radius-lg:   0.75rem;   /* 12px — cartes articles */
--radius-xl:   1rem;      /* 16px — modales, drawers */
--radius-2xl:  1.5rem;    /* 24px — hero cards */
--radius-full: 9999px;    /* Pilules, avatars */
```

### 3.5 Ombres

```css
--shadow-sm: 0 1px 3px rgba(26,22,20,.08), 0 1px 2px rgba(26,22,20,.06);
--shadow-md: 0 4px 12px rgba(26,22,20,.10), 0 2px 4px rgba(26,22,20,.06);
--shadow-lg: 0 12px 32px rgba(26,22,20,.12), 0 4px 8px rgba(26,22,20,.06);
--shadow-xl: 0 24px 48px rgba(26,22,20,.14);
```

### 3.6 Animations

```css
--duration-fast:   150ms;
--duration-normal: 250ms;
--duration-slow:   400ms;
--ease-out:   cubic-bezier(0.16, 1, 0.3, 1);
--ease-in-out: cubic-bezier(0.45, 0, 0.55, 1);
```

---

## 4. Composants UI Clés

### 4.1 Navigation mobile (Bottom Tab Bar)

```
┌────────┬────────┬────────┬────────┬────────┐
│  🏠    │  📰    │  📖    │  💬 3  │  👤   │
│Accueil │Actus   │Spirituel│Messages│Profil  │
└────────┴────────┴────────┴────────┴────────┘
```
- Badge compteur rouge sur Messagerie (WebSocket temps réel)
- L'onglet Spirituel ouvre un bottom sheet : Bible / Rosaire / Liturgie / TV

### 4.2 Carte Article (`ArticleCard`)

```
┌───────────────────────────────────────┐
│  [Image de couverture — ratio 16:9]   │
│                                       │
│  [Tag catégorie]    [Badge portée]    │
│                                       │
│  Titre de l'article (Playfair,        │
│  2 lignes max, font-size h3)          │
│                                       │
│  Résumé court en une ou deux lignes   │
│  (Inter, body-sm, neutral-700)        │
│                                       │
│  Auteur · Il y a 2h · 👁 1 247 vues  │
└───────────────────────────────────────┘
```

Variantes : `compact` (liste horizontale), `hero` (pleine largeur), `minimal` (texte seul).

Badge portée : `Mondial` (primary) · `Diocèse` (info) · `Paroisse` (gold)

### 4.3 Badges Statut Documents

| Statut backend | Couleur | Label affiché |
|----------------|---------|---------------|
| `submitted` | Info bleu | Soumise |
| `under_verification` | Warning orange | En vérification |
| `info_requested` | Warning orange | Complément demandé |
| `validated` | Success vert | Validée |
| `rejected` | Error rouge | Rejetée |
| `document_deposited` | Primary cardinal | Document disponible |

### 4.4 Badges Statut Article (back-office)

| Statut | Couleur |
|--------|---------|
| `draft` | Neutral gris |
| `published` | Success vert |
| `unpublished` | Error rouge |

### 4.5 Écran Liturgie

Un `OfficeCard` par heure canonique :
- Icône distinctive + nom de l'office + heure suggérée
- Accordion : lectures, antiennes, oraisons, hymne
- Typographie liturgique : Playfair Display Italic, `--leading-loose`
- Couleur de fond `--color-gold-surface` pour les citations

Offices disponibles : Laudes · Messe · Tierce · Sexte · None · Vêpres · Complies · Lectures

### 4.6 Interface Messagerie

```
┌─────────────────────────────────┐
│  ← P. Jean Dupont               │
│  Prêtre · St-Joseph Medina      │
├─────────────────────────────────┤
│                    Bonjour Père │◄─ bulle droite (primary-surface)
│                    Il y a 5min  │
│                                 │
│  Bonjour, je suis disponible    │◄─ bulle gauche (neutral-100)
│  demain matin.                  │
│  😊 1        Il y a 3min        │
├─────────────────────────────────┤
│  [📎] Écrire un message...  [➤] │
└─────────────────────────────────┘
```

- Avertissement CGU + purge automatique à la première ouverture
- Réactions emoji sous les bulles
- Bouton export de conversation

### 4.7 Wizard Demande de Document (3 étapes)

**Étape 1 — Type de document**
Grille de 2×3 cards sélectionnables :
- Certificat de baptême
- 1ère communion
- Confirmation
- Mariage religieux
- Parrain / Marraine

**Étape 2 — Motif**
Radio buttons : Mariage religieux · Parrain/marraine · Catéchèse · Dossier paroissial · Usage personnel · Autre (+ champ libre)

**Étape 3 — Justificatifs**
Zone drag & drop + bouton parcourir + récapitulatif avant envoi

### 4.8 Player TV

```
┌─────────────────────────────────┐
│                                 │
│   [🔴 EN DIRECT]  YouTube       │
│        embed 16:9               │
│                                 │
└─────────────────────────────────┘
[Titre de l'émission en cours]

── Replays ────────────────────────
[Card] [Card] [Card] [Card] →
```

- Badge `🔴 EN DIRECT` si `is_live = true`
- Badge `📌` si `is_pinned_live = true` (live épinglé en tête)

### 4.9 Navigation Bible

```
Ancien Testament / Nouveau Testament
        ↓
  [Genèse] [Exode] [Lévitique] ...
        ↓
  Chapitre 1 · 2 · 3 · ...
        ↓
  1 Au commencement, Dieu créa...
  2 La terre était informe...
```

- Verset sélectionnable pour partage ou copie
- Playfair Italic pour le texte des versets
- `--leading-loose` pour la lisibilité

---

## 5. Écrans à Maquetter — Priorité P1

### 5.1 Espace Fidèle (10 écrans)

| # | Écran | Éléments clés |
|---|-------|--------------|
| 1 | **Splash / Onboarding** | Logo + nom + baseline en wolof + boutons Connexion/Inscription |
| 2 | **Inscription** | Email, téléphone, mot de passe, rôle=fidèle automatique → vérif email |
| 3 | **Accueil personnalisé** | Hero liturgie du jour (gold) · Feed articles ma paroisse · Section Bible · Live TV si actif |
| 4 | **Feed Actualités** | Tabs Global/Paroisse/Diocèse · Filtre catégories (chips) · Infinite scroll |
| 5 | **Détail Article** | Image pleine largeur · Titre Playfair · Contenu Inter · Articles liés |
| 6 | **Bible** | Sélecteur testament/livre/chapitre · Versets scrollables · Bouton partage |
| 7 | **Liturgie du jour** | Date + couleur liturgique · Liste offices · Accordion contenu |
| 8 | **TV** | Player live en haut · Grille replays par catégorie |
| 9 | **Messagerie** | Liste conversations (prêtres disponibles) · Détail chat · Notifications |
| 10 | **Mes Documents** | Liste demandes + badge statut · Bouton "Nouvelle demande" · Wizard |

### 5.2 Espace Admin — Back-office (6 écrans)

| # | Écran | Éléments clés |
|---|-------|--------------|
| 11 | **Dashboard** | Compteurs : demandes en attente · brouillons · utilisateurs actifs · Graphique activité |
| 12 | **Éditeur Article** | Formulaire : titre · contenu (rich text) · catégorie · portée · image cover · actions publier |
| 13 | **Liste Articles** | Table filtrable statut/catégorie · Actions rapides inline (publier, supprimer) |
| 14 | **File Documents** | Kanban 6 colonnes (1 par statut) ou table avec filtres · Drag & drop entre colonnes |
| 15 | **Détail Demande** | Timeline des statuts · Justificatifs téléchargeables · Notes internes · Actions contextuelles |
| 16 | **Gestion Utilisateurs** | Table + filtres rôle/statut · Toggle actif · Créer admin · Voir logs audit |

---

## 6. Grilles & Breakpoints

```
Mobile:  320px – 767px    → 1 colonne, padding 16px, gutter 12px
Tablet:  768px – 1023px   → 2 colonnes, padding 24px, gutter 16px
Desktop: 1024px – 1439px  → 3 colonnes, padding 32px, gutter 24px
Wide:    1440px+           → 4 colonnes max, conteneur 1280px centré

Back-office: sidebar 240px fixe + zone contenu fluide
```

---

## 7. Iconographie

- Bibliothèque : **Lucide Icons** (open source, léger, React-compatible)
- Taille UI standard : 20px · Navigation : 24px · Inline texte : 16px
- Icônes métier à créer sur mesure : croix catholique stylisée, calice, rosaire, colombe

---

## 8. États & Micro-interactions

| Situation | Comportement UI |
|-----------|----------------|
| Chargement liste | Skeleton cards avec pulse animation |
| Pull-to-refresh | Spinner en haut des feeds (mobile) |
| Action réussie | Toast vert en bas, 3 secondes, auto-dismiss |
| Erreur réseau | Toast rouge + bouton "Réessayer" |
| Empty state | Illustration thématique + message contextuel + CTA |
| Hors-ligne | Bandeau haut de page "Mode hors-ligne — données en cache" |
| Badge messagerie | Compteur rouge mis à jour en temps réel (WebSocket) |
| Nouveau statut document | Notification push + badge dans "Mes Documents" |

---

## 9. Accessibilité (WCAG 2.1 AA minimum)

- Contraste texte : ≥ 4.5:1 normal, ≥ 3:1 large
- Touch targets : ≥ 44×44px sur tous les éléments cliquables
- Labels ARIA sur toutes les icônes sans texte visible
- Navigation clavier complète (focus visible, tab order logique)
- `prefers-reduced-motion` : animations désactivées si l'OS le demande
- Textes alternatifs sur toutes les images (couvertures articles, icônes)

---

## 10. Stack Frontend Recommandée

| Couche | Choix | Raison |
|--------|-------|--------|
| Framework | **Next.js 15** (App Router) | SSR/SSG liturgie & bible, ISR articles, SEO |
| UI base | **shadcn/ui** + composants custom | Accessible, headless, personnalisable |
| State serveur | **TanStack Query v5** | Cache, pagination, invalidation mutation |
| State global | **Zustand** | Légère — notifications, auth, préférences |
| Forms | **React Hook Form + Zod** | Validation robuste (wizard documents) |
| Styles | **Tailwind CSS v4** + CSS variables tokens | Rapide, thémable via les tokens ci-dessus |
| WebSocket | **WebSocket natif browser** | Messagerie temps réel (Django Channels déjà en place) |
| Auth | **JWT HTTP-only cookie** | Conforme au backend SimpleJWT |
| Médias | **next/image** + optimisation | Performances images couvertures |
| Mobile (V2) | **Expo / React Native** | Partage logique métier avec le web |

---

## 11. Fonctionnalités Hors Périmètre V1

Ces fonctionnalités sont dans le SRS mais **pas encore implémentées** côté backend — **ne pas maquetter pour la présentation client V1**.

| Fonctionnalité | Version prévue |
|----------------|---------------|
| Module Paroisses (annuaire, carte, localisation) | V2 |
| Module Diocèses (hiérarchie, gestion) | V2 |
| Q&A IA catholique (RAG / Gemini) | V2 (désactivé) |
| Rosaire recherche vectorielle | V2 (désactivé) |
| Événements / Agenda paroissial | V3 |
| Dons en ligne | V3 |
| App mobile native React Native | V2 |

---

## 12. Checklist Maquette Client

### Figma / Design
- [ ] Bibliothèque de tokens (couleurs, typo, spacing, radius, ombres)
- [ ] Composants : ArticleCard (3 variantes) · StatusBadge · OfficeCard · ChatBubble · DocumentWizard
- [ ] Thème clair finalisé (thème sombre optionnel en bonus)
- [ ] Auto-layout sur tous les composants (responsive)

### Flux à couvrir (mobile)
- [ ] Onboarding complet : Splash → Inscription → Vérif email → Choix paroisse → Accueil
- [ ] Lecture article : Accueil → Feed → Détail article
- [ ] Demande document : Mes docs → Wizard 3 étapes → Confirmation → Suivi statut
- [ ] Messagerie : Liste prêtres → Nouvelle conversation → Chat

### Flux à couvrir (back-office)
- [ ] Login admin → Dashboard
- [ ] Traitement demande : File → Détail → Action (Valider ou Demander info)
- [ ] Publication article : Créer → Éditeur → Publier

### Annotations
- [ ] Chaque écran annoté avec : rôle(s) autorisés, données affichées, actions disponibles
- [ ] États vides et états d'erreur maquettés pour les écrans P1
- [ ] Prototype cliquable couvrant les 3 flux mobiles + 2 flux admin
