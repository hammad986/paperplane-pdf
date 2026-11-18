from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import converters


class _CompletedProcess:
    pid = 43210
    returncode = 0

    def communicate(self, timeout=None):
        return "", ""

    def poll(self):
        return self.returncode


class _TimeoutProcess:
    pid = 43211
    returncode = None

    def communicate(self, timeout=None):
        raise subprocess.TimeoutExpired("soffice", timeout or 120)

    def poll(self):
        return None


def test_libreoffice_export_filters_match_office_document_family():
    assert converters._libreoffice_export_filter(Path("report.docx")) == "writer_pdf_Export"
    assert converters._libreoffice_export_filter(Path("report.xlsx")) == "calc_pdf_Export"
    assert converters._libreoffice_export_filter(Path("slides.pptx")) == "impress_pdf_Export"


def test_libreoffice_uses_explicit_filter_and_isolated_profile(tmp_path):
    source = tmp_path / "report.docx"
    output = tmp_path / "report.pdf"
    source.write_bytes(b"docx")
    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        out_dir = Path(command[command.index("--outdir") + 1])
        (out_dir / "report.pdf").write_bytes(b"%PDF-1.7\n")
        return _CompletedProcess()

    with patch.object(converters, "find_libreoffice_executable", return_value="soffice.exe"), \
         patch.object(converters.subprocess, "Popen", side_effect=fake_popen):
        assert converters._convert_with_libreoffice(source, output) == output

    command = captured["command"]
    assert command[command.index("--convert-to") + 1] == "pdf:writer_pdf_Export"
    assert any(argument.startswith("-env:UserInstallation=file:") for argument in command)
    assert captured["kwargs"]["text"] is True


def test_libreoffice_timeout_terminates_the_process_tree(tmp_path):
    source = tmp_path / "report.xlsx"
    output = tmp_path / "report.pdf"
    source.write_bytes(b"xlsx")

    with patch.object(converters, "find_libreoffice_executable", return_value="soffice.exe"), \
         patch.object(converters.subprocess, "Popen", return_value=_TimeoutProcess()), \
         patch.object(converters, "_terminate_process_tree") as terminate:
        assert converters._convert_with_libreoffice(source, output) is None

    terminate.assert_called_once()
