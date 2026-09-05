# libs/lynceus-utils/src/lynceus_utils/storage/filesystem.py

from typing import Optional

import fsspec

from .blob_storage import BlobStorageSettings


def _fsspec_storage_options(
    blob_storage_settings: Optional[BlobStorageSettings],
) -> dict:
    if blob_storage_settings is None:
        return {}

    scheme = "https" if blob_storage_settings.use_ssl else "http"
    endpoint = str(blob_storage_settings.endpoint)
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"{scheme}://{endpoint}"

    return {
        "key": blob_storage_settings.access_key_id,
        "secret": blob_storage_settings.access_key,
        "client_kwargs": {
            "endpoint_url": endpoint,
            "region_name": blob_storage_settings.region,
        },
        "config_kwargs": {
            "s3": {
                "addressing_style": (
                    "path" if blob_storage_settings.url_style == "path" else "virtual"
                )
            }
        },
    }


def get_filesystem(
    blob_storage_settings: Optional[BlobStorageSettings],
) -> fsspec.AbstractFileSystem:
    if blob_storage_settings:
        return fsspec.filesystem("s3", **_fsspec_storage_options(blob_storage_settings))
    return fsspec.filesystem("file")
