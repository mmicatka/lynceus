
# Surrogate Model Features

## Model

Trained on initial, tested on holdout

| Num Candidates | Features | Top 1% P/R | Top 5% P/R | Top 10% P/R | Top 15% P/R |
| - | - | - | - | - | - |
| 100000 | atom_pair | 0.313/0.322 | 0.140/0.722 | 0.085/0.872 | 0.06/0.927 |
| 100000 | autocorr | 0.239/0.246 | 0.113/0.582 | 0.074/0.0.763 | 0.056/0.859 |
| 100000 | descriptors | 0.38/0.392 | 0.159/0.82 | 0.09/0.932 | 0.063/0.981 |
| 100000 | e3fp | 0.236/0.243 | 0.118/0.606 | 0.075/0.771 | 0.056/0.865 |
| 100000 | ecfp | 0.245/0.253 | 0.122/0.629 | 0.077/0.799 | 0.057/0.884 |
| 100000 | electroshape | 0.084/0.087 | 0.055/0.284 | 0.042/0.435 | 0.034/0.526 |
| 100000 | functional_groups | 0.218/0.224 | 0.105/0.543 | 0.070/0.718 | 0.053/0.816 |
| 100000 | morse | 0.26/0.268 | 0.119/0.613 | 0.076/0.781 | 0.057/0.877 |
| 100000 | pharmacophore_3d | 0.218/0.224 | 0.103/0.534 | 0.069/0.715 | 0.051/0.794 |
| 100000 | rdf | 0.192/0.198 | 0.102/0.524 | 0.069/0.712 | 0.053/0.813 |
| 100000 | topological_torsion | 0.269/0.277 | 0.119/0.613 | 0.075/0.772 | 0.056/0.86 |
| 100000 | usrcat | 0.138/0.142 | 0.085/0.437 | 0.062/0.638 | 0.048/0.736 |
| 100000 | whim | 0.086/0.089 | 0.058/0.3 | 0.046/0.477 | 0.039/0.601 |
| 100000 | all | 0.42/0.433 | 0.166/0.854 | 0.093/0.958 | 0.064/0.987 |
| 100000 | atom_pair, autocorr, descriptors, usrcat | 0.391/0.403 | 0.160/0.827 | 0.091/0.943 | 0.064/0.983 |
| 100000 | atom_pair, autocorr, descriptors, e3fp, usrcat | 0.397/0.409 | 0.163/0.843 | 0.092/0.954 | 0.064/0.986 |
| 100000 | atom_pair, autocorr, descriptors, morse, usrcat | 0.399/0.411 | 0.165/0.849 | 0.092/0.953 | 0.064/0.985 |
| 100000 | atom_pair, autocorr, descriptors, ecfp, electroshape, functional_groups, morse, rdf, topological_torsion, usrcat, whim | 0.423/0.436 | 0.166/0.855 | 0.093/0.959 | 0.064/0.986 |
| 100000 | atom_pair, autocorr, descriptors, ecfp, electroshape, functional_groups, morse, rdf, topological_torsion, usrcat, whim | 0.423/0.436 | 0.166/0.855 | 0.093/0.959 | 0.064/0.986 |
| 100000 | autocorr, descriptors, ecfp, functional_groups, morse, rdf, topological_torsion, usrcat, whim | 0.410/0.422 | 0.163/0.842 | 0.093/0.956 | 0.064/0.988 |
| 100000 | atom_pair, autocorr, descriptors, ecfp, functional_groups, morse, rdf, topological_torsion, usrcat, whim | 0.406/0.418 | 0.166/0.854 | 0.093/0.956 | 0.064/0.987 |

## Feature gen time

| Num compounds | Features | Workers | Time (sec) | Compounds per sec per core |
| - | - | - | - | - |
| 100000 | atom_pair | 16 | 16.5 | 378.8 |
| 100000 | autocorr | 16 | 7.1 | 880.3 |
| 100000 | descriptors | 16 | 107.6 | 58.1 |
| 30000 | e3fp | 16 | 120.0 | 15.6 |
| 100000 | ecfp | 16 | 10.2 | 612.7 |
| 100000 | electroshape | 16 | 22.1 | 282.8 |
| 100000 | functional_groups | 16 | 9.9 | 631.3 |
| 100000 | morse | 16 | 11.332 | 551.6 |
| 100000 | pharmacophore_3d | 16 | 68.3 | 91.5 |
| 100000 | rdf | 16 | 11.4 | 548.2 |
| 100000 | topological_torsion | 16 | 15.3 | 408.5 |
| 100000 | usrcat | 16 | 6.6 | 947.0 |
| 100000 | whim | 16 | 7.1 | 880.3 |
