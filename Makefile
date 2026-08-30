# eliciter — read what you've been reading, ask you to write.
# Thin targets over scripts/; the scripts are the interface, this is the shortcut.

.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help ui ui-up ui-down ui-status ui-restart doctor test sweep queue gather prompts write clean

help:              ## show this help
	@grep -hE '^[a-z-]+:.*?##' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1;36m%-12s\033[0m %s\n", $$1, $$2}'

ui:                ## serve the UI in the foreground at http://127.0.0.1:8473 (Ctrl-C to stop)
	@bash scripts/ui.sh run

ui-up:             ## start the UI detached in the background
	@bash scripts/ui.sh start

ui-down:           ## stop the background UI started with ui-up
	@bash scripts/ui.sh stop

ui-status:         ## check whether the background UI is running
	@bash scripts/ui.sh status

ui-restart: ui-down ui-up ## restart the background UI

doctor:            ## check every source is readable, and read-only
	@bash scripts/doctor.sh

test:              ## run the tests (the read-only gate must never regress)
	@bash scripts/test.sh

sweep:             ## sweep arxiv into state/candidates.json (then ask a session to pick)
	@bash scripts/sweep.sh fetch

queue:             ## show what is waiting to be read
	@bash scripts/papers.sh

gather:            ## read every source into state/material.json (the skill does this for you)
	@bash scripts/gather.sh

prompts:           ## validate + render the prompts a session wrote
	@bash scripts/prompts.sh render

write:             ## list prompts on offer (then: scripts/write.sh <n>)
	@bash scripts/write.sh

clean:             ## remove generated prompts and digests (keeps the queue)
	@rm -rf prompts/*.md digest/*.md && echo "[eliciter] cleaned (state/ kept)"
