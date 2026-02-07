#!/bin/bash
# Run the full experiment suite for the pivorag paper.
# Executes all pipeline variants × attack combinations × query sets.
set -euo pipefail

CONFIGS_DIR="configs/pipelines"
QUERIES_DIR="data/queries"
RESULTS_DIR="results"

echo "=== PivoRAG Full Experiment Suite ==="
echo "Started: $(date)"

# Step 1: Generate synthetic data (if not exists)
if [ ! -f "data/raw/synthetic_enterprise.json" ]; then
    echo "--- Generating synthetic dataset ---"
    python scripts/make_synth_data.py
fi

# Step 2: Build indexes (if not exists)
echo "--- Building indexes ---"
python scripts/build_indexes.py --data data/raw/synthetic_enterprise.json

# Step 3: Run baselines (no attacks)
echo "--- Running baselines ---"
for config in "$CONFIGS_DIR"/*.yaml; do
    variant=$(basename "$config" .yaml)
    echo "  Running: $variant (benign queries)"
    pivorag run --config "$config" --queries "$QUERIES_DIR/benign.json" \
        --output "$RESULTS_DIR" --label "baseline"
done

# Step 4: Run with attacks
echo "--- Running attack scenarios ---"
for config in "$CONFIGS_DIR"/hybrid_*.yaml; do
    variant=$(basename "$config" .yaml)
    for attack in A1 A2 A3 A4; do
        echo "  Running: $variant + $attack"
        pivorag run --config "$config" --queries "$QUERIES_DIR/adversarial.json" \
            --output "$RESULTS_DIR" --label "attack_${attack}"
    done
done

echo "=== Experiment Suite Complete ==="
echo "Finished: $(date)"
echo "Results in: $RESULTS_DIR/"
