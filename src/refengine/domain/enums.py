from enum import StrEnum


class ExtractionMethod(StrEnum):
    """Supported page text extraction methods."""

    NATIVE = "native"
    OCR = "ocr"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"


class ProcessingStatus(StrEnum):
    """Document-level processing outcomes."""

    PROCESSED = "processed"
    PROCESSED_WITH_WARNINGS = "processed_with_warnings"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"


class ErrorCode(StrEnum):
    """Stable blocking error codes used by reports and integrations."""

    TITLE_NOT_FOUND = "TITLE_NOT_FOUND"
    AUTHORS_AMBIGUOUS = "AUTHORS_AMBIGUOUS"
    AUTHORS_NOT_VISIBLE_IN_SOURCE = "AUTHORS_NOT_VISIBLE_IN_SOURCE"
    JOURNAL_NOT_FOUND = "JOURNAL_NOT_FOUND"
    YEAR_AMBIGUOUS = "YEAR_AMBIGUOUS"
    DOI_INVALID = "DOI_INVALID"
    UNSUPPORTED_LAYOUT = "UNSUPPORTED_LAYOUT"
    UNSUPPORTED_DOCUMENT_TYPE = "UNSUPPORTED_DOCUMENT_TYPE"
    SOURCE_PROCESSING_FAILED = "SOURCE_PROCESSING_FAILED"
    STRUCTURED_METADATA_CONFLICT = "STRUCTURED_METADATA_CONFLICT"
    CORRECTION_SUGGESTION_AVAILABLE = "CORRECTION_SUGGESTION_AVAILABLE"


class WarningCode(StrEnum):
    """Non-blocking conditions that still require explicit visibility."""

    OCR_NOT_AVAILABLE = "OCR_NOT_AVAILABLE"
    OCR_LANGUAGE_MISSING = "OCR_LANGUAGE_MISSING"
    OCR_LOW_CONFIDENCE = "OCR_LOW_CONFIDENCE"
    PAGE_TEXT_UNAVAILABLE = "PAGE_TEXT_UNAVAILABLE"
    PLACE_NOT_IDENTIFIED = "PLACE_NOT_IDENTIFIED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    INFERRED_METADATA = "INFERRED_METADATA"
    METADATA_PAGES_ONLY = "METADATA_PAGES_ONLY"
    DUPLICATE_VARIANT = "DUPLICATE_VARIANT"
    SOURCE_FIELD_NOT_VISIBLE = "SOURCE_FIELD_NOT_VISIBLE"
    BIBTEX_METADATA_APPLIED = "BIBTEX_METADATA_APPLIED"
    BIBTEX_CONFLICT_REVIEW = "BIBTEX_CONFLICT_REVIEW"
    RIS_METADATA_APPLIED = "RIS_METADATA_APPLIED"
    RIS_CONFLICT_REVIEW = "RIS_CONFLICT_REVIEW"
    REVIEW_MEMORY_APPLIED = "REVIEW_MEMORY_APPLIED"
    CORRECTION_SUGGESTION_AVAILABLE = "CORRECTION_SUGGESTION_AVAILABLE"


class DocumentType(StrEnum):
    """Reference families supported by the local review workflow."""

    JOURNAL_ARTICLE = "journal_article"
    THESIS = "thesis"
    DISSERTATION = "dissertation"
    BOOK_MANUAL = "book_manual"
    WEB_ARTICLE = "web_article"
    UNKNOWN = "unknown"


class VariantType(StrEnum):
    """Physical representations of a bibliographic work."""

    PUBLISHER_ORIGINAL = "publisher_original"
    BROWSER_PRINT = "browser_print"
    INSTITUTIONAL_REPOSITORY = "institutional_repository"
    SCANNED = "scanned"
    BIBTEX = "bibtex"
    RIS = "ris"
    UNKNOWN = "unknown"


class ReviewState(StrEnum):
    """Human review lifecycle used by the local API workflow."""

    PENDING = "pending"
    APPROVED = "approved"
    CORRECTED = "corrected"
    EXCLUDED = "excluded"


class ReferenceReadiness(StrEnum):
    """Whether a generated reference is safe to present as final."""

    READY = "ready"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class QualityIssueCode(StrEnum):
    """Stable reasons emitted by the reference quality gate."""

    SECONDARY_VARIANT = "SECONDARY_VARIANT"
    REFERENCE_NOT_GENERATED = "REFERENCE_NOT_GENERATED"
    EXTRACTION_BLOCKED = "EXTRACTION_BLOCKED"
    OCR_ONLY_SOURCE = "OCR_ONLY_SOURCE"
    HEURISTIC_AUTHOR_EXTRACTION = "HEURISTIC_AUTHOR_EXTRACTION"
    LOW_TITLE_CONFIDENCE = "LOW_TITLE_CONFIDENCE"
    LOW_AUTHOR_CONFIDENCE = "LOW_AUTHOR_CONFIDENCE"
    LOW_CONFIDENCE_OCR_EVIDENCE = "LOW_CONFIDENCE_OCR_EVIDENCE"
    UNSUPPORTED_DOCUMENT_TYPE = "UNSUPPORTED_DOCUMENT_TYPE"
    STRUCTURED_METADATA_CONFLICT = "STRUCTURED_METADATA_CONFLICT"
    CORRECTION_SUGGESTION_AVAILABLE = "CORRECTION_SUGGESTION_AVAILABLE"
    REFERENCE_SCHEMA_NOT_IDENTIFIED = "REFERENCE_SCHEMA_NOT_IDENTIFIED"
    REFERENCE_SCHEMA_NOT_IMPLEMENTED = "REFERENCE_SCHEMA_NOT_IMPLEMENTED"
    REQUIRED_REFERENCE_FIELD_MISSING = "REQUIRED_REFERENCE_FIELD_MISSING"
    REFERENCE_FIELD_CONFLICT = "REFERENCE_FIELD_CONFLICT"


class ApiRunStatus(StrEnum):
    """Lifecycle of one local input-folder processing run."""

    QUEUED = "queued"
    PROCESSING = "processing"
    REVIEW = "review"
    PUBLISHED = "published"
    FAILED = "failed"
