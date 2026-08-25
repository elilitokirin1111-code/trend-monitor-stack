"""Knowledge-base integration contracts."""

from .service import (
    AnnotationRequiredError,
    KnowledgeConfigurationError,
    KnowledgeSyncService,
)
from .weknora import WeKnoraClient, WeKnoraConfig, WeKnoraError

__all__ = [
    "AnnotationRequiredError",
    "KnowledgeConfigurationError",
    "KnowledgeSyncService",
    "WeKnoraClient",
    "WeKnoraConfig",
    "WeKnoraError",
]
