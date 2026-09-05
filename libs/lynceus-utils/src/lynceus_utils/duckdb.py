# libs/lynceus-utils/src/lynceus_utils/duckdb.py

from typing import Optional

import duckdb
import pyarrow as pa

from .storage import BlobStorageSettings


def get_connection(
    blob_storage_settings: Optional[BlobStorageSettings] = None,
) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()

    if blob_storage_settings:
        con.execute("LOAD httpfs")

        con.execute("SET s3_endpoint = ?", [blob_storage_settings.endpoint])
        con.execute("SET s3_region = ?", [blob_storage_settings.region])
        con.execute("SET s3_url_style = ?", [blob_storage_settings.url_style])
        con.execute(
            f"SET s3_use_ssl = {'true' if blob_storage_settings.use_ssl else 'false'}"
        )
        con.execute("SET s3_access_key_id = ?", [blob_storage_settings.access_key_id])
        con.execute("SET s3_secret_access_key = ?", [blob_storage_settings.access_key])

    con.execute("SET arrow_large_buffer_size=true")

    return con


def export_parquet(
    con: duckdb.DuckDBPyConnection,
    data: pa.Table | pa.RecordBatch | duckdb.DuckDBPyRelation,
    file_path: str,
):
    con.register("_tmp_export_view", data)
    try:
        con.execute(f"COPY _tmp_export_view TO '{file_path}' (FORMAT PARQUET)")
    finally:
        con.unregister("_tmp_export_view")

    if not file_exists(con, file_path):
        raise RuntimeError(
            f"export_parquet: COPY reported success but {file_path} "
            "is not readable back via read_parquet — write did not land"
        )


def file_exists(con: duckdb.DuckDBPyConnection, file_path: str) -> bool:
    try:
        con.execute("SELECT 1 FROM read_parquet(?) LIMIT 1", [file_path])
        return True
    except duckdb.Error:
        return False
