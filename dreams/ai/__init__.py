"""Intégration des services d'intelligence artificielle (transcription, émotion, image).

Chaque service expose une fonction simple qui :

- appelle l'API avec un délai maximal (timeout) et des nouvelles tentatives
  automatiques sur les erreurs temporaires ;
- journalise l'appel (durée, succès, coût estimé) dans le modèle ``ApiCall`` ;
- traduit toute erreur technique en ``AIServiceError``, dont le message est
  compréhensible par l'utilisateur.
"""
