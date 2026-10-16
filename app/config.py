from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from app.personas import UNDERWRITING_FIELD_SCHEMA, get_field_schema, get_persona_config

try:
    # Load .env if python-dotenv is installed; fail silently otherwise.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

# Re-export for backward compatibility
__all__ = ["UNDERWRITING_FIELD_SCHEMA", "get_field_schema", "get_persona_config"]

# --- Database & RAG Settings ---


@dataclass
class DatabaseSettings:
    backend: str = "json"  # 'json' or 'postgresql'
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    ssl_mode: Optional[str] = None
    schema: Optional[str] = None


@dataclass
class RAGSettings:
    enabled: bool = False
    top_k: int = 5
    similarity_threshold: float = 0.5
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_deployment: Optional[str] = None  # Azure OpenAI deployment for embeddings


@dataclass
class AutomotiveClaimsSettings:
    """Settings for Automotive Claims multimodal processing."""

    enabled: bool = True
    doc_analyzer: str = "autoClaimsDocAnalyzer"
    image_analyzer: str = "autoClaimsImageAnalyzer"
    video_analyzer: str = "autoClaimsVideoAnalyzer"
    policies_path: str = "prompts/automotive-claims-policies.json"
    video_max_duration_minutes: int = 10
    image_max_size_mb: int = 20

    @classmethod
    def from_env(cls) -> "AutomotiveClaimsSettings":
        """Load automotive claims settings from environment variables."""
        return cls(
            enabled=os.getenv("AUTO_CLAIMS_ENABLED", "true").lower() == "true",
            doc_analyzer=os.getenv("AUTO_CLAIMS_DOC_ANALYZER", "autoClaimsDocAnalyzer"),
            image_analyzer=os.getenv("AUTO_CLAIMS_IMAGE_ANALYZER", "autoClaimsImageAnalyzer"),
            video_analyzer=os.getenv("AUTO_CLAIMS_VIDEO_ANALYZER", "autoClaimsVideoAnalyzer"),
            policies_path=os.getenv(
                "AUTO_CLAIMS_POLICIES_PATH", "prompts/automotive-claims-policies.json"
            ),
            video_max_duration_minutes=int(os.getenv("VIDEO_MAX_DURATION_MINUTES", "10")),
            image_max_size_mb=int(os.getenv("IMAGE_MAX_SIZE_MB", "20")),
        )


@dataclass
class MortgageUnderwritingSettings:
    """Settings for Mortgage Underwriting (HCSF / internal bank rules)."""

    enabled: bool = True
    doc_analyzer: str = "mortgageDocAnalyzer"
    policies_path: str = "prompts/mortgage-underwriting-policies.json"
    # Sensibilité taux : +1 pt (pratique de place française)
    taux_sensibilite_buffer_pct: float = 1.0
    # Plancher taux historique (conservé pour rétro-compatibilité, pas de norme FR)
    osfi_mqr_floor_pct: float = 5.25
    osfi_mqr_buffer_pct: float = 1.0
    # Limites HCSF : taux d'effort et endettement plafonnés à 35%
    gds_limit_standard: float = 0.35
    tds_limit_standard: float = 0.35
    # Limites LTV (règles internes de la banque)
    ltv_limit_conventional: float = 0.90  # 90% standard
    ltv_limit_insured: float = 1.00  # 100% rare (primo-accédant)
    # Durée HCSF : 25 ans, 27 ans pour VEFA
    max_amortization_insured: int = 25
    max_amortization_uninsured: int = 25
    # Apport personnel (règles internes de la banque)
    bank_apport_min_pct: float = 0.10
    bank_apport_recommande_pct: float = 0.20

    @classmethod
    def from_env(cls) -> "MortgageUnderwritingSettings":
        """Load mortgage underwriting settings from environment variables."""
        return cls(
            enabled=os.getenv("MORTGAGE_ENABLED", "true").lower() == "true",
            doc_analyzer=os.getenv("MORTGAGE_DOC_ANALYZER", "mortgageDocAnalyzer"),
            policies_path=os.getenv(
                "MORTGAGE_POLICIES_PATH", "prompts/mortgage-underwriting-policies.json"
            ),
            taux_sensibilite_buffer_pct=float(os.getenv("TAUX_SENSIBILITE_BUFFER_PCT", "1.0")),
            osfi_mqr_floor_pct=float(os.getenv("OSFI_MQR_FLOOR_PCT", "5.25")),
            osfi_mqr_buffer_pct=float(os.getenv("OSFI_MQR_BUFFER_PCT", "1.0")),
            gds_limit_standard=float(os.getenv("GDS_LIMIT_STANDARD", "0.35")),
            tds_limit_standard=float(os.getenv("TDS_LIMIT_STANDARD", "0.35")),
            ltv_limit_conventional=float(os.getenv("LTV_LIMIT_CONVENTIONAL", "0.90")),
            ltv_limit_insured=float(os.getenv("LTV_LIMIT_INSURED", "1.00")),
            max_amortization_insured=int(os.getenv("MAX_AMORT_INSURED", "25")),
            max_amortization_uninsured=int(os.getenv("MAX_AMORT_UNINSURED", "25")),
            bank_apport_min_pct=float(os.getenv("BANK_APPORT_MIN_PCT", "0.10")),
            bank_apport_recommande_pct=float(
                os.getenv("BANK_APPORT_RECOMMANDE_PCT", "0.20")
            ),
        )


@dataclass
class MistralSettings:
    """Settings for Mistral Document AI v25.12 OCR fallback."""

    endpoint: str = ""
    api_key: str = ""
    deployment: str = "mistral-document-ai-2512"
    api_version: str = "2024-05-01-preview"
    enabled: bool = False

    @classmethod
    def from_env(cls) -> "MistralSettings":
        """Load Mistral settings from environment variables."""
        return cls(
            endpoint=(os.getenv("MISTRAL_ENDPOINT", "") or "").rstrip("/"),
            api_key=os.getenv("MISTRAL_API_KEY", ""),
            deployment=os.getenv("MISTRAL_DEPLOYMENT_2512", "mistral-document-ai-2512"),
            api_version=os.getenv("MISTRAL_API_VERSION", "2024-05-01-preview"),
            enabled=os.getenv("MISTRAL_ENABLED", "false").lower() == "true",
        )

    def validate(self) -> list:
        """Validate Mistral configuration. Returns list of errors (empty if valid)."""
        errors = []
        if not self.endpoint:
            errors.append("MISTRAL_ENDPOINT not set")
        if not self.api_key:
            errors.append("MISTRAL_API_KEY not set")
        if not self.deployment:
            errors.append("MISTRAL_DEPLOYMENT_2512 not set")
        return errors


@dataclass
class FraudDetectionSettings:
    """Settings for fraud detection (2-model pipeline).

    - Vision model (GPT-5.4 mini): image description + manipulation detection
    - Reasoning model (GPT-5.4 mini, reasoning low): fraud reasoning from descriptions
    - Web intelligence agent (Foundry Agent Service + Bing WebSearch)
    """

    enabled: bool = True
    # Vision model — image description
    vision_deployment_name: str = "gpt-5.4-mini"
    vision_model_name: str = "gpt-5.4-mini"
    # Reasoning model — fraud detection
    deployment_name: str = "gpt-5.4-mini"
    model_name: str = "gpt-5.4-mini"
    # Web intelligence — Foundry Agent Service with WebSearchTool
    web_intelligence_enabled: bool = False
    foundry_project_endpoint: str = ""  # mirrors FoundrySettings.project_endpoint
    web_intelligence_agent_name: str = "PrevaIQ-WebIntelligence"

    @classmethod
    def from_env(cls) -> "FraudDetectionSettings":
        """Load fraud detection settings from environment variables."""
        return cls(
            enabled=os.getenv("FRAUD_DETECTION_ENABLED", "true").lower() == "true",
            vision_deployment_name=os.getenv("FRAUD_VISION_DEPLOYMENT", "gpt-5.4-mini"),
            vision_model_name=os.getenv("FRAUD_VISION_MODEL", "gpt-5.4-mini"),
            deployment_name=os.getenv("FRAUD_DETECTION_DEPLOYMENT", "gpt-5.4-mini"),
            model_name=os.getenv("FRAUD_DETECTION_MODEL", "gpt-5.4-mini"),
            web_intelligence_enabled=os.getenv("WEB_INTELLIGENCE_ENABLED", "false").lower()
            == "true",
            foundry_project_endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT", ""),
            web_intelligence_agent_name=os.getenv(
                "WEB_INTELLIGENCE_AGENT_NAME", "PrevaIQ-WebIntelligence"
            ),
        )


@dataclass
class ContentUnderstandingSettings:
    endpoint: str
    api_key: Optional[str]
    analyzer_id: str
    api_version: str = "2025-11-01"
    completion_deployment: Optional[str] = None
    embedding_deployment: Optional[str] = None
    use_azure_ad: bool = False  # Use Azure AD authentication instead of subscription key
    enable_confidence_scores: bool = True  # Enable confidence scoring for field extraction
    custom_analyzer_id: str = "underwritingAnalyzer"  # Default custom analyzer (persona-specific)


@dataclass
class MarkItDownSettings:
    """Settings for the optional MarkItDown conversion path."""

    enabled: bool = True
    mode: str = "local"  # local, cu, or auto
    use_content_understanding: bool = False
    preferred_extensions: tuple[str, ...] = (
        ".doc",
        ".xls",
        ".ppt",
        ".odt",
        ".ods",
        ".odp",
        ".eml",
        ".msg",
        ".csv",
        ".json",
        ".xml",
        ".html",
        ".htm",
        ".md",
        ".txt",
    )

    @classmethod
    def from_env(cls) -> "MarkItDownSettings":
        raw_mode = os.getenv("MARKITDOWN_MODE", "local").lower()
        mode = raw_mode if raw_mode in {"local", "cu", "auto"} else "local"
        raw_extensions = os.getenv("MARKITDOWN_PREFERRED_EXTENSIONS", "")
        if raw_extensions:
            preferred_extensions = tuple(
                ext if ext.startswith(".") else f".{ext}"
                for ext in (part.strip().lower() for part in raw_extensions.split(","))
                if ext
            )
        else:
            preferred_extensions = cls.preferred_extensions

        return cls(
            enabled=os.getenv("MARKITDOWN_ENABLED", "true").lower() == "true",
            mode=mode,
            use_content_understanding=os.getenv(
                "MARKITDOWN_USE_CONTENT_UNDERSTANDING", "false"
            ).lower()
            == "true",
            preferred_extensions=preferred_extensions,
        )


# Note: Field schemas are now managed in app/personas.py
# UNDERWRITING_FIELD_SCHEMA is imported from there for backward compatibility


@dataclass
class OpenAISettings:
    endpoint: str
    api_key: str
    deployment_name: str
    api_version: str = "2025-04-01-preview"
    model_name: str = "gpt-5.4-mini"
    use_azure_ad: bool = False  # Use Azure AD auth instead of API key
    reasoning_effort: str = "low"
    # Interactive chat answers: lowest latency, workflows keep reasoning_effort
    chat_reasoning_effort: str = "none"
    # Chat-specific settings (for Ask IQ feature)
    # If not set, falls back to main deployment
    chat_deployment_name: Optional[str] = None
    chat_model_name: Optional[str] = None
    chat_api_version: Optional[str] = None
    # Nano model — lightweight tasks (sentiment, context labels, quick intent)
    nano_deployment_name: Optional[str] = None
    nano_model_name: Optional[str] = None
    # Fallback endpoint for rate limiting (429) errors
    fallback_endpoint: Optional[str] = None
    fallback_api_key: Optional[str] = None
    fallback_deployment_name: Optional[str] = None
    fallback_api_version: Optional[str] = None
    fallback_use_azure_ad: bool = False  # Use Azure AD for fallback

    def get_deployment(self, tier: str = "primary") -> tuple[str, str]:
        """Return (deployment_name, model_name) for the given tier.

        Tiers cascade to the next-best available model:
          nano → chat → primary
          chat → primary
          primary → deployment_name
        """
        if tier == "nano":
            if self.nano_deployment_name:
                return self.nano_deployment_name, self.nano_model_name or "gpt-5.4-nano"
            tier = "chat"  # fallback
        if tier == "chat":
            if self.chat_deployment_name:
                return self.chat_deployment_name, self.chat_model_name or self.model_name
            # fall through to primary
        return self.deployment_name, self.model_name


@dataclass
class AppSettings:
    storage_root: str = "data"
    prompts_root: str = "prompts"  # Git-tracked folder for prompts and policies
    public_files_base_url: Optional[str] = None
    api_key: Optional[str] = None  # API key for backend authentication (X-API-Key header)


@dataclass
class ProcessingSettings:
    """Settings for document processing modes."""

    large_doc_threshold_kb: int = 1500  # Documents >= this size use large doc mode (1.5MB)
    chunk_size_chars: int = 50000  # Characters per chunk for summarization
    max_sample_pages: int = 15  # Max pages to sample for large docs
    condensed_context_max_chars: int = 40000  # Target size for condensed context
    auto_detect_mode: bool = True  # Automatically detect processing mode
    # Controlled orchestration budgets (0 disables a cap)
    extraction_budget_seconds: int = 900
    analysis_budget_seconds: int = 900
    analysis_token_budget: int = 400_000
    max_reextractions: int = 3  # per dossier, at most one per file
    reextraction_quality_threshold: float = 50.0  # _score_extraction_quality scale 0-100
    review_confidence_threshold: float = 0.6


@dataclass
class FoundrySettings:
    """Microsoft Foundry project endpoint (Agent Service / Responses agents only).

    Distinct from AZURE_OPENAI_ENDPOINT (direct model calls) and the Content
    Understanding endpoint (document analysis).
    """

    project_endpoint: str = ""
    # MAF agents: "responses" (OpenAIChatClient, default) or "chat_completions" (rollback)
    agents_openai_api: str = "responses"

    @classmethod
    def from_env(cls) -> "FoundrySettings":
        api = os.getenv("AGENTS_OPENAI_API", "responses").strip().lower()
        return cls(
            project_endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").rstrip("/"),
            agents_openai_api=api if api in {"responses", "chat_completions"} else "responses",
        )


@dataclass
class WebIQSettings:
    """Microsoft Web IQ remote MCP server (web/news/browse grounding)."""

    api_key: Optional[str] = None
    mcp_url: str = "https://api.microsoft.ai/v3/mcp"
    request_timeout_seconds: int = 30

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_env(cls) -> "WebIQSettings":
        return cls(
            api_key=os.getenv("WEBIQ_API_KEY") or None,
            mcp_url=os.getenv("WEBIQ_MCP_URL", "https://api.microsoft.ai/v3/mcp"),
            request_timeout_seconds=int(os.getenv("WEBIQ_TIMEOUT_SECONDS", "30")),
        )


@dataclass
class Settings:
    content_understanding: ContentUnderstandingSettings
    openai: OpenAISettings
    app: AppSettings
    processing: ProcessingSettings
    database: DatabaseSettings
    rag: RAGSettings
    automotive_claims: AutomotiveClaimsSettings
    mortgage_underwriting: MortgageUnderwritingSettings
    mistral: MistralSettings
    fraud_detection: FraudDetectionSettings
    markitdown: MarkItDownSettings
    brand_name: str = "PrevaIQ"
    webiq: WebIQSettings = field(default_factory=WebIQSettings)
    foundry: FoundrySettings = field(default_factory=FoundrySettings)


def load_settings() -> Settings:
    """Load configuration from environment variables."""

    use_azure_ad = os.getenv("AZURE_CONTENT_UNDERSTANDING_USE_AZURE_AD", "true").lower() == "true"
    api_key = os.getenv("AZURE_CONTENT_UNDERSTANDING_API_KEY") or None

    cu = ContentUnderstandingSettings(
        endpoint=os.getenv("AZURE_CONTENT_UNDERSTANDING_ENDPOINT", "").rstrip("/"),
        api_key=api_key,
        analyzer_id=os.getenv("AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID", "prebuilt-layout"),
        api_version=os.getenv("AZURE_CONTENT_UNDERSTANDING_API_VERSION", "2025-11-01"),
        completion_deployment=os.getenv(
            "AZURE_CONTENT_UNDERSTANDING_COMPLETION_DEPLOYMENT",
            "gpt-5.4-mini",
        )
        or None,
        embedding_deployment=os.getenv(
            "AZURE_CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT",
            "text-embedding-3-large",
        )
        or None,
        use_azure_ad=use_azure_ad,
    )

    oa = OpenAISettings(
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
        deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.4-mini"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        model_name=os.getenv("AZURE_OPENAI_MODEL_NAME", "gpt-5.4-mini"),
        use_azure_ad=os.getenv("AZURE_OPENAI_USE_AZURE_AD", "true").lower() == "true",
        reasoning_effort=os.getenv("AZURE_OPENAI_REASONING_EFFORT", "low").lower(),
        chat_reasoning_effort=os.getenv("AZURE_OPENAI_CHAT_REASONING_EFFORT", "none").lower(),
        # Chat-specific settings for Ask IQ (defaults to main model if not set)
        chat_deployment_name=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME") or None,
        chat_model_name=os.getenv("AZURE_OPENAI_CHAT_MODEL_NAME") or None,
        chat_api_version=os.getenv("AZURE_OPENAI_CHAT_API_VERSION") or None,
        # Nano model — lightweight tasks
        nano_deployment_name=os.getenv("AZURE_OPENAI_NANO_DEPLOYMENT_NAME", "gpt-5.4-nano") or None,
        nano_model_name=os.getenv("AZURE_OPENAI_NANO_MODEL_NAME", "gpt-5.4-nano") or None,
        # Fallback endpoint for rate limiting
        fallback_endpoint=os.getenv("AZURE_OPENAI_FALLBACK_ENDPOINT", "").rstrip("/") or None,
        fallback_api_key=os.getenv("AZURE_OPENAI_FALLBACK_API_KEY") or None,
        fallback_deployment_name=os.getenv("AZURE_OPENAI_FALLBACK_DEPLOYMENT_NAME") or None,
        fallback_api_version=os.getenv("AZURE_OPENAI_FALLBACK_API_VERSION") or None,
        fallback_use_azure_ad=os.getenv("AZURE_OPENAI_FALLBACK_USE_AZURE_AD", "false").lower()
        == "true",
    )

    app = AppSettings(
        storage_root=os.getenv("UW_APP_STORAGE_ROOT", "data"),
        prompts_root=os.getenv("UW_APP_PROMPTS_ROOT", "prompts"),
        public_files_base_url=os.getenv("PUBLIC_FILES_BASE_URL") or None,
        api_key=os.getenv("API_KEY") or None,
    )

    db = DatabaseSettings(
        backend=os.getenv("DATABASE_BACKEND", "json"),
        host=os.getenv("POSTGRESQL_HOST"),
        port=int(os.getenv("POSTGRESQL_PORT", 5432)) if os.getenv("POSTGRESQL_PORT") else None,
        database=os.getenv("POSTGRESQL_DATABASE"),
        user=os.getenv("POSTGRESQL_USER"),
        password=os.getenv("POSTGRESQL_PASSWORD"),
        ssl_mode=os.getenv("POSTGRESQL_SSL_MODE"),
        schema=os.getenv("POSTGRESQL_SCHEMA"),
    )

    rag = RAGSettings(
        enabled=os.getenv("RAG_ENABLED", "false").lower() == "true",
        top_k=int(os.getenv("RAG_TOP_K", 5)),
        similarity_threshold=float(os.getenv("RAG_SIMILARITY_THRESHOLD", 0.5)),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", 1536)),
        embedding_deployment=os.getenv("EMBEDDING_DEPLOYMENT")
        or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
    )

    auto_claims = AutomotiveClaimsSettings.from_env()
    mortgage = MortgageUnderwritingSettings.from_env()
    mistral = MistralSettings.from_env()
    fraud = FraudDetectionSettings.from_env()
    markitdown = MarkItDownSettings.from_env()
    foundry = FoundrySettings.from_env()
    fraud.foundry_project_endpoint = foundry.project_endpoint

    processing = ProcessingSettings(
        large_doc_threshold_kb=int(os.getenv("LARGE_DOC_THRESHOLD_KB", "1500")),
        chunk_size_chars=int(os.getenv("CHUNK_SIZE_CHARS", "50000")),
        max_sample_pages=int(os.getenv("MAX_SAMPLE_PAGES", "15")),
        condensed_context_max_chars=int(os.getenv("CONDENSED_CONTEXT_MAX_CHARS", "40000")),
        auto_detect_mode=os.getenv("AUTO_DETECT_PROCESSING_MODE", "true").lower() == "true",
        extraction_budget_seconds=int(os.getenv("EXTRACTION_BUDGET_SECONDS", "900")),
        analysis_budget_seconds=int(os.getenv("ANALYSIS_BUDGET_SECONDS", "900")),
        analysis_token_budget=int(os.getenv("ANALYSIS_TOKEN_BUDGET", "400000")),
        max_reextractions=int(os.getenv("MAX_REEXTRACTIONS", "3")),
        reextraction_quality_threshold=float(os.getenv("REEXTRACTION_QUALITY_THRESHOLD", "50")),
        review_confidence_threshold=float(os.getenv("REVIEW_CONFIDENCE_THRESHOLD", "0.6")),
    )

    from app.brands import get_current_brand_profile

    brand_profile = get_current_brand_profile()

    return Settings(
        content_understanding=cu,
        openai=oa,
        app=app,
        processing=processing,
        database=db,
        rag=rag,
        automotive_claims=auto_claims,
        mortgage_underwriting=mortgage,
        mistral=mistral,
        fraud_detection=fraud,
        markitdown=markitdown,
        brand_name=brand_profile.brand_name,
        webiq=WebIQSettings.from_env(),
        foundry=foundry,
    )


def validate_settings(settings: Settings) -> List[str]:
    """Validate configuration and return a list of human-readable error messages."""
    errors: List[str] = []

    # Content Understanding
    if not settings.content_understanding.endpoint:
        errors.append("AZURE_CONTENT_UNDERSTANDING_ENDPOINT is not set.")
    if (
        not settings.content_understanding.use_azure_ad
        and not settings.content_understanding.api_key
    ):
        errors.append(
            "AZURE_CONTENT_UNDERSTANDING_API_KEY is not set (required when not using Azure AD auth)."
        )
    if not settings.content_understanding.analyzer_id:
        errors.append("AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID is not set.")

    # OpenAI
    if not settings.openai.endpoint:
        errors.append("AZURE_OPENAI_ENDPOINT is not set.")
    if not settings.openai.use_azure_ad and not settings.openai.api_key:
        errors.append("AZURE_OPENAI_API_KEY is not set.")
    if not settings.openai.deployment_name:
        errors.append("AZURE_OPENAI_DEPLOYMENT_NAME is not set.")

    # App
    if not settings.app.storage_root:
        errors.append("UW_APP_STORAGE_ROOT is not set or empty.")

    return errors
