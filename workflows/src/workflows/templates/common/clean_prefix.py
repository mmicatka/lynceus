# workflows/templates/common/clean_prefix.py

from hera.workflows import Container, Parameter

from workflows.resources.volumes import LYNCEUS_VOLUME

CLEAN_SCRIPT = 'test -n "$1" && rm -rf "$0/$1"'


def build_clean_prefix_template() -> Container:
    return Container(
        name="clean-prefix",
        image="alpine:3.20",
        command=["sh", "-c"],
        args=[
            CLEAN_SCRIPT,
            "{{inputs.parameters.mount_path}}",
            "{{inputs.parameters.prefix}}",
        ],
        inputs=[Parameter(name="mount_path"), Parameter(name="prefix")],
        volumes=[LYNCEUS_VOLUME],
    )
