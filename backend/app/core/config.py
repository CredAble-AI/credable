from pathlib import Path

from pydantic import BaseModel, ConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = "CredAble Backend"
    slug: str = "credible-backend"
    version: str = "0.1.0"
    database_path: Path = BACKEND_ROOT / "data" / "credable.db"
    demo_cases_path: Path = BACKEND_ROOT / "app" / "data" / "demo_cases.json"
    demo_profiles_path: Path = BACKEND_ROOT / "app" / "data" / "demo_profiles.json"
    demo_consent_scopes_path: Path = BACKEND_ROOT / "app" / "data" / "demo_consent_scopes.json"
    demo_products_path: Path = BACKEND_ROOT / "app" / "data" / "demo_products.json"
    demo_product_conditions_path: Path = (
        BACKEND_ROOT / "app" / "data" / "demo_product_conditions.json"
    )


settings = Settings()
