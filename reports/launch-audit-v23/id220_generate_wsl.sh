#!/bin/sh
set -eu
src=/mnt/c/Users/mdham/Downloads/pdf_splitter/pdf_splitter/reports/launch-audit-v23/id220-clean-source.pdf
out=/mnt/c/Users/mdham/Downloads/pdf_splitter/pdf_splitter/reports/launch-audit-v23/id220-wsl-gs.pdf
profile=/usr/share/color/icc/sRGB.icc
def=/tmp/paperplane-pdfa-def.ps
sed "s|/ICCProfile (srgb.icc)|/ICCProfile ($profile)|" /usr/share/ghostscript/10.02.1/lib/PDFA_def.ps > "$def"
gs -dPDFA=1 -dBATCH -dNOPAUSE -dNOOUTERSAVE -sProcessColorModel=DeviceRGB -sColorConversionStrategy=RGB -sDEVICE=pdfwrite -dPDFACompatibilityPolicy=2 "--permit-file-read=$profile" -sOutputFile="$out" "$def" "$src"
