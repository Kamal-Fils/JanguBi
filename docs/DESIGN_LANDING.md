# DESIGN_LANDING.md — Jàngu Bi · Landing Page Marketing

> Document de référence pour la conception et le développement de la page de présentation publique.
> Objectif : convaincre fidèles, paroisses et diocèses d'adopter la plateforme.

---

## 1. Positionnement Marketing

### Tagline principale
> **« Jàngu Bi — L'Église du Sénégal dans votre poche »**

### Tagline alternative (plus spirituelle)
> **« Écoute. Prie. Connecte-toi à ta communauté. »**

### Proposition de valeur en une phrase
Jàngu Bi réunit Bible, Liturgie, Actualités paroissiales et messagerie confidentielle avec les prêtres — une seule application pour toute la vie catholique au Sénégal.

### Audiences cibles de la landing
| Audience | Message principal |
|----------|------------------|
| **Fidèles** | Restez connectés à votre paroisse, priez chaque jour |
| **Paroisses** | Publiez vos actualités, gérez vos demandes de documents |
| **Diocèses** | Fédérez vos communautés sur une plateforme unifiée |

---

## 2. Direction Artistique

**Style :** Moderne / lumineux / spirituel — clarté africaine, chaleur solaire, foi vivante.
**Ambiance :** Ciel ouvert, lumière naturelle, communauté joyeuse — pas austère, pas institutionnel.
**Références :** Illustrations géométriques douces, photos authentiques de fidèles sénégalais, croix épurées, dégradés bleu ciel → blanc.

---

## 3. Design Tokens — Landing Page

### 3.1 Palette — Couleur principale `#70CBFF`

```css
/* ── Bleu Ciel — Couleur signature landing ── */
--lp-primary:          #70CBFF;   /* Bleu Ciel — couleur principale */
--lp-primary-dark:     #3AADEC;   /* Hover, CTA actif */
--lp-primary-darker:   #1A8FCC;   /* Pressed, liens, icônes */
--lp-primary-light:    #A8DEFF;   /* Bordures légères, highlights */
--lp-primary-surface:  #EBF7FF;   /* Sections alternées, arrière-plans */
--lp-primary-glow:     rgba(112, 203, 255, 0.25); /* Halo, glow */

/* ── Or Liturgique — accent secondaire ── */
--lp-gold:             #C8922A;
--lp-gold-light:       #E8B84B;
--lp-gold-surface:     #FDF8EE;

/* ── Neutrals — base bleu nuit (harmonise avec le primaire) ── */
--lp-neutral-900: #0F1923;   /* Titres — bleu nuit profond */
--lp-neutral-800: #1E2D3D;   /* Corps texte sombre */
--lp-neutral-600: #4A6080;   /* Texte secondaire */
--lp-neutral-400: #8BA3BC;   /* Labels, placeholders */
--lp-neutral-200: #D6E4F0;   /* Séparateurs, bordures */
--lp-neutral-100: #EEF5FA;   /* Surfaces légères */
--lp-neutral-0:   #FFFFFF;

/* ── Dégradés signature ── */
--lp-gradient-hero:    linear-gradient(135deg, #0F1923 0%, #1A3A5C 50%, #1A8FCC 100%);
--lp-gradient-cta:     linear-gradient(135deg, #70CBFF 0%, #3AADEC 100%);
--lp-gradient-section: linear-gradient(180deg, #EBF7FF 0%, #FFFFFF 100%);
--lp-gradient-card:    linear-gradient(145deg, rgba(112,203,255,0.08) 0%, rgba(255,255,255,0) 100%);

/* ── Sémantique ── */
--lp-success: #2E7D4F;
--lp-error:   #C0392B;
```

### 3.2 Typographie

| Usage | Famille | Poids | Variable |
|-------|---------|-------|----------|
| Hero headline | **Playfair Display** | Bold 700 | `--lp-text-display` |
| Section headings | **Playfair Display** | SemiBold 600 | `--lp-text-h2` |
| Sous-titres UI | **Inter** | SemiBold 600 | `--lp-text-h4` |
| Corps marketing | **Inter** | Regular 400 | `--lp-text-body-lg` |
| CTA boutons | **Inter** | SemiBold 600 | `--lp-text-body` |
| Labels, captions | **Inter** | Medium 500 | `--lp-text-caption` |
| Citations / versets | **Playfair Display** | Italic 400 | `--lp-text-h3` |

```css
/* Google Fonts : Playfair Display (400, 600, 700, 700i) + Inter (400, 500, 600) */

--lp-text-display: clamp(2.5rem,  6vw,  4.5rem);
--lp-text-h1:      clamp(2rem,    4vw,  3.25rem);
--lp-text-h2:      clamp(1.625rem,3vw,  2.5rem);
--lp-text-h3:      clamp(1.25rem, 2vw,  1.875rem);
--lp-text-h4:      1.25rem;
--lp-text-body-lg: 1.125rem;    /* 18px */
--lp-text-body:    1rem;
--lp-text-body-sm: 0.875rem;
--lp-text-caption: 0.75rem;

--lp-leading-tight:   1.2;
--lp-leading-snug:    1.35;
--lp-leading-normal:  1.55;
--lp-leading-relaxed: 1.7;
```

### 3.3 Espacement

```css
--lp-space-2:  0.5rem;    /*  8px */
--lp-space-3:  0.75rem;   /* 12px */
--lp-space-4:  1rem;      /* 16px */
--lp-space-6:  1.5rem;    /* 24px */
--lp-space-8:  2rem;      /* 32px */
--lp-space-12: 3rem;      /* 48px */
--lp-space-16: 4rem;      /* 64px */
--lp-space-20: 5rem;      /* 80px */
--lp-space-24: 6rem;      /* 96px */

--lp-section-y:     clamp(4rem, 8vw, 8rem);
--lp-container-max: 1200px;
--lp-container-pad: clamp(1rem, 5vw, 2rem);
```

### 3.4 Border Radius

```css
--lp-radius-sm:   0.375rem;   /*  6px — tags, badges */
--lp-radius-md:   0.75rem;    /* 12px — cartes features */
--lp-radius-lg:   1.25rem;    /* 20px — cartes principales */
--lp-radius-xl:   2rem;       /* 32px — sections, mockups */
--lp-radius-full: 9999px;     /* Boutons pilule, avatars */
```

### 3.5 Ombres

```css
--lp-shadow-sm:   0 2px 8px  rgba(112, 203, 255, 0.15);
--lp-shadow-md:   0 8px 24px rgba(15, 25, 35, 0.10),
                  0 2px 8px  rgba(112, 203, 255, 0.12);
--lp-shadow-lg:   0 16px 48px rgba(15, 25, 35, 0.14),
                  0 4px  16px rgba(112, 203, 255, 0.18);
--lp-shadow-glow: 0 0 40px rgba(112, 203, 255, 0.35);
```

### 3.6 Animations

```css
--lp-duration-fast:   200ms;
--lp-duration-normal: 350ms;
--lp-duration-slow:   600ms;
--lp-ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
--lp-ease-out:    cubic-bezier(0.16, 1, 0.3, 1);
--lp-ease-smooth: cubic-bezier(0.45, 0, 0.55, 1);
```

---

## 4. Structure des Sections (Scroll Narrative)

```
01. NAVBAR
02. HERO
03. SOCIAL PROOF  — chiffres clés
04. FEATURES A    — Spiritualité (Bible, Liturgie, Rosaire, TV)
05. FEATURES B    — Actualités & Messagerie
06. FEATURES C    — Demandes de documents
07. POUR QUI ?    — 3 audiences (fidèle / paroisse / diocèse)
08. MOCKUP SHOWCASE
09. TÉMOIGNAGES
10. CTA FINAL
11. FOOTER
```

---

## 5. Détail Section par Section

### 01 — NAVBAR

```
┌──────────────────────────────────────────────────────────┐
│  [Logo Jàngu Bi]    Fonctionnalités  Paroisses  Contact  │
│                                        [Télécharger →]   │
└──────────────────────────────────────────────────────────┘
```

- **Fond :** transparent → glassmorphism (`backdrop-filter: blur(12px)` + blanc/10%) au scroll
- **Logo :** croix stylisée SVG + "Jàngu Bi" en Playfair Display SemiBold
- **CTA navbar :** pilule `--lp-gradient-cta`, texte `--lp-neutral-900`, `--lp-shadow-sm`
- **Mobile :** hamburger → drawer full-height, fond `--lp-neutral-900`

---

### 02 — HERO

**Layout :** min-height 100dvh, deux colonnes desktop, une colonne mobile.

```
┌──────────────────────────────────────────────────────────┐
│  [Fond : --lp-gradient-hero  bleu nuit → bleu profond]   │
│                                                          │
│  COLONNE GAUCHE (55%)          COLONNE DROITE (45%)      │
│                                                          │
│  [✨ Badge — Nouveau]          [Mockup smartphone        │
│                                 avec halo --lp-shadow-   │
│  L'Église du Sénégal           glow, animation float]   │
│  dans votre poche.                                       │
│  (Playfair Bold, display)                                │
│                                                          │
│  Priez chaque jour, restez                               │
│  connecté à votre paroisse,                              │
│  accédez à la Bible et à la                              │
│  Liturgie en quelques secondes.                          │
│  (Inter Regular, body-lg, neutral-200)                   │
│                                                          │
│  [📱 Télécharger l'app]  [Découvrir ↓]                  │
│                                                          │
│  ★★★★★  4.8 · 2 400+ fidèles · 50+ paroisses            │
└──────────────────────────────────────────────────────────┘
```

- Titre : Playfair Display Bold, `--lp-text-display`, blanc
- Sous-titre : Inter Regular, `--lp-text-body-lg`, `--lp-neutral-200`
- CTA principal : `--lp-gradient-cta` + `--lp-shadow-glow`, texte `--lp-neutral-900`
- CTA secondaire : texte blanc, underline animé au hover
- Mockup : PNG transparent, halo `--lp-primary-glow`, `float-y` 6s ease-in-out infinite
- Particules : points lumineux CSS subtils en arrière-plan

---

### 03 — SOCIAL PROOF

Bande horizontale, fond blanc, 4 compteurs animés au scroll :

```
┌───────────┬───────────┬───────────┬───────────┐
│  2 400+   │   50+     │    7      │  99.9 %   │
│  Fidèles  │ Paroisses │ Diocèses  │  Uptime   │
└───────────┴───────────┴───────────┴───────────┘
```

- Chiffres : Playfair Display Bold, `--lp-text-h1`, `--lp-primary-darker`
- Labels : Inter Medium, `--lp-text-caption`, `--lp-neutral-600`
- Animation : count-up déclenché à l'entrée viewport (IntersectionObserver)

---

### 04 — FEATURES A — Spiritualité

**Titre :** « Nourrissez votre foi chaque jour »
**Layout :** grille 2×2 de feature cards, fond `--lp-primary-surface`

```
┌──────────────────────────┬──────────────────────────┐
│  📖  Bible               │  🕊️  Liturgie du jour    │
│  Naviguez dans les 73    │  Laudes, Messe, Vêpres,  │
│  livres, lisez le texte  │  Complies — tous les     │
│  du jour, cherchez un    │  offices en un seul      │
│  verset.                 │  endroit.                │
├──────────────────────────┼──────────────────────────┤
│  📿  Rosaire             │  📺  TV Catholique       │
│  Priez le Rosaire du     │  Suivez les messes en    │
│  jour avec mystères et   │  direct et les replays   │
│  prières guidées.        │  des émissions.          │
└──────────────────────────┴──────────────────────────┘
```

**Style des cards :**
- Fond blanc + bordure `--lp-primary-light` 1px + `--lp-shadow-sm`
- Hover : fond `--lp-gradient-card` + `--lp-shadow-md` + `translateY(-4px)` 250ms
- Icône : 40px dans cercle `--lp-primary-surface`, couleur `--lp-primary-darker`
- Titre : Inter SemiBold, `--lp-text-h4`, `--lp-neutral-900`
- Corps : Inter Regular, `--lp-text-body`, `--lp-neutral-600`
- Radius : `--lp-radius-lg`

---

### 05 — FEATURES B — Actualités & Messagerie

**Layout :** deux blocs alternés image + texte

**Bloc A — Actualités paroissiales** (texte à droite)
```
[Screenshot feed actualités]     VOTRE PAROISSE,
                                 EN TEMPS RÉEL.

                                 Actualités globales, diocésaines
                                 et paroissiales — tout en un.

                                 ✓  Catégories par thème
                                 ✓  Portées global / paroisse / diocèse
                                 ✓  Partage en un tap
```

**Bloc B — Messagerie confidentielle** (texte à gauche)
```
   PARLEZ À VOTRE          [Screenshot interface
   PRÊTRE EN PRIVÉ.         de chat, bulles bleues
                             et blanches, épuré]
   Échanges sécurisés et
   confidentiels avec les
   prêtres de votre
   communauté.

   ✓  Messages chiffrés de bout en bout
   ✓  Purge automatique (180 jours)
   ✓  Réactions & export
```

- Sections alternées : `--lp-primary-surface` → blanc
- Screenshots : radius `--lp-radius-xl`, `--lp-shadow-lg`
- Checklist : icône check `--lp-primary`, Inter Medium

---

### 06 — FEATURES C — Demandes de Documents

**Layout :** fond `--lp-gradient-hero` (sombre), texte blanc

**Titre :** « Vos certificats sacramentels, sans file d'attente »

```
[Timeline horizontale animée au scroll]

  📋 Déposez       🔍 Suivez        ✅ Récupérez
  votre demande    chaque étape     votre document
  en ligne         en temps réel    à la paroisse
      │                 │                │
   ÉTAPE 1          ÉTAPE 2          ÉTAPE 3
```

Badges documents (chips `--lp-primary-surface` + texte `--lp-primary-darker`) :
`Baptême` · `1ère Communion` · `Confirmation` · `Mariage` · `Parrain/Marraine`

---

### 07 — POUR QUI ?

**Layout :** 3 colonnes — cards audiencées, fond blanc

```
┌───────────────────┬───────────────────┬───────────────────┐
│  👤 FIDÈLES       │  ⛪ PAROISSES     │  🏛️ DIOCÈSES     │
│                   │                   │                   │
│  Priez, lisez,    │  Publiez vos      │  Fédérez vos      │
│  restez connecté  │  actualités,      │  communautés,     │
│  à votre          │  traitez les      │  pilotez en       │
│  communauté       │  demandes de      │  temps réel       │
│  paroissiale.     │  documents.       │  l'activité.      │
│                   │                   │                   │
│  [Je m'inscris →] │  [Ma paroisse →]  │  [Mon diocèse →]  │
└───────────────────┴───────────────────┴───────────────────┘
```

- Card active (hover) : bordure `--lp-primary` 2px + fond `--lp-primary-surface`
- Icône : 48px SVG personnalisé
- CTA par carte : bouton ghost `--lp-primary`

---

### 08 — MOCKUP SHOWCASE

**Layout :** fond `--lp-primary-surface`, présentation multi-écrans flottants

```
          [mockup tablette — accueil app]
     [mobile — liturgie]   [mobile — chat]
               [mobile — mes documents]
```

- Float `ease-in-out 6s infinite`, décalé entre les écrans (stagger)
- Halo `--lp-shadow-glow` sous chaque phone
- Entrée au scroll : staggered `translateY` + opacity via `--lp-ease-spring`

---

### 09 — TÉMOIGNAGES

**Layout :** carrousel auto-play, 3 slides desktop / 1 mobile

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  " Jàngu Bi a changé ma façon de vivre ma foi.           │
│    La liturgie du jour est ma première lecture           │
│    chaque matin. "                                       │
│                                                          │
│  [Avatar]  Marie-Claire Diop                            │
│            Fidèle · Paroisse Saint-Joseph, Dakar         │
│            ★ ★ ★ ★ ★                                    │
└──────────────────────────────────────────────────────────┘
```

- Fond card : blanc, radius `--lp-radius-lg`, `--lp-shadow-md`
- Citation : Playfair Display Italic, `--lp-text-h4`, `--lp-neutral-800`
- Guillemets décoratifs : grand, couleur `--lp-primary-light`
- Étoiles : `--lp-gold`
- Navigation dots : `--lp-primary`

---

### 10 — CTA FINAL

**Layout :** pleine largeur, fond `--lp-gradient-hero`, centré

```
┌──────────────────────────────────────────────────────────┐
│  [Fond bleu nuit avec texture croix subtile en overlay]  │
│                                                          │
│         Rejoignez la communauté Jàngu Bi.                │
│                                                          │
│    Disponible pour les fidèles, les paroisses            │
│         et les diocèses du Sénégal.                      │
│                                                          │
│     [📱 Télécharger l'app]   [🌐 Version web]            │
│                                                          │
│         Gratuit · Sans publicité · Sécurisé              │
└──────────────────────────────────────────────────────────┘
```

- Titre : Playfair Display Bold, `--lp-text-h1`, blanc
- Sous-titre : Inter Regular, `--lp-text-body-lg`, `--lp-neutral-200`
- CTA principal : `--lp-gradient-cta` + `--lp-shadow-glow`, texte `--lp-neutral-900`
- CTA secondaire : outlined blanc
- Badges rassurants : `--lp-primary-light`, `--lp-text-caption`

---

### 11 — FOOTER

```
┌─────────────────────────────────────────────────────────┐
│  [Logo Jàngu Bi]                                        │
│  L'Église du Sénégal dans votre poche.                  │
│                                                         │
│  Fonctionnalités   Paroisses    Légal                   │
│  Bible             Annuaire     CGU                     │
│  Rosaire           Rejoindre    Confidentialité         │
│  Liturgie          Contact      Mentions légales        │
│  Actualités                                             │
│  Messagerie                                             │
│                                                         │
│  ──────────────────────────────────────────────         │
│  © 2026 Jàngu Bi · Fait avec ❤️ pour l'Église           │
│  catholique du Sénégal                                  │
└─────────────────────────────────────────────────────────┘
```

- Fond : `--lp-neutral-900`
- Liens : `--lp-neutral-400`, hover `--lp-primary`
- Copyright : `--lp-neutral-600`, `--lp-text-caption`

---

## 6. Responsive

| Breakpoint | Comportement |
|------------|-------------|
| Mobile < 768px | Hero 1 colonne, mockup sous le texte · Features 1 colonne · "Pour qui" en tabs · Carrousel 1 slide swipeable |
| Tablet 768–1023px | Hero 2 colonnes compactes · Features 2 colonnes · Carrousel 2 slides |
| Desktop ≥ 1024px | Toutes sections pleine largeur, max 1200px centré · Mockup showcase 3D proéminent · Parallax hero |

---

## 7. Animations & Interactions

| Élément | Animation |
|---------|-----------|
| Hero headline | Fade-in + `translateY(24px→0)` au load, stagger par ligne |
| Mockup hero | `float-y` CSS 6s + parallax léger au scroll |
| Compteurs stats | Count-up déclenché à l'entrée viewport |
| Feature cards | Fade-in + `translateY` en cascade (stagger 100ms) |
| Timeline documents | Ligne de progression qui se dessine au scroll |
| Mockup showcase | Entrée en cascade `--lp-ease-spring` |
| CTA buttons | `scale(1.04)` + `--lp-shadow-glow` intensifié au hover |
| Navbar | Glassmorphism progressif au scroll |

`prefers-reduced-motion` : toutes animations à 0ms, pas de float.

---

## 8. Performance & SEO

| Métrique | Cible |
|----------|-------|
| LCP | < 2.0s |
| INP | < 200ms |
| CLS | < 0.05 |
| Lighthouse | ≥ 95 |

- Hero image : `fetchpriority="high"`, format AVIF/WebP
- Fonts : `font-display: swap`, preconnect Google Fonts
- JS : minimal — Astro SSG ou HTML/CSS/JS vanilla
- `<title>` : "Jàngu Bi — L'application catholique du Sénégal"
- `<meta description>` : "Bible, Liturgie, Actualités paroissiales et messagerie avec les prêtres. L'Église catholique du Sénégal réunie dans une seule application."
- OG image : 1200×630px (hero mockup + logo)
- Schema.org : `SoftwareApplication` + `Organization`

---

## 9. Stack Technique Recommandée

| Couche | Choix | Raison |
|--------|-------|--------|
| Framework | **Astro 5** (SSG) | HTML statique pur, 0 JS par défaut, Lighthouse 100 |
| Styles | **Tailwind CSS v4** + variables CSS tokens | Tokens mappés, purge auto |
| Animations scroll | **GSAP ScrollTrigger** ou CSS natif | Légère, performante |
| Illustrations | **Lottie** | Animations vectorielles (timeline documents) |
| Hébergement | **Cloudflare Pages** | CDN mondial, git push, gratuit |

---

## 10. Assets à Préparer

### Illustrations & Iconographie
- [ ] Logo Jàngu Bi — SVG + PNG 512px + favicon 32px
- [ ] Croix catholique stylisée SVG (usage logo + footer)
- [ ] Icônes SVG métier : Bible, Rosaire, Liturgie, TV, Messagerie, Document
- [ ] Illustration / photo hero (fidèles sénégalais, lumière naturelle)
- [ ] Mockup smartphone frame PNG transparent (pour y insérer screenshots)
- [ ] Texture subtile croix (section CTA final, très basse opacité)

### Screenshots de l'app (à faire une fois l'app disponible)
- [ ] Écran Accueil
- [ ] Écran Bible — chapitre ouvert
- [ ] Écran Liturgie — offices du jour
- [ ] Écran Chat — conversation avec prêtre
- [ ] Écran Mes Documents — liste avec badges statuts

### Médias
- [ ] OG image 1200×630px
- [ ] Vidéo ou GIF de démo (optionnel — section showcase)

---

## 11. Contenu à Valider avec le Client

| Point | Question |
|-------|----------|
| Tagline | Laquelle retenir ? Propositions en §1 |
| Chiffres stats | Réels ou estimés pour la maquette ? |
| Témoignages | Citations réelles ou placeholders ? |
| CTA téléchargement | App Store / Play Store disponibles ? (V2) |
| Langue | Français uniquement ou sections en wolof ? |
| Tarifs | Section tarifaire pour les paroisses/diocèses ? |
| CGU & Confidentialité | Textes à rédiger avant mise en ligne |

---

## 12. Checklist Maquette Landing

### Figma
- [ ] Bibliothèque tokens landing (séparée du design app)
- [ ] Composants : NavBar · HeroSection · FeatureCard · StatCounter · TestimonialCard · CTABanner · Footer
- [ ] Thème clair (principal) — thème sombre non requis pour la landing
- [ ] Auto-layout responsive sur tous les composants

### Prototypes
- [ ] Scrollable desktop 1440px — 11 sections
- [ ] Scrollable mobile 375px — version adaptée
- [ ] États hover sur CTA et feature cards
- [ ] Animation navbar au scroll (annotée)

### Contenu
- [ ] Tous les textes en français finalisés
- [ ] Images / illustrations placées (ou placeholders)
- [ ] États vides non requis (page statique)
- [ ] Mentions légales en footer
