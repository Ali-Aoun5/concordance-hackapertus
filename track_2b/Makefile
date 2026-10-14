# Concordance: `make run` must work from a clean checkout. Needs Docker only.
IMAGE ?= concordance
PY    ?= python

.PHONY: run build test warm ingest doctor clean

build:
	docker build -t $(IMAGE) .

# What judges run. Replays the committed model responses (data/cache) with the network
# switched OFF (--network none), which demonstrates air-gapped operation.
# Result: out/review.html (open in a browser), out/summary.md, out/eval_table.md
run: build
	mkdir -p out
	docker run --rm --network none -v "$(CURDIR)/out:/app/out" $(IMAGE) --llm-mode replay demo --max-articles 60 --max-per-type 12
	@echo ""
	@echo "Done. Open out/review.html in your browser."

# Record fresh model responses (needs .env with CSCS_API_KEY, and network).
# They are appended to data/cache so that `make run` can replay them later.
warm: build
	mkdir -p out
	docker run --rm --env-file .env -v "$(CURDIR)/out:/app/out" -v "$(CURDIR)/data/cache:/app/data/cache" $(IMAGE) --llm-mode live demo --max-articles 60 --max-per-type 12

test:
	PYTHONPATH=src $(PY) -m pytest -q

doctor:
	PYTHONPATH=src $(PY) -m concordance doctor

ingest:
	PYTHONPATH=src $(PY) -m concordance ingest --preset --name fedlex_demo

clean:
	rm -rf out
