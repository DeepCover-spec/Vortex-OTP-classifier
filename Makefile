# Targets: data train eval up demo retrain
# No make on Windows? Use run.ps1 with the same target names.
PY ?= python

.PHONY: data train eval up demo retrain

data:    # P2 extends this to download the UCI ham file
	$(PY) data/generate.py

train:
	$(PY) src/train.py

eval:
	$(PY) src/evaluate.py

up:
	docker compose up --build

demo:
	$(PY) scripts/run_shift_demo.py

retrain:
	$(PY) src/retrain.py
