# eliciter — read what you've been reading, ask you to write.
# Thin targets over scripts/; the scripts are the interface, this is the shortcut.

.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help ui doctor test digest queue elicit write clean

help:              ## show this help
	@grep -hE '^[a-z-]+:.*?##' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1;36m%-8s\033[0m %s\n", $$1, $$2}'

ui:                ## serve the local UI at http://127.0.0.1:8473
	@bash scripts/ui.sh

doctor:            ## check every source is readable, and read-only
	@bash scripts/doctor.sh

test:              ## run the tests (the read-only gate must never regress)
	@bash scripts/test.sh

digest:            ## sweep arxiv and top up the reading queue
	@bash scripts/arxiv-digest.sh

queue:             ## show what is waiting to be read
	@bash scripts/papers.sh

elicit:            ## render writing prompts from every source
	@bash scripts/elicit.sh

write:             ## list prompts on offer (then: scripts/write.sh <n>)
	@bash scripts/write.sh

clean:             ## remove generated prompts and digests (keeps the queue)
	@rm -rf prompts/*.md digest/*.md && echo "[eliciter] cleaned (state/ kept)"
