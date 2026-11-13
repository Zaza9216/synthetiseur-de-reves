"""Format de logs JSON pour la production.

Une ligne JSON par événement : les plateformes d'hébergement et les outils de
supervision peuvent alors filtrer par niveau, module ou champ, au lieu de
chercher dans du texte libre.
"""

import json
import logging
from datetime import UTC, datetime

# Attributs standard d'un LogRecord, à ne pas recopier comme champs « extra ».
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Formate chaque enregistrement de log en un objet JSON sur une ligne."""

    def format(self, record: logging.LogRecord) -> str:
        """Construit la ligne JSON : horodatage, niveau, module, message, extras.

        Args:
            record: L'enregistrement de log.

        Returns:
            L'enregistrement sérialisé en JSON.
        """
        payload: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(
            {key: value for key, value in vars(record).items() if key not in _STANDARD_ATTRS}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)
