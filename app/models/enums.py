from enum import Enum


class AnomalyType(str, Enum):
    PRICE_CREEP = "PRICE_CREEP"
    DUPLICATE = "DUPLICATE"
    ABNORMAL_TOTAL = "ABNORMAL_TOTAL"


class AnomalySeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AnomalyStatus(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    VALID = "VALID"
    ISSUE = "ISSUE"
