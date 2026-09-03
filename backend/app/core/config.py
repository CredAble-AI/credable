from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = "CredAble Backend"
    slug: str = "credible-backend"
    version: str = "0.1.0"


settings = Settings()
