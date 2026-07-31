lynceus_chem/docking/
├── types.py          — DockingResult, SearchBox, DockingError, ProviderNotAvailableError
├── base.py            — DockingProvider ABC (dock, dock_batch, validate_environment)
├── parsing.py          — shared Vina-output PDBQT parser, tested against synthetic fixtures
├── providers/
│   ├── vina_cpu.py     — vina Python bindings; dock_batch loops (optionally multiprocessed)
│   └── vina_gpu.py     — Vina-GPU+ subprocess wrapper; dock_batch uses --ligand_directory
├── registry.py         — get_provider("cpu"/"gpu", **kwargs) factory
└── cli.py              — argparse CLI with --provider and --batch-size
