lynceus_chem/docking/
├── types.py          — DockingResult, SearchBox, DockingError, ProviderNotAvailableError
├── base.py            — DockingProvider ABC (dock, dock_batch, validate_environment)
├── parsing.py          — shared Vina-output PDBQT parser, tested against synthetic fixtures
├── providers/
│   ├── vina_cpu.py     — vina Python bindings; dock_batch loops (optionally multiprocessed)
│   └── vina_gpu.py     — Vina-GPU+ subprocess wrapper; dock_batch uses --ligand_directory
├── registry.py         — get_provider("cpu"/"gpu", **kwargs) factory
└── cli.py              — argparse CLI with --provider and --batch-size

 docker run -t \
  -v "$(pwd)/work:/app/work" \
  lynceus/docking-run:cpu-0.1.0 \
  docking-run --provider cpu \
  --receptor work/2b/b37b95ec1090e15bf010954947d50e/1STP_static_v1_prepped/1STP.pdbqt \
  --ligands work/cd/7b863476bd78a964c4cfb9824b14b5/candidates_conformers_converted/partitions/0/* \
  --center 11.093 0.8061 -9.7802 \
  --size 6.317 6.317 6.317 \
  --n-workers 1

docker run --rm --gpus all \
  -v "$(pwd)/work:/app/work" \
  -t lynceus/docking-run:gpu-0.1.0 \
  docking-run --provider gpu \
  --receptor work/2b/b37b95ec1090e15bf010954947d50e/1STP_static_v1_prepped/1STP.pdbqt \
  --ligands work/cd/7b863476bd78a964c4cfb9824b14b5/candidates_conformers_converted/partitions/0/* \
  --center 11.093 0.8061 -9.7802 \
  --size 6.317 6.317 6.317 \
  --vina-gpu-binary AutoDock-Vina-GPU-2-1

[
  {
    "schema_version": "1.0.0",
    "site_id": "1STP:p2rank:1",
    "conformational_state_id": "1STP",
    "center": [
      11.093,
      0.8061,
      -9.7802
    ],
    "extent": {
      "kind": "sphere",
      "center": [
        11.093,
        0.8061,
        -9.7802
      ],
      "radius": 6.31728166677784
    },
    "lining_residues": [],
    "pocket_score": 17.47,
    "provenance": {
      "tool": "p2rank",
      "pocket_rank": 1,
      "probability": 0.803
    }
  }
]
