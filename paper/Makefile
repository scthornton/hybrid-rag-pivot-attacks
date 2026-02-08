# Build the paper PDF
# Usage: make        (builds main.pdf)
#        make clean  (removes build artifacts)
#        make watch  (continuous rebuild on file changes, requires latexmk)

MAIN = main

.PHONY: all clean watch

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex references.bib figures/*.png
	pdflatex $(MAIN)
	bibtex $(MAIN)
	pdflatex $(MAIN)
	pdflatex $(MAIN)

watch:
	latexmk -pdf -pvc $(MAIN)

clean:
	rm -f $(MAIN).pdf $(MAIN).aux $(MAIN).bbl $(MAIN).blg \
	      $(MAIN).log $(MAIN).out $(MAIN).toc $(MAIN).fls \
	      $(MAIN).fdb_latexmk $(MAIN).synctex.gz
