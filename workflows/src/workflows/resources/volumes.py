# workflows/src/workflows/utils/volumes.py

from hera.workflows import ExistingVolume

LYNCEUS_VOLUME = ExistingVolume(
    name="lynceus-data",
    claim_name="lynceus-bucket-pvc",
    mount_path="/mnt/data",
)
