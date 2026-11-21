# Makefile - build, test and clean isa-dnsproxy
# Written with AI assistance (Claude), see the Use of AI section of README.md

PROGRAM = isa-dnsproxy

.PHONY: all NixDevShellName test clean

all:
	printf '#!/bin/sh\nexec python3 "$$(dirname "$$0")/main.py" "$$@"\n' > $(PROGRAM)
	chmod +x $(PROGRAM)

NixDevShellName:
	@echo python

test: all
	python3 -m pytest tests

clean:
	rm -rf __pycache__ tests/__pycache__ .pytest_cache
