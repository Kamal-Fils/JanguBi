# **Spécification fonctionnelle**

# **Formulaire unique de demande de documents ecclésiaux**

Document de cadrage destiné à l'équipe de développement pour la mise en place d'un formulaire ultra simple, d'un workflow de vérification par la paroisse et d'un dépôt direct des documents validés sur la plateforme.

**Objectif**

Mettre en place un formulaire unique, compréhensible par tout fidèle, permettant de demander un document ecclésial sans exiger la maîtrise des détails administratifs des registres. Après soumission, la paroisse vérifie les informations, retrouve l'acte dans ses registres, valide ou rejette la demande, puis dépose le document sur l'espace personnel du demandeur.

**Documents couverts dans la première version**

- Certificat de baptême

- Attestation de première communion

- Attestation de confirmation

- Attestation de mariage religieux

- Attestation pour être parrain ou marraine

**Parcours utilisateur recommandé**

| Étape | Écran / action | Contenu attendu |
| :---- | :---- | :---- |
| 1 | Choix de la demande | Type de document \+ motif de la demande |
| 2 | Identification du demandeur | Nom, prénoms, date et lieu de naissance, téléphone, email |
|  3 |  Recherche dans les registres | Informations minimales pour retrouver l'acte \+ champs dynamiques selon le document |
| 4 | Validation finale | Pièce jointe éventuelle \+ consentement \+ envoi |

Le parcours doit tenir en 4 écrans maximum sur mobile afin de limiter l'abandon. Les champs inutiles pour la recherche paroissiale ne doivent pas être exposés au fidèle.

**Structure du formulaire \- tronc commun**

| Bloc | Champ | Type | Obligatoire | Remarques |
| :---- | :---- | :---- | :---- | :---- |
|  Document | Type de document demandé | Liste déroulante |  Oui |  Une seule valeur autorisée par demande. |
|  Document |  Motif de la demande | Liste déroulante |  Oui | Valeurs : mariage religieux, parrain / marraine, inscription catéchèse, dossier paroissial, usage personnel, autre. |
|  Document |  Motif libre |  Texte court | Conditionne l |  Visible seulement si la valeur “autre” est choisie. |
| Identité | Nom | Texte court | Oui | Nom actuel du demandeur. |
| Identité | Prénom(s) | Texte court | Oui | Prénoms complets. |
| Identité | Date de naissance | Date | Oui | Format JJ/MM/AAAA. |
| Identité | Lieu de naissance | Texte court | Oui | Ville / commune / pays. |
| Contact | Téléphone | Téléphone | Oui | Utilisé pour notification et suivi. |
| Contact | Email | Email | Oui | Utilisé pour notification et accès au document. |
| Recherche | Nom enregistré possible | Texte court | Non | Nom sous lequel l'acte pourrait apparaître dans le registre. |
|  Recherche | Prénom(s) enregistrés possibles |  Texte court |  Non |  Variante possible des prénoms dans le registre. |
| Recherche | Nom du père | Texte court | Oui | Aide à la recherche en cas d'homonymie. |
| Recherche | Nom de la mère | Texte court | Oui | Idem. |
|  Recherche |  Paroisse concernée | Liste / recherche |  Oui |  Champ prioritaire pour orienter la demande. |
|  Recherche |  Diocèse | Liste déroulante |  Oui |  Peut être prérempli à partir de la paroisse. |
|  Recherche | Date approximative du sacrement |  Date ou année |  Oui |  Doit accepter une date imprécise ou une simple année. |
| Recherche | Lieu du sacrement | Texte court | Oui | Ville / paroisse / chapelle si connu. |
| Complémen t | Informations complémentaires |  Zone de texte |  Non | Permet d'aider la recherche sans complexifier le formulaire. |

| Bloc | Champ | Type | Obligatoire | Remarques |
| :---- | :---- | :---- | :---- | :---- |
|  Pièce jointe |  Justificatif |  Upload |  Non | Pièce d'identité ou ancien document religieux si disponible. |
| Consentem ent | Déclaration de véracité et autorisation de vérification |  Case à cocher |  Oui |  Impossible d'envoyer sans ce consentement. |

**Champs dynamiques selon le document demandé**

| Document | Champs additionnels à afficher | Notes fonctionnelles |
| :---- | :---- | :---- |
|  Certificat de baptême | Date approximative du baptême ; paroisse de baptême ; ville du baptême ; nom du parrain si connu ; nom de la marraine si connue | Le bloc s'affiche dès sélection du document. Les champs parrain / marraine restent facultatifs. |
|  Première communion | Date approximative de la première communion ; paroisse ; lieu ; nom du catéchiste ou responsable si connu | Le nom du catéchiste est facultatif et sert uniquement d'indice de recherche. |
|  Confirmation | Date approximative de la confirmation ; paroisse ou lieu ; diocèse ; nom de l'évêque ou du célébrant si connu | Le diocèse peut être distinct de la paroisse habituelle du fidèle. |
|  Mariage religieux | Nom complet de l'époux ; nom complet de l'épouse ; date approximative ; paroisse du mariage ; lieu ; nom du célébrant si connu |  Ne pas exiger le numéro d'acte. Un seul conjoint peut initier la demande. |
|  Parrain / marraine | Type de célébration concernée : baptême ou confirmation ; nom de l'enfant / du confirmand si connu ; paroisse de la célébration ; date prévue si connue |  Permet à la paroisse d'évaluer l'urgence et l'usage exact du document. |

**Règles UX et validations**

- Le formulaire doit être pleinement utilisable sur mobile.

- Les champs conditionnels ne s'affichent qu'après le choix du type de document.

- La date du sacrement doit accepter une année seule ou une date approximative.

- Les messages d'erreur doivent être simples et orientés action.

- Le bouton d'envoi reste désactivé tant que les champs obligatoires et le consentement ne sont pas fournis.

- Une confirmation visuelle de dépôt doit être affichée immédiatement après soumission.

**Workflow de traitement côté paroisse**

| Statut | Définition | Action principale |
| :---- | :---- | :---- |
|  Soumise |  La demande a été envoyée par le fidèle. | Visible dans la file paroisse avec date, type de document et identité du demandeur. |
|  En vérification | Un agent paroissial a commencé la recherche dans les registres. |  Consultation, annotations internes, tentative de rapprochement. |

| Statut | Définition | Action principale |
| :---- | :---- | :---- |
| Complément demandé | Les informations sont insuffisantes ou ambiguës. |  Notification envoyée au fidèle pour compléter la demande. |
|  Validée | La paroisse a retrouvé l'acte et approuvé l'émission du document. |  Génération ou dépôt manuel du document signé / cacheté. |
| Rejetée | La demande ne peut pas aboutir. | Motif de rejet obligatoire et notification au fidèle. |
|  Document déposé | Le document final a été versé dans l'espace personnel. |  Notification SMS / email \+ historisation du dépôt. |

**Back-office minimum attendu**

- Vue liste avec filtres : statut, type de document, paroisse, date de dépôt, nom du demandeur.

- Fiche détail de la demande avec toutes les données fournies, historique des actions et zone de notes internes.

- Possibilité de téléverser le document final au format PDF.

- Possibilité de demander un complément au fidèle sans recréer la demande.

- Journal d'audit simple : qui a consulté, modifié, validé ou rejeté la demande.

**Données et intégration**

| Objet | Recommandation |
| :---- | :---- |
| Identifiant de demande | Générer un identifiant unique lisible du type DOC-20260408-000123. |
| Pièces jointes | Stockage sécurisé avec lien interne non public. |
|  Document final | PDF déposé dans l'espace personnel du fidèle avec métadonnées : type, paroisse, date de dépôt, statut. |
|  Historique | Conserver les changements de statut, la date, l'utilisateur interne et le commentaire éventuel. |
| Notification | Prévoir email et SMS, avec préférence de canal selon les données disponibles. |
| Sécurité | Restreindre l'accès aux demandes par profil paroisse / diocèse / administration. |

**Résumé exécutable pour l'équipe technique**

- Créer un formulaire unique avec une seule demande par soumission.

- Afficher un tronc commun fixe puis des champs dynamiques selon le document choisi.

- Limiter le parcours à 4 écrans maximum sur mobile.

- Mettre en place un back-office paroisse avec statuts, pièces jointes, notes internes et dépôt du PDF final.

- Notifier automatiquement le fidèle à chaque étape utile, en particulier au dépôt du document.