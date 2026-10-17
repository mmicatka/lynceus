# workflows/src/workflows/templates/surrogate/surrogate_sample.py


def surrogate_sample_template(
    base_path: str,
    source: str,
    features_input_prefix: str,
    conformers_input_prefix: str,
    output_prefix: str,
    num_samples: int,
    id_column: str = "id",
):
    import os
    import subprocess

    subprocess.run(
        [
            "surrogate-sample",
            "--features-input",
            os.path.join(base_path, features_input_prefix, source),
            "--conformers-input",
            os.path.join(base_path, conformers_input_prefix, source),
            "--output",
            os.path.join(base_path, output_prefix, source),
            "--num-samples",
            str(num_samples),
            "--id-column",
            id_column,
        ],
        check=True,
    )
