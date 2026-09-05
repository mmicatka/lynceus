# libs/lynceus-utils/src/lynceus_utils/storage/blob_storage.py

from typing import Literal

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class BlobStorageSettings(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True)

    access_key_id: str = Field(default="", validation_alias="BLOB_ACCESS_KEY_ID")
    access_key: str = Field(default="", validation_alias="BLOB_ACCESS_KEY")
    endpoint: HttpUrl | str = Field(default="", validation_alias="BLOB_ENDPOINT")
    region: str = Field(default="", validation_alias="BLOB_REGION")
    use_ssl: bool = Field(default=True, validation_alias="BLOB_USE_SSL")
    url_style: Literal["path", "virtual"] = Field(
        default="path", validation_alias="BLOB_URL_STYLE"
    )


def get_blob_storage_settings() -> BlobStorageSettings:
    return BlobStorageSettings()
