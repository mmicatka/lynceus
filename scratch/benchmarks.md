# Benchmarks

## Preprocessing

| Num Samples | Num CPUs | Duration | CPU Hours | Samples/cpu hr |
| - | - | - | - | - |
| 4560139 | 24 | 6h 49 m | 188.5 | 24192 |

docker run -v ./targets/protein_ensembles:/app/protein_ensembles -v ./sample:/app/sample -v ./docking_run:/app/docking_run --rm registry.nebula.lan:5000/lynceus/docking-run:gpu-0.1.0 docking-run --ensemble protein_ensembles/T4_lysozyme_L99 --member-id 1L83 --ligands-path sample/shard_0.parquet --center 38.22 17.68 10.80 --size 6 6 6 --out-parquet docking_run/output.parquet --conformational-state-id 1L83 --num-modes 1 --site-id 1L83:p2rank:1
