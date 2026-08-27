# libs/lynceus-utils/src/lynceus_utils/storage/blob_storage.py

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class BlobStorageSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    access_key_id: str = Field(..., validation_alias="BLOB_ACCESS_KEY_ID")
    access_key: str = Field(..., validation_alias="BLOB_ACCESS_KEY")
    endpoint: HttpUrl | str = Field(..., validation_alias="BLOB_ENDPOINT")
    region: str = Field(..., validation_alias="BLOB_REGION")
    use_ssl: bool = Field(True, validation_alias="BLOB_USE_SSL")
    url_style: Literal["path", "virtual"] = Field(
        "path", validation_alias="BLOB_URL_STYLE"
    )


def get_blob_storage_settings() -> BlobStorageSettings:
    return BlobStorageSettings(
        access_key_id=os.environ.get("BLOB_ACCESS_KEY_ID"),
        access_key=os.environ.get("BLOB_ACCESS_KEY"),
        endpoint=os.environ.get("BLOB_ENDPOINT"),
        region=os.environ.get("BLOB_REGION"),
        use_ssl=os.environ.get("BLOB_USE_SSL", "true"),
        url_style=os.environ.get("BLOB_URL_STYLE", "path"),
    )
