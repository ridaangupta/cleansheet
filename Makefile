PY := .venv/bin/python
CLIP ?= synth

.PHONY: setup brands synth clip synctest test serve harness

setup:            ## create the Python venv and install JS deps
	python3 -m venv .venv
	$(PY) -m pip install -q -r requirements.txt
	npm install

brands:           ## render fictional sponsor banners into assets/brands/
	$(PY) pipeline/brands.py

synth: brands     ## synthetic clip -> composite -> HLS, end to end
	$(PY) pipeline/synth_clip.py --name synth
	$(MAKE) clip CLIP=synth

clip:             ## composite + package an annotated clip: make clip CLIP=<name in footage/>
	$(PY) pipeline/composite.py footage/$(CLIP).mp4
	$(PY) pipeline/sidecar.py media/$(CLIP)/sidecar.json
	pipeline/package_hls.sh media/$(CLIP)/composited.mp4

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
