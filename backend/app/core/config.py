import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def load_admin_api_key() -> SecretStr | None:
    value = os.getenv("CREDABLE_ADMIN_API_KEY")
    return SecretStr(value) if value else None


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
    demo_assessments_path: Path = BACKEND_ROOT / "app" / "data" / "demo_assessments.json"
    demo_supplemental_assessments_path: Path = (
        BACKEND_ROOT / "app" / "data" / "demo_supplemental_assessments.json"
    )
    demo_policy_boundaries_path: Path = (
        BACKEND_ROOT / "app" / "data" / "demo_policy_boundaries.json"
    )
    demo_evidence_candidates_path: Path = (
        BACKEND_ROOT / "app" / "data" / "demo_evidence_candidates.json"
    )
    demo_evidence_submissions_path: Path = (
        BACKEND_ROOT / "app" / "data" / "demo_evidence_submissions.json"
    )
    demo_evidence_quality_path: Path = BACKEND_ROOT / "app" / "data" / "demo_evidence_quality.json"
    demo_products_path: Path = BACKEND_ROOT / "app" / "data" / "demo_products.json"
    demo_product_conditions_path: Path = (
        BACKEND_ROOT / "app" / "data" / "demo_product_conditions.json"
    )
    admin_api_key: SecretStr | None = Field(default_factory=load_admin_api_key)


settings = Settings()
