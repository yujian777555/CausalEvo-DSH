"""Genome/phenotype audit (P4-R1.1-S4): enumerate the genotype space, map to
phenotypes, count degeneracies. Offline analysis; writes results/phase4/audit/.
"""
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from causalevo.evolution.genome import GENES, InterventionGenome  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "phase4" / "audit"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ranges = [range(hi + 1) for _n, hi in GENES]
    pheno_of = {}
    genotypes = []
    for combo in itertools.product(*ranges):
        g = InterventionGenome(combo)
        pheno = tuple(g.phenotype_transforms())
        genotypes.append((g.genome_id, combo))
        pheno_of[combo] = pheno
    pheno_counts = Counter(pheno_of.values())
    total_genotypes = len(genotypes)
    unique_phenotypes = len(pheno_counts)
    duplicates = {str(k): v for k, v in pheno_counts.items() if v > 1}

    # gene effectiveness: does flipping the gene alone ever change phenotype?
    gene_effect = {}
    for gi, (name, hi) in enumerate(GENES):
        changed = 0
        for combo in itertools.product(*ranges):
            for v in range(hi + 1):
                alt = list(combo)
                alt[gi] = v
                if tuple(alt) != combo and pheno_of[tuple(alt)] != pheno_of[combo]:
                    changed += 1
        gene_effect[name] = changed

    report = {
        "gene_space": {n: hi for n, hi in GENES},
        "total_genotypes": total_genotypes,
        "unique_phenotypes": unique_phenotypes,
        "duplicate_ratio": round(1 - unique_phenotypes / total_genotypes, 4),
        "duplicate_phenotypes": duplicates,
        "gene_effect_counts": gene_effect,
        "degenerate_genes": [n for n, c in gene_effect.items() if c == 0],
        "reserved_genes": ["reflection_step", "retry_strategy"],
        "effective_genes": [n for n, c in gene_effect.items() if c > 0],
    }
    (OUT / "genome_phenotype_audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in
                      ("total_genotypes", "unique_phenotypes", "duplicate_ratio",
                       "degenerate_genes", "effective_genes")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
