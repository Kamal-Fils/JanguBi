"""Cohérence « type de document ↔ motif de la demande ».

Certaines combinaisons n'ont aucun sens pastoral : on ne demande pas une
attestation de mariage religieux *pour être parrain ou marraine*. Cette table est
la **source unique** de la règle — le backend la fait respecter à la création
(services) et l'expose telle quelle au frontend (endpoint « options »), pour que
le formulaire ne redéclare jamais sa propre copie.

RÈGLE MÉTIER ECCLÉSIALE — à faire valider par l'autorité pastorale.
Justification de chaque ligne :

* **Baptême** — pièce maîtresse du registre : exigé au dossier de mariage, pour
  être parrain/marraine (can. 874), et à l'inscription au catéchisme.
* **Première communion** — n'est requise ni pour le mariage ni pour le
  parrainage : reste le catéchisme, le dossier paroissial et l'usage personnel.
* **Confirmation** — requise pour être parrain/marraine (can. 874 §1 3°) et
  versée au dossier de mariage.
* **Mariage religieux** — atteste un sacrement déjà célébré : ne peut pas servir
  de pièce à un futur mariage ni à un parrainage.
* **Parrain / marraine** — même logique : atteste une fonction déjà exercée.
* **Autre document** — catégorie ouverte : tous les motifs restent proposés.

« Autre » (motif) reste disponible partout : c'est l'échappatoire qui évite de
bloquer un cas non prévu, la précision étant alors saisie dans `reason_free`.
"""

from apps.documents.models import DocumentRequest

_TYPE = DocumentRequest.DocumentType
_REASON = DocumentRequest.RequestReason

# Motifs toujours recevables, quel que soit le document demandé.
_UNIVERSAL_REASONS: tuple[str, ...] = (
    _REASON.PARISH_FILE,
    _REASON.PERSONAL,
    _REASON.OTHER,
)

ALL_REASONS: tuple[str, ...] = tuple(_REASON.values)

REASONS_BY_DOCUMENT_TYPE: dict[str, tuple[str, ...]] = {
    _TYPE.BAPTISM: (
        _REASON.RELIGIOUS_MARRIAGE,
        _REASON.GODPARENT,
        _REASON.CATECHISM,
        *_UNIVERSAL_REASONS,
    ),
    _TYPE.FIRST_COMMUNION: (
        _REASON.CATECHISM,
        *_UNIVERSAL_REASONS,
    ),
    _TYPE.CONFIRMATION: (
        _REASON.RELIGIOUS_MARRIAGE,
        _REASON.GODPARENT,
        *_UNIVERSAL_REASONS,
    ),
    _TYPE.RELIGIOUS_MARRIAGE: _UNIVERSAL_REASONS,
    _TYPE.GODPARENT: _UNIVERSAL_REASONS,
    _TYPE.OTHER: ALL_REASONS,
}


def allowed_reasons_for(document_type: str) -> tuple[str, ...]:
    """Motifs recevables pour ce type de document.

    Un type inconnu (front désynchronisé, donnée legacy) ne restreint rien : la
    validation du champ `document_type` lui-même relève du serializer, et il ne
    faut pas transformer une erreur d'énumération en un rejet de motif trompeur.
    """
    return REASONS_BY_DOCUMENT_TYPE.get(document_type, ALL_REASONS)


def is_reason_allowed(*, document_type: str, reason: str) -> bool:
    return reason in allowed_reasons_for(document_type)
