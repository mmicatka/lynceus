# modules/local/generate_manifest/src/generate_manifest/cli.py

import click


@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Path to the input file.",
)
@click.option(
    "--output",
    "output",
    type=str,
    required=True,
    help="Output manifest.",
)
def generate_manifest():