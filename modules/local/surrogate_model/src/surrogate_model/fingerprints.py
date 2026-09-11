# modules/local/surrogate_model/src/surrogate_model/fingerprints.py

import numpy as np
import polars as pl
from rdkit import Chem
from skfp.fingerprints import (
    E3FPFingerprint,
    GETAWAYFingerprint,
    PharmacophoreFingerprint,
    USRCATFingerprint,
    WHIMFingerprint,
)
from tqdm.auto import tqdm

DEFAULT_FINGERPRINTS = {
    "e3fp": E3FPFingerprint(n_jobs=-1),
    "usrcat": USRCATFingerprint(n_jobs=-1),
    "whim": WHIMFingerprint(n_jobs=-1),
    "getaway": GETAWAYFingerprint(n_jobs=-1),
    "pharmacophore_3d": PharmacophoreFingerprint(
        variant="folded",
        use_3D=True,
        n_jobs=-1,
        fp_size=1024,
    ),
}


def parse_mol_batches(sdf_series, batch_size):
    for i in range(0, len(sdf_series), batch_size):
        chunk = sdf_series[i : i + batch_size]
        mols = [Chem.MolFromMolBlock(sdf) for sdf in chunk]
        failed_indices = [j for j, mol in enumerate(mols) if mol is None]
        if failed_indices:
            raise RuntimeError(
                f"Failed to parse {len(failed_indices)} SDF blocks in batch starting at"
                f" row {i}: local indices {failed_indices}"
            )
        yield mols


def generate_fingerprints(df, fps=DEFAULT_FINGERPRINTS, batch_size=1000):

    for name, fp_transformer in fps.items():
        sample = fp_transformer.transform(
            next(parse_mol_batches(df["conformer_sdf"].head(batch_size), batch_size))
        )
        print(name, sample.dtype, sample.shape)

    total_batches = (len(df) + batch_size - 1) // batch_size
    result_columns = []

    for name, fp_transformer in fps.items():
        fp_list = [
            fp_transformer.transform(batch)
            for batch in tqdm(
                parse_mol_batches(df["conformer_sdf"], batch_size),
                total=total_batches,
                desc=f"Generating {name}",
            )
        ]
        fp_array = np.vstack(fp_list)
        del fp_list

        if fp_array.shape[0] != len(df):
            raise RuntimeError(
                f"{name}: expected {len(df)} rows, got {fp_array.shape[0]}"
            )

        arr_dtype = (
            pl.Float64 if np.issubdtype(fp_array.dtype, np.floating) else pl.Int64
        )
        fp_array = fp_array.astype(
            np.float64 if arr_dtype == pl.Float64 else np.int64, copy=False
        )
        result_columns.append(
            pl.Series(name, fp_array).cast(pl.Array(arr_dtype, fp_array.shape[1]))
        )
        del fp_array

    return df.with_columns(result_columns)
