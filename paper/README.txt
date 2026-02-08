Retrieval Pivot Attacks in Hybrid RAG
=====================================

Building the PDF
----------------

Option 1: Overleaf (easiest)
  - Upload this entire zip to Overleaf (New Project > Upload Project)
  - Overleaf will detect main.tex and build automatically

Option 2: Local build with Make
  - Requires: pdflatex, bibtex (from TeX Live or MacTeX)
  - Run: make

Option 3: Local build manually
  - pdflatex main
  - bibtex main
  - pdflatex main
  - pdflatex main

Option 4: latexmk (continuous rebuild)
  - Run: latexmk -pdf main
  - Or:  make watch

Requirements
------------
  - LaTeX distribution with IEEEtran class (included in TeX Live, MacTeX)
  - Packages: amsmath, graphicx, hyperref, booktabs, algorithm,
    algpseudocode, listings, multirow, subcaption, balance

Contents
--------
  main.tex          - Paper source (1007 lines, ~12 pages)
  references.bib    - Bibliography (44 entries)
  figures/          - 4 publication-quality plots (300 dpi PNG)
    rpr_comparison.png      - RPR across pipeline variants
    context_size.png        - Context size under progressive defenses
    defense_heatmap.png     - Defense effectiveness heatmap
    leakage_distribution.png - Leakage distribution
  Makefile          - Build automation
  README.txt        - This file
