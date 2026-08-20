# modules/local/rebalance_candidates/src/rebalance_candidates/cli.py

import argparse
import logging
import os
import sys

import duckdb

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("gather_shard_candidates")

HASH_KEY_CANDIDATES = ("blake3_hash", "candidate_id", "smiles")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-uri", required=True)
    parser.add_argument("--output-uri-prefix", required=True)
    parser.add_argument("--num-shards", type=int, required=True)
    parser.add_argument("--s3-endpoint", required=True)
    parser.add_argument("--s3-region", default="garage")
    parser.add_argument("--s3-url-style", default="path", choices=["path", "vhost"])
    parser.add_argument("--s3-use-ssl", action="store_true")
    return parser.parse_args()


def _configure_s3(con: duckdb.DuckDBPyConnection, args: argparse.Namespace) -> None:
    endpoint_host = args.s3_endpoint.removeprefix("https://").removeprefix("http://")

    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute("SET s3_endpoint = ?", [endpoint_host])
    con.execute("SET s3_region = ?", [args.s3_region])
    con.execute("SET s3_url_style = ?", [args.s3_url_style])
    con.execute(f"SET s3_use_ssl = {'true' if args.s3_use_ssl else 'false'}")
    access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not access_key_id or not secret_access_key:
        logger.error("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must both be set")
        sys.exit(1)

    con.execute("SET s3_access_key_id = ?", [access_key_id])
    con.execute("SET s3_secret_access_key = ?", [secret_access_key])


def _resolve_hash_key(con: duckdb.DuckDBPyConnection, input_uri: str) -> str:
    schema_columns = {
        row[0]
        for row in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{input_uri}') LIMIT 0"
        ).fetchall()
    }
    for candidate_column in HASH_KEY_CANDIDATES:
        if candidate_column in schema_columns:
            return candidate_column
    logger.error(
        "no usable hash key column found; expected one of %s, got %s",
        HASH_KEY_CANDIDATES,
        sorted(schema_columns),
    )
    sys.exit(1)


def _write_shards(
    con: duckdb.DuckDBPyConnection,
    input_uri: str,
    hash_key: str,
    num_shards: int,
    output_uri_prefix: str,
) -> None:
    con.execute(
        f"""
        CREATE VIEW candidates AS
        SELECT *, hash({hash_key}) % {num_shards} AS shard_id
        FROM read_parquet('{input_uri}', union_by_name=true)
        """
    )

    row_count = con.execute("SELECT count(*) FROM candidates").fetchone()[0]
    if row_count == 0:
        logger.error(
            "input %s matched zero rows; refusing to write empty shards", input_uri
        )
        sys.exit(1)

    logger.info(
        "gathered %d rows from %s into %d shards", row_count, input_uri, num_shards
    )

    for shard_id in range(num_shards):
        shard_uri = f"{output_uri_prefix.rstrip('/')}/shard_{shard_id:04d}.parquet"
        con.execute(
            f"""
            COPY (
                SELECT * EXCLUDE (shard_id)
                FROM candidates
                WHERE shard_id = {shard_id}
            ) TO '{shard_uri}' (FORMAT PARQUET)
            """
        )
        logger.info("wrote shard %d -> %s", shard_id, shard_uri)


def rebalance_candidates() -> None:
    args = _parse_args()

    con = duckdb.connect()
    _configure_s3(con, args)

    hash_key = _resolve_hash_key(con, args.input_uri)
    logger.info("using hash key column: %s", hash_key)

    _write_shards(
        con, args.input_uri, hash_key, args.num_shards, args.output_uri_prefix
    )
