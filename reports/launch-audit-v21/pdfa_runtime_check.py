import os,re,shutil,subprocess,logging
from pathlib import Path
import fitz
logger=logging.getLogger(__name__)
def _find_srgb_icc_profile() -> Path | None:
    """Resolve the distro ICC package's real sRGB path, including container variants."""
    configured = os.environ.get("PAPERPLANE_SRGB_ICC")
    candidates = [Path(configured)] if configured else [
        Path("/usr/share/color/icc/sRGB.icc"),
        Path("/usr/share/color/icc/colord/sRGB.icc"),
        Path("/usr/share/ghostscript/iccprofiles/default_rgb.icc"),
    ]
    if not configured:
        for root in (Path("/usr/share/color/icc"), Path("/usr/share/ghostscript")):
            if root.is_dir():
                candidates.extend(root.rglob("sRGB.icc"))
                candidates.extend(root.rglob("default_rgb.icc"))
    for candidate in candidates:
        try:
            with candidate.open("rb") as profile:
                header = profile.read(128)
            if len(header) == 128 and header[36:40] == b"acsp":
                return candidate.resolve()
        except OSError:
            continue
    return None

def pdf_to_pdfa(source: Path, output: Path) -> Path:
    """Convert to PDF/A-1b with Ghostscript; never relabel an ordinary PDF as archival."""
    gs = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
    if not gs:
        raise RuntimeError("PDF/A conversion is unavailable because Ghostscript is not installed.")

    icc_profile = _find_srgb_icc_profile()
    if icc_profile is None:
        raise RuntimeError("PDF/A conversion is unavailable because the required sRGB ICC profile is missing.")

    gs_path = Path(gs).resolve()
    gs_roots = [Path("/usr/share/ghostscript")]
    if gs_path.parent.name.lower() == "bin":
        gs_roots.insert(0, gs_path.parent.parent / "share" / "ghostscript")
    definition = next(
        (candidate for root in gs_roots if root.exists() for candidate in root.glob("*/lib/PDFA_def.ps")),
        None,
    )
    if definition is None:
        raise RuntimeError("PDF/A conversion is unavailable because Ghostscript's PDFA_def.ps is missing.")

    import tempfile
    with tempfile.TemporaryDirectory(prefix="paperplane-pdfa-") as temp_dir:
        definition_copy = Path(temp_dir) / "PDFA_def.ps"
        definition_text = definition.read_text(encoding="latin-1")
        # Distro templates put a comment and newline before `def`.
        # Replace only the string operand so both template forms remain valid.
        profile_declaration = re.compile(r"(?m)^[ \t]*/ICCProfile[ \t]*\([^\r\n]*?\)")
        profile_path = icc_profile.resolve().as_posix().replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        replacement = f"/ICCProfile ({profile_path})"
        if not profile_declaration.search(definition_text):
            raise RuntimeError("Ghostscript's PDF/A definition does not declare an ICC profile.")
        definition_copy.write_text(profile_declaration.sub(lambda match: replacement, definition_text, count=1), encoding="latin-1")
        try:
            subprocess.run(
                [gs, "-dPDFA=1", "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE",
                 "-sProcessColorModel=DeviceRGB", "-sColorConversionStrategy=RGB",
                 "-sDEVICE=pdfwrite", "-dPDFACompatibilityPolicy=2",
                 f"--permit-file-read={icc_profile.resolve()}",
                 f"-sOutputFile={output}", str(definition_copy), str(source)],
                check=True, timeout=180, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as error:
            output.unlink(missing_ok=True)
            raise RuntimeError("Ghostscript could not create a conforming PDF/A-1b file.") from error
        except subprocess.TimeoutExpired as error:
            output.unlink(missing_ok=True)
            raise RuntimeError("PDF/A conversion timed out before a validated output was created.") from error

    try:
        with fitz.open(str(output)) as converted:
            metadata = converted.metadata or {}
            xmp = converted.get_xml_metadata() or ""
            pdfa_claimed = bool(re.search(r"pdfaid:part\s*=\s*['\"]1['\"]", xmp))
            catalog = converted.pdf_catalog()
            intent_kind, intent_array = converted.xref_get_key(catalog, "OutputIntents")
            intent_ref = re.search(r"\b(\d+)\s+0\s+R", intent_array or "")
            intent_object = converted.xref_object(int(intent_ref.group(1)), compressed=False) if intent_ref else ""
            if (not converted.page_count or not pdfa_claimed or intent_kind != "array"
                    or "/Type /OutputIntent" not in intent_object
                    or "/DestOutputProfile" not in intent_object):
                raise RuntimeError("The converted PDF is missing required PDF/A identification or output intent.")
            if metadata.get("producer", "").lower().find("ghostscript") < 0:
                logger.warning("PDF/A output was generated but its producer metadata is unexpected")
    except Exception as error:
        output.unlink(missing_ok=True)
        if isinstance(error, RuntimeError):
            raise
        raise RuntimeError("The PDF/A output failed structural conformance checks.") from error
    return output
root=Path('/mnt/c/Users/mdham/Downloads/pdf_splitter/pdf_splitter/reports/launch-audit-v21')
source_pdf=root/'source.pdf'
for i in (1,2):
 out=root/f'pdfa-{i}.pdf'
 try:
  pdf_to_pdfa(source_pdf,out)
  with fitz.open(out) as doc: assert 'PDF/A runtime check' in doc[0].get_text()
  print('PDF/A pass',i,out.stat().st_size)
 except Exception as e:
  print('PDF/A failure',type(e).__name__,str(e),repr(e.__cause__))
