"""Storage-provider configuration for the gradual repository cutover.

Phase 0 intentionally does not connect these flags to the live domain models.
Every domain remains Firestore-backed until a later, separately reviewed phase.
"""

from repositories.config import RepositoryBackend, repository_backends
from repositories.interfaces import (
    AccountRepository, ApiAccessRepository, CallRepository,
    LanguageMetricsRepository, OrganizationRepository, ParticipantRepository,
    ReviewRepository, TaxonomyRepository, TranscriptRepository,
    TranslatorRepository,
)

__all__ = [
    "AccountRepository", "ApiAccessRepository", "CallRepository",
    "LanguageMetricsRepository", "OrganizationRepository",
    "ParticipantRepository", "RepositoryBackend", "ReviewRepository",
    "TaxonomyRepository", "TranscriptRepository", "TranslatorRepository",
    "repository_backends",
]

__all__ = ["RepositoryBackend", "repository_backends"]
