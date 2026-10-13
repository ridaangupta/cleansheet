PY := .venv/bin/python
CLIP ?= synth

.PHONY: setup brands synth clip dataset train detect eval synctest test serve harness

setup:            ## create the Python venv and install JS deps
	python3 -m venv .venv
	$(PY) -m pip install -q -r requirements.txt
	npm install

brands:           ## render fictional sponsor banners into assets/brands/
	$(PY) pipeline/brands.py

synth: brands     ## synthetic clip -> composite -> HLS, end to end
	$(PY) pipeline/synth_clip.py --name synth
	$(MAKE) clip CLIP=synth

clip:             ## composite + package + obscuring textures for an annotated clip: make clip CLIP=<name in footage/>
	$(PY) pipeline/composite.py footage/$(CLIP).mp4
	$(PY) pipeline/sidecar.py media/$(CLIP)/sidecar.json
	pipeline/package_hls.sh media/$(CLIP)/composited.mp4
	$(PY) pipeline/board_textures.py media/$(CLIP)

TRAIN_CLIPS ?= tachira_01 tachira_02 tachira_04
SEEDS ?= 11 23
dataset:          ## extra composites of the training clips with other brand assignments (media/seeds/)
	for c in $(TRAIN_CLIPS); do for s in $(SEEDS); do \
	  $(PY) pipeline/composite.py footage/$$c.mp4 --seed $$s --frame-stride 4 --out media/seeds/$${c}_s$$s || exit 1; \
	done; done

train:            ## train the board detector (needs `make clip` for each clip, then `make dataset`)
	$(PY) pipeline/train.py --train synth $(TRAIN_CLIPS) $(foreach c,$(TRAIN_CLIPS),$(foreach s,$(SEEDS),seeds/$(c)_s$(s))) --val tachira_03

WEIGHTS ?= media/train/runs/boards/weights/best.pt
detect:           ## model sidecar + its textures for a composited clip: make detect CLIP=<name>
	$(PY) pipeline/detect.py $(WEIGHTS) media/$(CLIP)/composited.mp4
	$(PY) pipeline/board_textures.py media/$(CLIP) --sidecar sidecar.model.json

eval:             ## precision/recall vs ground truth, raw detector and tracked sidecar: make eval CLIP=metro_ucv_01
	$(PY) pipeline/eval_detector.py $(WEIGHTS) $(CLIP)
	$(PY) pipeline/eval_detector.py media/$(CLIP)/sidecar.model.json $(CLIP)

synctest:         ## copy of a clip with burned-in frame numbers, for measuring overlay sync on Vega: make synctest CLIP=<name>
	$(PY) pipeline/burn_frames.py media/$(CLIP)/composited.mp4
	pipeline/package_hls.sh media/$(CLIP)/frames_burned.mp4 media/$(CLIP)/hls_tc

test:             ## TS unit tests, typecheck, and tracker accuracy on the synthetic clip
	npx vitest run
	npx tsc --noEmit
	$(PY) pipeline/check_tracking.py footage/synth.mp4 footage/synth.boards.json

serve:            ## mock CDN on :8787 (media/ and assets/)
	$(PY) cloud/mock_server.py

harness:          ## browser sync harness on :5173 (run `make serve` too)
	npm run harness
