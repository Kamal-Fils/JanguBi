from rest_framework import serializers

class RagQuerySerializer(serializers.Serializer):
    query = serializers.CharField(
        required=True,
        help_text="The question or prompt to ask the assistant (e.g., 'Quel mystère aujourd'hui et as-tu un prêtre dispo à Mbour ?')"
    )

class RagResponseSerializer(serializers.Serializer):
    # allow_blank : sur les branches "aucun contexte"/"erreur", context="" est
    # légitime (sinon le endpoint renvoyait un 400 — bug latent).
    answer = serializers.CharField(allow_blank=True, help_text="La réponse (extractive par défaut, ou générée si activé).")
    context = serializers.CharField(allow_blank=True, help_text="Le contexte brut récupéré en base (peut être vide).")
    intent = serializers.DictField(help_text="Métadonnée de routage (intent/domains/entities).")
