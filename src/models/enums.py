"""
PITCHPULSE 2026 - Strict Domain Enumerations
Criterion #1: Code Quality (Replaces plain string literals with type-safe enums)
"""

from enum import Enum


class PriorityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentCategory(str, Enum):
    CONGESTION = "congestion"
    MEDICAL = "medical"
    ACCESSIBILITY_ASSIST = "accessibility_assist"
    FACILITY = "facility"


class MobilityProfile(str, Enum):
    WHEELCHAIR = "wheelchair"
    LOW_MOBILITY = "low_mobility"
    SENSORY_SENSITIVE = "sensory_sensitive"
    STANDARD = "standard"


class UserRole(str, Enum):
    FAN = "fan"
    VOLUNTEER = "volunteer"
    VENUE_STAFF = "venue_staff"
    INCIDENT_COMMANDER = "incident_commander"


class LanguageCode(str, Enum):
    AUTO = "auto"
    EN = "en"
    ES = "es"
    FR = "fr"
    PT = "pt"
    AR = "ar"


class GateStatusLevel(str, Enum):
    NORMAL = "normal"
    MODERATE = "moderate"
    SURGE = "surge"


class ActionCategory(str, Enum):
    NAVIGATION = "navigation"
    ACCESSIBILITY = "accessibility"
    TRANSIT = "transit"
    SAFETY = "safety"
    SUSTAINABILITY = "sustainability"
    INFO = "info"
