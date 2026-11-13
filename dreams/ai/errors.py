"""Erreurs des services d'IA et traduction des erreurs de l'API OpenAI."""

import logging

import openai

logger = logging.getLogger(__name__)


class AIServiceError(Exception):
    """Échec d'un service d'IA, avec un message destiné à l'utilisateur.

    Attributes:
        user_message: Message clair, sans détail technique, affiché à l'utilisateur.
        retryable: ``True`` si une nouvelle tentative plus tard a des chances de réussir.
    """

    def __init__(self, user_message: str, *, retryable: bool = True) -> None:
        """Initialise l'erreur.

        Args:
            user_message: Message affiché à l'utilisateur.
            retryable: Indique si l'utilisateur peut relancer le traitement.
        """
        super().__init__(user_message)
        self.user_message = user_message
        self.retryable = retryable


def translate_openai_error(error: Exception) -> AIServiceError:
    """Convertit une exception du SDK OpenAI en ``AIServiceError``.

    Le SDK a déjà effectué ses nouvelles tentatives automatiques (avec délai
    croissant) sur les erreurs temporaires avant de lever l'exception.

    Args:
        error: L'exception levée par le SDK OpenAI.

    Returns:
        L'erreur métier correspondante, prête à être affichée.
    """
    if isinstance(error, openai.APITimeoutError):
        return AIServiceError("Le service d'IA a mis trop de temps à répondre. Réessayez.")
    if isinstance(error, openai.APIConnectionError):
        return AIServiceError("Le service d'IA est injoignable pour le moment. Réessayez.")
    if isinstance(error, openai.RateLimitError):
        if getattr(error, "code", None) == "insufficient_quota":
            logger.critical("Crédit OpenAI épuisé : recharger le compte ou ajuster le budget.")
            return AIServiceError(
                "Le service d'IA a atteint sa limite d'utilisation. Réessayez plus tard.",
                retryable=False,
            )
        return AIServiceError("Le service d'IA est très sollicité. Réessayez dans une minute.")
    if isinstance(error, openai.AuthenticationError | openai.PermissionDeniedError):
        logger.critical("Clé OpenAI refusée : vérifier OPENAI_API_KEY.")
        return AIServiceError("Le service d'IA est mal configuré.", retryable=False)
    if isinstance(error, openai.BadRequestError):
        return AIServiceError("Le service d'IA n'a pas pu traiter ce contenu.", retryable=False)
    if isinstance(error, openai.InternalServerError):
        return AIServiceError("Le service d'IA rencontre un incident. Réessayez plus tard.")
    return AIServiceError("Une erreur inattendue est survenue avec le service d'IA.")
