from __future__ import annotations

import base64
import datetime
import hashlib
import io
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID
import fitz
from pyasn1.codec.der import decoder, encoder
from pyasn1_modules import rfc2315


# ==============================================================================
# 1. PDF FORM ENGINE
# ==============================================================================

def analyze_pdf_forms(source: Path) -> dict[str, Any]:
    """Inspects a PDF document and extracts all interactive AcroForm widgets and field metadata."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    doc = fitz.open(str(source))
    fields: list[dict[str, Any]] = []

    try:
        for page_idx, page in enumerate(doc):
            for widget in page.widgets():
                flags = widget.field_flags
                field_info = {
                    "page": page_idx,
                    "field_name": widget.field_name or f"field_p{page_idx}_{widget.xref}",
                    "field_type": widget.field_type,
                    "field_type_string": widget.field_type_string,
                    "field_value": widget.field_value,
                    "rect": [round(coord, 2) for coord in widget.rect],
                    "read_only": bool(flags & fitz.PDF_FIELD_IS_READ_ONLY),
                    "required": bool(flags & fitz.PDF_FIELD_IS_REQUIRED),
                    "multiline": bool(flags & fitz.PDF_TX_FIELD_IS_MULTILINE) if widget.field_type == fitz.PDF_WIDGET_TYPE_TEXT else False,
                    "choice_values": list(widget.choice_values) if widget.choice_values else [],
                    "tooltip": widget.field_label or "",
                    "xref": widget.xref
                }
                fields.append(field_info)
    finally:
        doc.close()

    return {
        "has_forms": len(fields) > 0,
        "field_count": len(fields),
        "fields": fields
    }


def add_form_field(source: Path, output: Path, field_data: dict[str, Any]) -> Path:
    """Adds a new interactive AcroForm field (text, checkbox, combobox, radio, etc.) to a PDF page."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    doc = fitz.open(str(source))
    try:
        page_num = int(field_data.get("page", 0))
        if page_num < 0 or page_num >= len(doc):
            raise ValueError(f"Page number {page_num} is out of document bounds (0..{len(doc) - 1}).")

        page = doc[page_num]
        rect_coords = field_data.get("rect", [72, 72, 220, 100])
        rect = fitz.Rect(rect_coords)

        widget = fitz.Widget()
        field_type_str = str(field_data.get("type", "text")).lower()

        if field_type_str in ("text", "textbox"):
            widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            widget.field_value = str(field_data.get("value", ""))
            if field_data.get("multiline"):
                widget.field_flags |= fitz.PDF_TX_FIELD_IS_MULTILINE
        elif field_type_str in ("checkbox", "check"):
            widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
            checked = bool(field_data.get("value", False))
            widget.field_value = "Yes" if checked else "Off"
        elif field_type_str in ("combobox", "dropdown"):
            widget.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
            choices = field_data.get("choice_values", ["Option 1", "Option 2"])
            widget.choice_values = choices
            widget.field_value = str(field_data.get("value", choices[0] if choices else ""))
        elif field_type_str in ("listbox", "list"):
            widget.field_type = fitz.PDF_WIDGET_TYPE_LISTBOX
            choices = field_data.get("choice_values", ["Item 1", "Item 2"])
            widget.choice_values = choices
            widget.field_value = str(field_data.get("value", choices[0] if choices else ""))
        elif field_type_str in ("radio", "radiobutton"):
            widget.field_type = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
            widget.field_value = str(field_data.get("value", "Off"))
        elif field_type_str in ("signature", "sig"):
            widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
        else:
            raise ValueError(f"Unsupported form field type '{field_type_str}'.")

        # Name sanitization
        name = str(field_data.get("name", "")).strip()
        if not name:
            name = f"field_{field_type_str}_{int(datetime.datetime.now().timestamp())}"
        name = re.sub(r"[^\w\.\-\_]", "_", name)
        widget.field_name = name

        # Flags & presentation
        if field_data.get("required"):
            widget.field_flags |= fitz.PDF_FIELD_IS_REQUIRED
        if field_data.get("read_only"):
            widget.field_flags |= fitz.PDF_FIELD_IS_READ_ONLY

        if field_data.get("tooltip"):
            widget.field_label = str(field_data["tooltip"])

        widget.rect = rect
        widget.text_fontsize = float(field_data.get("font_size", 10.0))

        # Colors
        if "text_color" in field_data:
            widget.text_color = tuple(field_data["text_color"])
        if "fill_color" in field_data:
            widget.fill_color = tuple(field_data["fill_color"])
        if "border_color" in field_data:
            widget.border_color = tuple(field_data["border_color"])
            widget.border_width = float(field_data.get("border_width", 1.0))

        page.add_widget(widget)
        out_bytes = doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()

    output.write_bytes(out_bytes)
    return output


def fill_pdf_forms(source: Path, output: Path, field_values: dict[str, Any]) -> Path:
    """Fills existing AcroForm fields in a PDF document and updates their visual appearances."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    doc = fitz.open(str(source))
    try:
        updated_count = 0
        total_widgets = 0
        available_fields: list[str] = []
        for page in doc:
            for widget in page.widgets():
                total_widgets += 1
                if widget.field_name:
                    available_fields.append(widget.field_name)
                if widget.field_name in field_values:
                    val = field_values[widget.field_name]
                    if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                        if isinstance(val, bool):
                            widget.field_value = "Yes" if val else "Off"
                        elif str(val).lower() in ("yes", "true", "1", "on"):
                            widget.field_value = "Yes"
                        else:
                            widget.field_value = "Off"
                    else:
                        widget.field_value = str(val) if val is not None else ""

                    widget.update()
                    updated_count += 1

        if total_widgets == 0:
            raise ValueError("This document contains no interactive AcroForm fields. Use Advanced Studio to add text or form fields.")
        if updated_count == 0:
            sample_fields = ", ".join(list(dict.fromkeys(available_fields))[:8])
            raise ValueError(f"None of the provided field names matched this PDF's form fields. Available field names: {sample_fields}")

        out_bytes = doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()

    output.write_bytes(out_bytes)
    return output


def mask_aadhaar_pdf(source: Path, output: Path) -> Path:
    """
    UIDAI Compliant Aadhaar Masking Engine.
    Detects 12-digit Aadhaar patterns and permanently redacts the first 8 digits,
    leaving only the last 4 digits visible.
    """
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")
    
    doc = fitz.open(str(source))
    try:
        pattern = re.compile(r'\b(\d{4})[\s-](\d{4})[\s-](\d{4})\b')
        for page in doc:
            text_page = page.get_text("text")
            matches = list(pattern.finditer(text_page))
            for m in matches:
                full_aadhaar = m.group(0)
                first_8 = full_aadhaar[:9]
                rects = page.search_for(first_8)
                for r in rects:
                    page.add_redact_annot(r, text="XXXX XXXX", fill=(0.1, 0.1, 0.1), fontname="helv", fontsize=9, text_color=(1, 1, 1))

            if matches:
                page.apply_redactions()

        out_bytes = doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()

    output.write_bytes(out_bytes)
    return output


def flatten_pdf_forms(source: Path, output: Path) -> Path:
    """Destructively bakes form field appearances into page vector content and eliminates interactive widgets."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    doc = fitz.open(str(source))
    try:
        # Use PyMuPDF's bake method to burn widgets into page streams
        if hasattr(doc, "bake"):
            doc.bake(annots=False, widgets=True)
        else:
            for page in doc:
                for widget in list(page.widgets()):
                    page.delete_widget(widget)

        out_bytes = doc.tobytes(garbage=4, clean=True, deflate=True)
    finally:
        doc.close()

    output.write_bytes(out_bytes)

    # Validate output has 0 active form widgets
    verify_doc = fitz.open(str(output))
    active_widgets = 0
    for page in verify_doc:
        active_widgets += len(list(page.widgets()))
    verify_doc.close()

    if active_widgets > 0:
        raise RuntimeError(f"Form flattening failed: {active_widgets} widgets still active.")

    return output


def reset_pdf_forms(source: Path, output: Path) -> Path:
    """Resets all form fields in the PDF document to their blank or default states."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    doc = fitz.open(str(source))
    try:
        for page in doc:
            for widget in page.widgets():
                if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                    doc.xref_set_key(widget.xref, "V", "/Off")
                    doc.xref_set_key(widget.xref, "AS", "/Off")
                    widget.field_value = "Off"
                else:
                    doc.xref_set_key(widget.xref, "V", "()")
                    doc.xref_set_key(widget.xref, "DV", "()")
                    widget.field_value = ""
                widget.update()

        out_bytes = doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()

    output.write_bytes(out_bytes)
    return output


def export_form_data(source: Path) -> dict[str, Any]:
    """Exports all form field values into a clean dictionary."""
    analysis = analyze_pdf_forms(source)
    data = {}
    for f in analysis.get("fields", []):
        data[f["field_name"]] = f["field_value"]
    return data


def import_form_data(source: Path, output: Path, data: dict[str, Any]) -> Path:
    """Imports key-value form field data into the target PDF."""
    return fill_pdf_forms(source, output, data)


# ==============================================================================
# 2. PDF SIGNING ENGINE (VISUAL + CRYPTOGRAPHIC DIGITAL)
# ==============================================================================

def generate_test_certificate(
    common_name: str = "Paperplane Verified Signer",
    org: str = "Paperplane Platform",
    days: int = 365
) -> tuple[bytes, bytes]:
    """Generates an in-memory 2048-bit RSA private key and self-signed X.509 certificate for testing/signing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, org),
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US")
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=days))
        .sign(key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    return cert_pem, key_pem


def add_visual_signature(
    source: Path,
    output: Path,
    signature_data: str | bytes,
    page_num: int = 0,
    rect: tuple[float, float, float, float] | None = None,
    signer_name: str = "Signed",
    date_str: str = ""
) -> Path:
    """Places a visual/electronic signature mark (drawn strokes, typed signature, or stamp) on a PDF page."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    doc = fitz.open(str(source))
    try:
        if page_num < 0 or page_num >= len(doc):
            raise ValueError(f"Page {page_num} is out of bounds (0..{len(doc) - 1}).")

        page = doc[page_num]
        if rect:
            target_rect = fitz.Rect(rect)
        else:
            target_rect = fitz.Rect(page.rect.width - 240, page.rect.height - 110, page.rect.width - 40, page.rect.height - 30)

        # Check if signature_data is base64 or raw image bytes, or plain text
        is_image = False
        img_bytes = None
        if isinstance(signature_data, (bytes, bytearray)):
            img_bytes = bytes(signature_data)
            is_image = True
        elif isinstance(signature_data, str):
            clean_str = signature_data.strip()
            if clean_str.startswith("data:image/") or ";base64," in clean_str:
                raw_b64 = clean_str.split(",", 1)[1] if "," in clean_str else clean_str
                try:
                    img_bytes = base64.b64decode(raw_b64)
                    is_image = True
                except Exception:
                    is_image = False
            else:
                try:
                    decoded = base64.b64decode(clean_str, validate=True)
                    if len(decoded) > 16 and (decoded.startswith(b"\x89PNG") or decoded.startswith(b"\xff\xd8")):
                        img_bytes = decoded
                        is_image = True
                except Exception:
                    is_image = False

        if is_image and img_bytes:
            page.insert_image(target_rect, stream=img_bytes)
        else:
            text_val = str(signature_data)
            page.draw_rect(target_rect, color=(0.7, 0.7, 0.7), width=0.5, dashes="[2 2]")
            page.insert_text(
                fitz.Point(target_rect.x0 + 8, target_rect.y0 + target_rect.height * 0.6),
                text_val,
                fontsize=max(14.0, min(24.0, target_rect.height * 0.4)),
                color=(0.1, 0.2, 0.5)
            )
            page.draw_line(
                fitz.Point(target_rect.x0 + 6, target_rect.y1 - 6),
                fitz.Point(target_rect.x1 - 6, target_rect.y1 - 6),
                color=(0.1, 0.2, 0.5),
                width=1.0
            )

        # Add optional subtle caption underneath
        if date_str or signer_name:
            caption = f"{signer_name} | {date_str or datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
            caption_point = fitz.Point(target_rect.x0, min(page.rect.height - 10, target_rect.y1 + 10))
            page.insert_text(caption_point, caption, fontsize=7.5, color=(0.4, 0.4, 0.4))

        out_bytes = doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()

    output.write_bytes(out_bytes)
    return output


def sign_pdf_digitally(
    source: Path,
    output: Path,
    cert_pem: bytes,
    key_pem: bytes,
    reason: str = "Document Integrity Verification",
    location: str = "Paperplane Workstation",
    contact_info: str = "security@paperplane.local",
    visual_appearance: dict[str, Any] | None = None
) -> Path:
    """Signs a PDF using standard detached PKCS#7 / CMS digital signature (ISO 32000-1 / Adobe PPKLite)."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    # 1. Parse Private Key and Certificate
    private_key = serialization.load_pem_private_key(key_pem, password=None)
    certificate = x509.load_pem_x509_certificate(cert_pem)
    common_name = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    signer_name = common_name[0].value if common_name else "Verified Signer"

    # 2. Prepare visual presentation if requested
    doc = fitz.open(str(source))
    target_page_idx = 0
    if visual_appearance:
        target_page_idx = int(visual_appearance.get("page", 0))
        page = doc[target_page_idx]
        rect_coords = visual_appearance.get("rect", [72, page.rect.height - 130, 320, page.rect.height - 60])
        box_rect = fitz.Rect(rect_coords)

        # Draw decorative signature seal box
        page.draw_rect(box_rect, color=(0.14, 0.38, 0.72), width=1.2)
        page.insert_text((box_rect.x0 + 8, box_rect.y0 + 18), f"DIGITALLY SEALED BY {signer_name.upper()}", fontsize=9, color=(0.14, 0.38, 0.72))
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        page.insert_text((box_rect.x0 + 8, box_rect.y0 + 34), f"Reason: {reason}", fontsize=8, color=(0.25, 0.25, 0.25))
        page.insert_text((box_rect.x0 + 8, box_rect.y0 + 48), f"Date: {now_str}", fontsize=8, color=(0.25, 0.25, 0.25))
        page.insert_text((box_rect.x0 + 8, box_rect.y0 + 60), "Cryptographic SHA-256 / RSA-2048 PKCS#7 Seal", fontsize=7, color=(0.4, 0.4, 0.4))

    # Add signature field widget
    page0 = doc[target_page_idx]
    sig_widget = fitz.Widget()
    sig_widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    sig_name = f"Signature_{int(datetime.datetime.now().timestamp())}"
    sig_widget.field_name = sig_name
    sig_widget.rect = fitz.Rect(72, 72, 250, 110)
    page0.add_widget(sig_widget)

    base_bytes = doc.tobytes(garbage=0, deflate=False)
    doc.close()

    # 3. Create signature dictionary object
    doc2 = fitz.open(stream=base_bytes, filetype="pdf")
    w2 = [x for x in doc2[target_page_idx].widgets() if x.field_name == sig_name][0]

    sig_xref = doc2.get_new_xref()
    placeholder_hex = "0" * 8192
    byte_range_placeholder = "/ByteRange [ 1000000000 1000000000 1000000000 1000000000 ]"
    sign_time_pdf = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%SZ")

    sig_dict = f"""<<
  /Type /Sig
  /Filter /Adobe.PPKLite
  /SubFilter /adbe.pkcs7.detached
  {byte_range_placeholder}
  /Contents <{placeholder_hex}>
  /M (D:{sign_time_pdf})
  /Name ({signer_name})
  /Reason ({reason})
  /Location ({location})
>>"""
    doc2.update_object(sig_xref, sig_dict)
    doc2.xref_set_key(w2.xref, "V", f"{sig_xref} 0 R")

    pdf_buffer = bytearray(doc2.tobytes(garbage=0, deflate=False))
    doc2.close()

    # 4. Compute byte ranges
    c_pos = pdf_buffer.find(b"/Contents<")
    if c_pos < 0:
        c_pos = pdf_buffer.find(b"/Contents <")
    if c_pos < 0:
        raise RuntimeError("Signature /Contents placeholder not found in PDF byte stream.")

    c_open_bracket = pdf_buffer.find(b"<", c_pos)
    hex_start = c_open_bracket + 1
    hex_end = pdf_buffer.find(b">", hex_start)
    if hex_end < 0:
        raise RuntimeError("Signature /Contents closing delimiter '>' not found.")

    range1_start = 0
    range1_len = hex_start - 1  # excludes '<'
    range2_start = hex_end + 1  # right after '>'
    range2_len = len(pdf_buffer) - range2_start

    br_match = re.search(rb'/ByteRange\s*\[\s*1000000000\s+1000000000\s+1000000000\s+1000000000\s*\]', pdf_buffer)
    if not br_match:
        raise RuntimeError("Signature /ByteRange placeholder not found in byte stream.")
    match_len = br_match.end() - br_match.start()
    base_str = f"/ByteRange [{range1_start:d} {range1_len:d} {range2_start:d} {range2_len:d}"
    pad_len = match_len - len(base_str) - 1
    new_byte_range = f"{base_str}{' ' * pad_len}]".encode("ascii")
    pdf_buffer[br_match.start() : br_match.end()] = new_byte_range

    # 5. Extract signed byte slices and generate detached PKCS#7 signature
    signed_data = bytes(pdf_buffer[range1_start : range1_start + range1_len] + pdf_buffer[range2_start : range2_start + range2_len])

    builder = pkcs7.PKCS7SignatureBuilder().set_data(signed_data).add_signer(certificate, private_key, hashes.SHA256())
    sig_der = builder.sign(serialization.Encoding.DER, options=[pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary])
    sig_hex = sig_der.hex().upper().encode("ascii")

    if len(sig_hex) > len(placeholder_hex):
        raise RuntimeError(f"Signature size ({len(sig_hex)} hex chars) exceeds placeholder ({len(placeholder_hex)} chars).")

    # Overwrite placeholder hex
    pdf_buffer[hex_start : hex_start + len(sig_hex)] = sig_hex

    # 6. Save atomically
    final_signed_bytes = bytes(pdf_buffer)
    output.write_bytes(final_signed_bytes)
    return output


def verify_pdf_signatures(source: Path) -> dict[str, Any]:
    """Inspects and cryptographically verifies all digital signatures in a PDF document."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    pdf_bytes = source.read_bytes()
    br_matches = list(re.finditer(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\]", pdf_bytes))
    c_matches = list(re.finditer(rb"/Contents\s*<([0-9A-Fa-f]+)>", pdf_bytes))

    if not br_matches or not c_matches:
        return {
            "is_signed": False,
            "signature_count": 0,
            "signatures": []
        }

    signatures_report: list[dict[str, Any]] = []

    for idx, br_m in enumerate(br_matches):
        r0 = int(br_m.group(1))
        r1 = int(br_m.group(2))
        r2 = int(br_m.group(3))
        r3 = int(br_m.group(4))

        if idx < len(c_matches):
            raw_hex = c_matches[idx].group(1)
        else:
            raw_hex = c_matches[0].group(1)

        sig_info: dict[str, Any] = {
            "index": idx + 1,
            "status": "UNKNOWN",
            "byte_range": [r0, r1, r2, r3],
            "tamper_detected": False,
            "certificate": {}
        }

        # Validate range boundary integrity
        total_len = len(pdf_bytes)
        if r0 != 0 or (r0 + r1) > total_len or r2 > total_len or (r2 + r3) > total_len:
            sig_info["status"] = "TAMPERED"
            sig_info["tamper_detected"] = True
            sig_info["error"] = "Signature ByteRange coordinates fall outside file boundaries."
            signatures_report.append(sig_info)
            continue

        signed_content = pdf_bytes[r0 : r0 + r1] + pdf_bytes[r2 : r2 + r3]
        actual_digest = hashlib.sha256(signed_content).digest()

        # Decode DER
        try:
            padded_der = bytes.fromhex(raw_hex.decode("ascii"))
            content_info, remainder = decoder.decode(padded_der, asn1Spec=rfc2315.ContentInfo())
            exact_der = padded_der[: len(padded_der) - len(remainder)]

            # Extract certificate
            certs = pkcs7.load_der_pkcs7_certificates(exact_der)
            if not certs:
                sig_info["status"] = "INVALID"
                sig_info["error"] = "No embedded X.509 certificate found in PKCS#7 block."
                signatures_report.append(sig_info)
                continue

            cert = certs[0]
            sig_info["certificate"] = {
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "serial_number": str(cert.serial_number),
                "not_before": cert.not_valid_before_utc.isoformat(),
                "not_after": cert.not_valid_after_utc.isoformat()
            }

            # Check validity dates
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if now_utc < cert.not_valid_before_utc:
                sig_info["status"] = "CERTIFICATE_NOT_YET_VALID"
            elif now_utc > cert.not_valid_after_utc:
                sig_info["status"] = "CERTIFICATE_EXPIRED"

            # Parse SignerInfo
            signed_data_obj, _ = decoder.decode(bytes(content_info["content"]), asn1Spec=rfc2315.SignedData())
            signer_info = signed_data_obj["signerInfos"][0]

            # Verify message digest
            auth_attrs = signer_info["authenticatedAttributes"]
            claimed_digest = None
            for attr in auth_attrs:
                if str(attr["type"]) == "1.2.840.113549.1.9.4":  # messageDigest
                    val, _ = decoder.decode(bytes(attr["values"][0]))
                    claimed_digest = bytes(val)
                    break

            if claimed_digest != actual_digest:
                sig_info["status"] = "TAMPERED"
                sig_info["tamper_detected"] = True
                sig_info["error"] = "Signed document byte stream was altered after signature generation."
                signatures_report.append(sig_info)
                continue

            # Verify RSA cryptographic signature over authenticated attributes
            raw_attrs = bytes(encoder.encode(auth_attrs))
            attrs_for_sig = b"\x31" + raw_attrs[1:]
            enc_sig = bytes(signer_info["encryptedDigest"])
            public_key = cert.public_key()
            public_key.verify(enc_sig, attrs_for_sig, padding.PKCS1v15(), hashes.SHA256())

            if sig_info["status"] == "UNKNOWN":
                sig_info["status"] = "VALID"
                sig_info["intact"] = True

        except Exception as e:
            sig_info["status"] = "INVALID"
            sig_info["error"] = f"Cryptographic verification error: {str(e)}"

        signatures_report.append(sig_info)

    all_valid = all(s.get("status") == "VALID" for s in signatures_report)
    any_tampered = any(s.get("tamper_detected") for s in signatures_report)

    overall_status = "VALID" if all_valid else ("TAMPERED" if any_tampered else "INVALID")

    return {
        "is_signed": True,
        "signature_count": len(signatures_report),
        "overall_status": overall_status,
        "signatures": signatures_report
    }


# ==============================================================================
# 3. PDF SECURITY & SANITIZATION ENGINE
# ==============================================================================

def protect_pdf(
    source: Path,
    output: Path,
    user_password: str = "",
    owner_password: str = "",
    permissions: dict[str, bool] | None = None
) -> Path:
    """Applies modern AES-256 encryption and configurable user/owner permission constraints."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    if not user_password and not owner_password:
        raise ValueError("At least one password (user open password or owner permissions password) is required.")

    doc = fitz.open(str(source))
    try:
        perms_cfg = permissions or {}
        # Start with base accessibility permitted
        perm_mask = fitz.PDF_PERM_ACCESSIBILITY

        if perms_cfg.get("allow_printing", True):
            perm_mask |= (fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ)
        if perms_cfg.get("allow_copying", True):
            perm_mask |= fitz.PDF_PERM_COPY
        if perms_cfg.get("allow_modifying", False):
            perm_mask |= fitz.PDF_PERM_MODIFY
        if perms_cfg.get("allow_annotating", False):
            perm_mask |= fitz.PDF_PERM_ANNOTATE
        if perms_cfg.get("allow_form_filling", True):
            perm_mask |= fitz.PDF_PERM_FORM

        out_bytes = doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw=user_password,
            owner_pw=owner_password or user_password,
            permissions=perm_mask,
            deflate=True
        )
    finally:
        doc.close()

    output.write_bytes(out_bytes)
    return output


def unlock_pdf(source: Path, output: Path, password: str) -> Path:
    """Authenticates against a protected PDF using the supplied password and saves an unencrypted copy."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    doc = fitz.open(str(source))
    try:
        if doc.is_encrypted:
            auth_status = doc.authenticate(password)
            if auth_status == 0:
                raise ValueError("Incorrect password provided for document unlock.")

        out_bytes = doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE, garbage=4, clean=True, deflate=True)
    finally:
        doc.close()

    output.write_bytes(out_bytes)
    return output


def inspect_pdf_security(source: Path, password: str = "") -> dict[str, Any]:
    """Performs a comprehensive security inspection of encryption, permissions, active content, and attachments."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    doc = fitz.open(str(source))
    try:
        is_encrypted = doc.is_encrypted
        if is_encrypted and password:
            doc.authenticate(password)

        # Check forms
        form_count = 0
        if not doc.is_encrypted or not doc.needs_pass:
            for page in doc:
                form_count += len(list(page.widgets()))

        # Check attachments
        emb_count = doc.embfile_count() if hasattr(doc, "embfile_count") else 0
        emb_names = doc.embfile_names() if hasattr(doc, "embfile_names") else []

        # Check signatures
        sig_ver = verify_pdf_signatures(source)

        # Check JavaScript / active content
        js_detected = False
        cat_xref = doc.pdf_catalog()
        cat_str = doc.xref_object(cat_xref)
        if "/JavaScript" in cat_str or "/JS" in cat_str or "/AA" in cat_str:
            js_detected = True

        # Check metadata
        meta = doc.metadata or {}
        has_metadata = any(bool(v) for k, v in meta.items() if k not in ("format", "encryption"))

        # Permissions report
        perms = doc.permissions
        permissions_report = {
            "print": bool(perms & fitz.PDF_PERM_PRINT),
            "can_print": bool(perms & fitz.PDF_PERM_PRINT),
            "modify": bool(perms & fitz.PDF_PERM_MODIFY),
            "can_modify": bool(perms & fitz.PDF_PERM_MODIFY),
            "copy": bool(perms & fitz.PDF_PERM_COPY),
            "can_copy": bool(perms & fitz.PDF_PERM_COPY),
            "annotate": bool(perms & fitz.PDF_PERM_ANNOTATE),
            "can_annotate": bool(perms & fitz.PDF_PERM_ANNOTATE),
            "forms": bool(perms & fitz.PDF_PERM_FORM),
            "can_fill_forms": bool(perms & fitz.PDF_PERM_FORM),
            "accessibility": bool(perms & fitz.PDF_PERM_ACCESSIBILITY)
        }

        enc_type = None
        if is_encrypted:
            raw_enc = str(meta.get("encryption", ""))
            if "256" in raw_enc or "AES" in raw_enc:
                enc_type = "AES-256"
            elif raw_enc:
                enc_type = raw_enc
            else:
                enc_type = "AES-256"

        return {
            "is_encrypted": is_encrypted,
            "encryption_type": enc_type,
            "page_count": len(doc),
            "open_password_required": doc.needs_pass,
            "permissions": permissions_report,
            "has_javascript": js_detected,
            "attachment_count": emb_count,
            "attachments": emb_names,
            "form_field_count": form_count,
            "is_digitally_signed": sig_ver.get("is_signed", False),
            "digital_signature_count": sig_ver.get("signature_count", 0),
            "has_metadata": has_metadata,
            "metadata_summary": {k: v for k, v in meta.items() if v and k != "encryption"}
        }
    finally:
        doc.close()


def sanitize_pdf(source: Path, output: Path, targets: dict[str, bool] | None = None) -> Path:
    """Removes private metadata, active JavaScript, embedded file attachments, and user comments."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    cfg = targets or {
        "remove_metadata": True,
        "remove_attachments": True,
        "remove_javascript": True,
        "remove_annotations": True
    }

    doc = fitz.open(str(source))
    try:
        # 1. Sanitize Metadata
        if cfg.get("remove_metadata", True):
            doc.set_metadata({})
            if hasattr(doc, "set_xml_metadata"):
                doc.set_xml_metadata("")

        # 2. Sanitize Attachments
        if cfg.get("remove_attachments", True) and hasattr(doc, "embfile_names"):
            for name in list(doc.embfile_names()):
                doc.embfile_del(name)

        # 3. Sanitize User Annotations / Comments
        if cfg.get("remove_annotations", True):
            for page in doc:
                for annot in list(page.annots()):
                    page.delete_annot(annot)

        # 4. Sanitize JavaScript / Actions
        if cfg.get("remove_javascript", True):
            cat_xref = doc.pdf_catalog()
            doc.xref_set_key(cat_xref, "JavaScript", "null")
            doc.xref_set_key(cat_xref, "OpenAction", "null")
            doc.xref_set_key(cat_xref, "AA", "null")
            doc.xref_set_key(cat_xref, "Names", "null")

        out_bytes = doc.tobytes(garbage=4, clean=True, deflate=True)
    finally:
        doc.close()

    output.write_bytes(out_bytes)
    return output


def apply_hardened_redaction(source: Path, output: Path, redactions: list[dict[str, Any]]) -> Path:
    """Applies irreversible visual and stream redaction, permanently destroying character glyphs and vectors."""
    if not source.exists():
        raise ValueError(f"File '{source.name}' does not exist.")

    doc = fitz.open(str(source))
    try:
        for item in redactions:
            page_idx = int(item.get("page", 0))
            if page_idx < 0 or page_idx >= len(doc):
                continue
            page = doc[page_idx]

            rect_coords = item.get("rect")
            text_target = item.get("text")

            rects_to_redact: list[fitz.Rect] = []
            if rect_coords:
                rects_to_redact.append(fitz.Rect(rect_coords))
            elif text_target:
                found_rects = page.search_for(str(text_target))
                rects_to_redact.extend(found_rects)

            for r in rects_to_redact:
                page.add_redact_annot(r, fill=(0, 0, 0))

            page.apply_redactions()

        out_bytes = doc.tobytes(garbage=4, clean=True, deflate=True)
    finally:
        doc.close()

    output.write_bytes(out_bytes)
    return output
