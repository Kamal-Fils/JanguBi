from typing import List, Optional, TypedDict

from django.db import models


class IntentType(models.TextChoices):
    BIBLE = "BIBLE", "Bible Search"
    ROSARY = "ROSARY", "Rosary Information"
    AVAILABILITY = "AVAILABILITY", "Priest/Sister Availability"
    MIXED = "MIXED", "Mixed Domains"
    UNKNOWN = "UNKNOWN", "Unknown Intent"

# On utilise TypedDict (stdlib) pour des schémas légers, sans dépendance extra.


class EntitiesSchema(TypedDict):
    topic: Optional[str]
    date: Optional[str]  # YYYY-MM-DD
    time_after: Optional[str] # HH:MM
    city: Optional[str]
    service: Optional[str]

class ExtractedIntentSchema(TypedDict):
    intent: str # BIBLE, ROSARY, AVAILABILITY, MIXED, UNKNOWN
    domains: List[str] # list of strings
    entities: EntitiesSchema

# This represents the JSON schema we will push to Gemini for structured output
GEMINI_INTENT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["BIBLE", "ROSARY", "AVAILABILITY", "MIXED", "UNKNOWN"],
            "description": "The primary intent of the user."
        },
        "domains": {
            "type": "array",
            "items": {"type": "string", "enum": ["BIBLE", "ROSARY", "AVAILABILITY"]},
            "description": "All domains the query touches."
        },
        "entities": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "nullable": True, "description": "Subject, keyword, or summary of the request (e.g. 'miséricorde', 'joie')."},
                "date": {"type": "string", "nullable": True, "description": "Specific date requested in YYYY-MM-DD format, or relative converted to YYYY-MM-DD."},
                "time_after": {"type": "string", "nullable": True, "description": "Time requested in HH:MM format."},
                "city": {"type": "string", "nullable": True, "description": "City or parish location."},
                "service": {"type": "string", "nullable": True, "description": "Type of service requested (e.g., 'confession', 'messe')."}
            },
            "required": ["topic", "date", "time_after", "city", "service"]
        }
    },
    "required": ["intent", "domains", "entities"]
}
