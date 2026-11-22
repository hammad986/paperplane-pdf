#!/usr/bin/env python3
"""
PDF Splitter — terminal-based, local-only, page-range extraction.

Usage:
  python pdf_splitter.py input.pdf --start 70 --end 142
  python pdf_splitter.py input.pdf --start 70 --end 142 --output chapter.pdf
    python pdf_splitter.py input.pdf --ranges 1-10,25-30,70-142 --output selected.pdf
    python pdf_splitter.py
  python pdf_splitter.py input.pdf --all
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    print("Missing dependency: pypdf")
    print("Install with: python -m pip install pypdf")
    sys.exit(2)


def parse_range(spec: str, total: int) -> list[int]:
    pages: list[int] = []
    seen = set()
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            a, b = item.split("-", 1)
            start, end = int(a), int(b)
            if start > end:
                raise ValueError(f"Invalid range '{item}': start > end")
            candidates = range(start, end + 1)
        else:
            candidates = [int(item)]
        for page in candidates:
            if page < 1 or page > total:
                raise ValueError(f"Page {page} is outside 1..{total}")
            if page not in seen:
                seen.add(page)
                pages.append(page)
    if not pages:
        raise ValueError("No pages selected.")
    return pages


def default_output(src: Path, pages: list[int]) -> Path:
    if pages == list(range(pages[0], pages[-1] + 1)):
        return src.with_name(f"{src.stem}_pages_{pages[0]}-{pages[-1]}.pdf")
    return src.with_name(f"{src.stem}_selected_pages.pdf")


def split_pdf(src: Path, pages: list[int], out: Path, compress: bool = True) -> None:
    reader = PdfReader(str(src), strict=False)
    if reader.is_encrypted:
        raise RuntimeError("Input PDF is encrypted. Decrypt it first or provide a PDF with an accessible password.")

    writer = PdfWriter()
    for page_num in pages:
        writer.add_page(reader.pages[page_num - 1])

    # Preserve common document metadata where available.
    metadata = dict(reader.metadata or {})
    metadata["/Producer"] = "Local PDF Splitter (pypdf)"
    metadata["/Title"] = f"{src.stem} — selected pages"
    writer.add_metadata(metadata)

    # pypdf does not recompress already-compressed page streams by default;
    # this keeps the operation fast and avoids unnecessary quality loss.
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(out.suffix + ".tmp")
    with temp.open("wb") as f:
        writer.write(f)
    temp.replace(out)


def split_ranges(src: Path, range_specs: list[str], total: int, output_dir: Path) -> list[Path]:
    outputs: list[Path] = []
    for range_spec in range_specs:
        pages = parse_range(range_spec, total)
        if pages != list(range(pages[0], pages[-1] + 1)):
            raise ValueError(f"Range '{range_spec}' must contain one continuous range.")

        out = output_dir / f"{src.stem}_pages_{pages[0]}-{pages[-1]}.pdf"
        split_pdf(src, pages, out)
        outputs.append(out)
    return outputs


def interactive_args() -> list[str]:
    input_path = input("PDF file path: ").strip().strip('"')
    ranges = input(
        "Ranges (default: 1-69,70-142,143-219,220-293,294-378): "
    ).strip() or "1-69,70-142,143-219,220-293,294-378"
    output_dir = input("Output folder (default: same folder as PDF): ").strip().strip('"')

    args = [input_path, "--split-ranges", ranges]
    if output_dir:
        args.extend(["--output-dir", output_dir])
    return args


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local terminal PDF splitter — extract one or more page ranges."
    )
    parser.add_argument("input", type=Path, nargs="?", help="Input PDF")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--start", type=int, help="1-based start page (inclusive)")
    group.add_argument("--ranges", help="Comma-separated ranges/pages, e.g. 1-10,25,70-142")
    group.add_argument("--split-ranges", help="Comma-separated continuous ranges; write one PDF per range")
    group.add_argument("--all", action="store_true", help="Save an exact copy as a new PDF")
    parser.add_argument("--end", type=int, help="1-based end page (inclusive); required with --start")
    parser.add_argument("-o", "--output", type=Path, help="Output PDF path")
    parser.add_argument("--output-dir", type=Path, help="Output folder for --split-ranges")
    args = parser.parse_args(interactive_args() if len(sys.argv) == 1 else None)

    if args.input is None:
        parser.error("input PDF is required")
    if not any((args.start is not None, args.ranges is not None, args.split_ranges is not None, args.all)):
        parser.error("choose --start/--end, --ranges, --split-ranges, or --all")

    if not args.input.exists():
        print(f"ERROR: file not found: {args.input}", file=sys.stderr)
        return 1
    if args.input.suffix.lower() != ".pdf":
        print("ERROR: input must be a .pdf file", file=sys.stderr)
        return 1

    try:
        reader = PdfReader(str(args.input), strict=False)
        total = len(reader.pages)
    except Exception as e:
        print(f"ERROR: cannot read PDF: {e}", file=sys.stderr)
        return 1

    if total == 0:
        print("ERROR: PDF has no pages.", file=sys.stderr)
        return 1

    try:
        if args.all:
            pages = list(range(1, total + 1))
        elif args.split_ranges is not None:
            output_dir = args.output_dir or args.input.parent
            outputs = split_ranges(args.input, args.split_ranges.split(","), total, output_dir)
            for output in outputs:
                print(f"DONE: saved {output} ({output.stat().st_size:,} bytes)")
            return 0
        elif args.ranges is not None:
            pages = parse_range(args.ranges, total)
        else:
            if args.end is None:
                parser.error("--end is required when using --start")
            if args.start < 1 or args.end < 1 or args.start > args.end:
                parser.error("Require 1 <= start <= end")
            if args.end > total:
                parser.error(f"End page {args.end} exceeds PDF page count ({total})")
            pages = list(range(args.start, args.end + 1))

        out = args.output or default_output(args.input, pages)
        if out.resolve() == args.input.resolve():
            print("ERROR: output must be different from input.", file=sys.stderr)
            return 1

        print(f"Input : {args.input}")
        print(f"Pages : {total}")
        print(f"Select: {pages[0]}-{pages[-1]} ({len(pages)} pages)" if len(pages) == pages[-1]-pages[0]+1
              else f"Select: {len(pages)} pages")
        print(f"Output: {out}")

        split_pdf(args.input, pages, out)
        print(f"DONE: saved {out} ({out.stat().st_size:,} bytes)")
        return 0

    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: split failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
