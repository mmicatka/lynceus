# modules/local/surrogate_model/src/surrogate_model/models/registry.py


from pathlib import Path
from typing import Any


class ModelBundle:
    def __init__(
        self, estimator: Any, feature_spec: FeatureMatrixSpec, metadata: dict
    ) -> None:
        self.estimator = estimator
        self.feature_spec = feature_spec
        self.metadata = metadata

    def save(self, path: str | Path) -> Path:
        out_dir = Path(path)
        out_dir.mkdir(parents=True, exist_ok=True)

        joblib.dump(self.estimator, out_dir / MODEL_FILENAME)

        (out_dir / FEATURE_SPEC_FILENAME).write_text(
            json.dumps(self.feature_spec.to_dict(), indent=2)
        )

        metadata = {**self.metadata, "saved_at": datetime.now(timezone.utc).isoformat()}
        (out_dir / METADATA_FILENAME).write_text(
            json.dumps(metadata, indent=2, default=str)
        )

        return out_dir

    @classmethod
    def load(cls, path: str | Path) -> "ModelBundle":
        in_dir = Path(path)
        missing = [
            f
            for f in (MODEL_FILENAME, FEATURE_SPEC_FILENAME, METADATA_FILENAME)
            if not (in_dir / f).exists()
        ]
        if missing:
            raise FileNotFoundError(
                f"Model bundle at {in_dir} is missing required file(s): {missing}"
            )

        estimator = joblib.load(in_dir / MODEL_FILENAME)
        feature_spec = FeatureMatrixSpec.from_dict(
            json.loads((in_dir / FEATURE_SPEC_FILENAME).read_text())
        )
        metadata = json.loads((in_dir / METADATA_FILENAME).read_text())

        return cls(estimator=estimator, feature_spec=feature_spec, metadata=metadata)
