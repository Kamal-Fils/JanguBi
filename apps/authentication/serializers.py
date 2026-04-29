from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Sérialiseur JWT custom :
    - Injecte `jwt_key` dans le payload → permet la révocation globale
    - Injecte `role` → le frontend n'a pas besoin d'un appel /me/ supplémentaire
    - Vérifie is_active et is_verified avant d'émettre le token
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Claims custom dans le payload JWT
        token["jwt_key"] = str(user.jwt_key)
        token["role"] = user.role
        token["email"] = user.email
        return token

    def validate(self, attrs):
        # Appel parent → vérifie email/password, retourne access + refresh
        data = super().validate(attrs)

        # Vérifications métier post-authentification
        if not self.user.is_active:
            raise AuthenticationFailed(
                "Votre compte est désactivé. Contactez le support.",
                code="account_disabled",
            )
        if not self.user.is_verified:
            raise AuthenticationFailed(
                "Veuillez vérifier votre email avant de vous connecter.",
                code="email_not_verified",
            )

        # Enrichit la réponse avec les données utilisateur
        data["user"] = {
            "id": self.user.id,
            "email": self.user.email,
            "role": self.user.role,
            "is_admin": self.user.is_admin,
        }

        return data
