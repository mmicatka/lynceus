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

    return con


def export_parquet(
    con: duckdb.DuckDBPyConnection,
    table: pa.Table,
    file_path: str,
):
    con.register("_output_table", table)
    con.execute(f"COPY (SELECT * FROM _output_table) TO '{file_path}' (FORMAT PARQUET)")
    con.unregister("_output_table")


def file_exists(con: duckdb.DuckDBPyConnection, file_path: str) -> bool:
    try:
        con.execute("SELECT 1 FROM read_parquet(?) LIMIT 1", [file_path])
        return True
    except duckdb.Error:
        return False
