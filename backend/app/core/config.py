import os
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr

BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_ROOT / ".env", override=False)


class ExplanationProviderMode(StrEnum):
    DEMO = "demo"
    GEMINI = "gemini"


def load_gemini_api_key() -> SecretStr | None:
    value = os.getenv("GEMINI_API_KEY")
    return SecretStr(value) if value else None


def load_explanation_provider_mode() -> ExplanationProviderMode:
    value = os.getenv("CREDABLE_EXPLANATION_PROVIDER", ExplanationProviderMode.DEMO)
    return ExplanationProviderMode(value.strip().lower())


def load_gemini_model() -> str:
    return os.getenv("CREDABLE_GEMINI_MODEL", "gemini-3.5-flash-lite").strip()


def load_gemini_timeout_seconds() -> float:
    return float(os.getenv("CREDABLE_GEMINI_TIMEOUT_SECONDS", "10"))


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = "CredAble Backend"
    slug: str = "credible-backend"
    version: str = "0.1.0"
    database_path: Path = BACKEND_ROOT / "data" / "credable.db"
    demo_profiles_path: Path = BACKEND_ROOT / "app" / "data" / "demo_profiles.json"
    demo_consent_scopes_path: Path = BACKEND_ROOT / "app" / "data" / "demo_consent_scopes.json"
    demo_data_sources_path: Path = BACKEND_ROOT / "app" / "data" / "demo_data_sources.json"
    demo_bank_data_path: Path = BACKEND_ROOT / "app" / "data" / "demo_bank_data.json"
    demo_credit_history_path: Path = BACKEND_ROOT / "app" / "data" / "demo_credit_history.json"
    demo_loan_history_path: Path = BACKEND_ROOT / "app" / "data" / "demo_loan_history.json"
    demo_credit_exposures_path: Path = BACKEND_ROOT / "app" / "data" / "demo_credit_exposures.json"
    demo_assessments_path: Path = BACKEND_ROOT / "app" / "data" / "demo_assessments.json"
    demo_supplemental_assessments_path: Path = (
        BACKEND_ROOT / "app" / "data" / "demo_supplemental_assessments.json"
    )
    demo_model_registry_path: Path = BACKEND_ROOT / "app" / "data" / "demo_model_registry.json"
    demo_policy_boundaries_path: Path = (
        BACKEND_ROOT / "app" / "data" / "demo_policy_boundaries.json"
    )
    demo_evidence_candidates_path: Path = (
        BACKEND_ROOT / "app" / "data" / "demo_evidence_candidates.json"
    )
    demo_evidence_submissions_path: Path = (
        BACKEND_ROOT / "app" / "data" / "demo_evidence_submissions.json"
    )
    demo_evidence_files_path: Path = BACKEND_ROOT / "app" / "data" / "demo_evidence_files.json"
    demo_evidence_quality_path: Path = BACKEND_ROOT / "app" / "data" / "demo_evidence_quality.json"
    demo_products_path: Path = BACKEND_ROOT / "app" / "data" / "demo_products.json"
    demo_product_conditions_path: Path = (
        BACKEND_ROOT / "app" / "data" / "demo_product_conditions.json"
    )
    explanation_provider: ExplanationProviderMode = Field(
        default_factory=load_explanation_provider_mode
    )
    gemini_api_key: SecretStr | None = Field(default_factory=load_gemini_api_key)
    gemini_model: str = Field(default_factory=load_gemini_model, min_length=1)
    gemini_timeout_seconds: float = Field(
        default_factory=load_gemini_timeout_seconds,
        ge=1,
        le=30,
    )


settings = Settings()
