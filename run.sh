#!/usr/bin/env bash
# Mac/Linux equivalent of the Makefile. Usage: ./run.sh train
set -e
PY=${PY:-python}
case "$1" in
  data)    $PY data/generate.py ;;
  train)   $PY src/train.py ;;
  eval)    $PY src/evaluate.py ;;
  up)      docker compose up --build ;;
  demo)    $PY scripts/run_shift_demo.py ;;
  retrain) $PY src/retrain.py ;;
  *)       echo "Usage: ./run.sh data|train|eval|up|demo|retrain" ;;
esac
