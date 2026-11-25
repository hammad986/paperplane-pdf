"""Isolated PDF-to-Word converter process for hard cancellation deadlines."""
from __future__ import annotations

from multiprocessing.connection import Connection
from pathlib import Path


def run_pdf_to_word_job_worker(
    result_pipe: Connection,
    source_path: str,
    output_path: str,
    pages: str,
) -> None:
    """Run the converter in a child process and return only a compact outcome."""
    try:
        import converters

        converters.pdf_to_word(Path(source_path), Path(output_path), pages=pages)
        result_pipe.send((True, None, None))
    except BaseException as error:
        try:
            result_pipe.send((False, type(error).__name__, str(error)[:1000]))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        result_pipe.close()
