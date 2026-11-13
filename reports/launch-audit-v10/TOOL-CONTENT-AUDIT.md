# Paperplane v10 — Local 41-tool output-content audit

Two sequential rounds called the same local `server.process` dispatcher used by queued jobs, wrote each available artifact, and opened it with a format-aware parser. The run used synthetic marked files plus the 4,980,286-byte, 69-page repository substitute. It did not call the browser UI or production, use owner credentials, or make a real payment.

Files: [structured evidence](outputs/tool-content-audit.json); synthetic input fixtures are under `inputs/tool-audit-round-1/` and `inputs/tool-audit-round-2/`.

## Round 1

Duration: 49.473 s; operations: 41 in the catalog; attempted: 41.

| Tool | Status | Download / bytes | Opened content evidence | Time |
|---|---|---|---|---:|
| `merge` | completed | merged-PDF.pdf / 4984735 B | pages=71; Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throug | 0.210s |
| `split` | completed | notes-69page_split.pdf / 1373 B | pages=1; Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throug | 0.079s |
| `remove` | completed | notes-69page_remove.pdf / 4980702 B | pages=68; Page 2 of 69 Section 2. Machine learning is the study of computer algorithms that improve automatically throug | 0.198s |
| `rotate` | completed | notes-69page_rotate.pdf / 4981662 B | pages=69; Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throug | 0.233s |
| `organize` | completed | audit-sample_organize.pdf / 2491 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_2 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.023s |
| `scan_pdf` | completed | audit-photo_scan_pdf.pdf / 54384 B | pages=1; verified=True, opened_as_pdf=True, page_count=1 | 0.217s |
| `compress` | completed | notes-69page_compress.pdf / 51967 B | pages=69; Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throug | 0.542s |
| `repair` | completed | notes-69page_repair.pdf / 4967264 B | pages=69; Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throug | 0.249s |
| `ocr` | skipped_unavailable | — / — B | pages=—; Requires Tesseract OCR engine installed | 0.000s |
| `jpg_to_pdf` | completed | audit-photo_jpg_to_pdf.pdf / 148292 B | pages=2;   | 0.063s |
| `word_to_pdf` | completed | audit-office_word_to_pdf.pdf / 31195 B | pages=1; audit_office_word_output | 12.149s |
| `excel_to_pdf` | completed | audit-office_excel_to_pdf.pdf / 2013 B | pages=1; audit_office_excel_output | 0.039s |
| `powerpoint_to_pdf` | completed | audit-office_powerpoint_to_pdf.pdf / 27868 B | pages=1; audit_office_powerpoint_output | 6.459s |
| `html_to_pdf` | blocked_by_ssrf_guard | — / — B | pages=—; Localhost URL was refused by the SSRF guard. | 0.032s |
| `pdf_to_jpg` | completed | audit-sample_pdf_to_jpg.zip / 59415 B | pages=—; verified=True | 0.189s |
| `pdf_to_word` | completed | notes-69page_pdf_to_word.docx / 4960304 B | pages=—;  Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throu | 4.863s |
| `pdf_to_excel` | completed | notes-69page_pdf_to_excel.xlsx / 14474 B | pages=—; verified=True | 3.396s |
| `pdf_to_powerpoint` | completed | notes-69page_pdf_to_powerpoint.pptx / 13809861 B | pages=—; verified=True | 6.554s |
| `pdf_to_pdfa` | completed | notes-69page_pdf_to_pdfa.pdf / 4967498 B | pages=69; Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throug | 0.229s |
| `pdf_to_text` | completed | notes-69page_pdf_to_text.txt / 129553 B | pages=—; --- Page 1 --- Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve autom | 0.076s |
| `pdf_to_markdown` | completed | notes-69page_pdf_to_markdown.md / 130323 B | pages=—; # notes-69page ## Page 1 ## Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that  | 3.392s |
| `edit` | completed | audit-sample_edit.pdf / 2687 B | pages=2; PAPERPLANE_EDITED_TEXT | 0.023s |
| `annotate` | completed | audit-sample_annotate.pdf / 2684 B | pages=2; ANNOTATION_AUDIT_NOTE | 0.021s |
| `crop` | completed | audit-sample_crop.pdf / 2538 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_1 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.020s |
| `redact` | completed | audit-sample_redact.pdf / 1597 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_1 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.024s |
| `watermark` | completed | audit-sample_watermark.pdf / 3018 B | pages=2; AUDIT_WATERMARK | 0.031s |
| `page_numbers` | completed | audit-sample_page_numbers.pdf / 2478 B | pages=2; Page 1 of 2 | 0.026s |
| `protect` | completed | audit-sample_protect.pdf / 3290 B | pages=2; opened_as_pdf=True, encrypted=True, page_count=2, verified=True | 0.076s |
| `unlock` | completed | protect_unlock.pdf / 1441 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_1 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.092s |
| `sign` | completed | audit-sample_sign.pdf / 3209 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_1 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.025s |
| `compare` | completed | audit-sample_compare.txt / 290 B | pages=—; --- audit-sample.pdf +++ audit-sample-changed.pdf @@ -9,5 +9,5 @@ Applicant: [synthetic details redacted] Docu | 0.025s |
| `forms` | completed | audit-form_forms.pdf / 2994 B | pages=1; Paperplane Synthetic Form Audit Audit Applicant audit@example.test Paperplane Output Audit Synthetic form valu | 0.041s |
| `metadata` | completed | audit-sample_metadata.pdf / 3473 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_1 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.018s |
| `ai_chat` | completed | audit-sample_ai_chat.json / 292 B | pages=—; verified=True | 0.023s |
| `ai_extract` | completed | audit-sample_ai_extract.json / 682 B | pages=—; verified=True | 0.015s |
| `summarize` | skipped_unavailable | — / — B | pages=—; Requires the Paperplane AI service to be configured and enabled | 0.000s |
| `translate` | skipped_unavailable | — / — B | pages=—; Requires the Paperplane AI translation service to be configured and enabled | 0.000s |
| `photo_resizer` | completed | audit-photo_photo_resizer.jpg / 35840 B | pages=—; verified=True, dimensions=[350, 450] | 0.032s |
| `mask_aadhaar` | completed | audit-sample_mask_aadhaar.pdf / 2496 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_1 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.024s |
| `grayscale` | completed | notes-69page_grayscale.pdf / 7162310 B | pages=69;   | 9.738s |
| `flatten` | completed | audit-form_flatten.pdf / 1118 B | pages=1; Paperplane Synthetic Form Audit  | 0.027s |

## Round 2

Duration: 42.74 s; operations: 41 in the catalog; attempted: 41.

| Tool | Status | Download / bytes | Opened content evidence | Time |
|---|---|---|---|---:|
| `merge` | completed | merged-PDF.pdf / 4984736 B | pages=71; Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throug | 0.211s |
| `split` | completed | notes-69page_split.pdf / 1373 B | pages=1; Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throug | 0.096s |
| `remove` | completed | notes-69page_remove.pdf / 4980702 B | pages=68; Page 2 of 69 Section 2. Machine learning is the study of computer algorithms that improve automatically throug | 0.219s |
| `rotate` | completed | notes-69page_rotate.pdf / 4981662 B | pages=69; Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throug | 0.229s |
| `organize` | completed | audit-sample_organize.pdf / 2492 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_2 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.028s |
| `scan_pdf` | completed | audit-photo_scan_pdf.pdf / 54384 B | pages=1; verified=True, opened_as_pdf=True, page_count=1 | 0.085s |
| `compress` | completed | notes-69page_compress.pdf / 51967 B | pages=69; Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throug | 0.552s |
| `repair` | completed | notes-69page_repair.pdf / 4967264 B | pages=69; Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throug | 0.246s |
| `ocr` | skipped_unavailable | — / — B | pages=—; Requires Tesseract OCR engine installed | 0.000s |
| `jpg_to_pdf` | completed | audit-photo_jpg_to_pdf.pdf / 148292 B | pages=2;   | 0.070s |
| `word_to_pdf` | completed | audit-office_word_to_pdf.pdf / 31195 B | pages=1; audit_office_word_output | 5.998s |
| `excel_to_pdf` | completed | audit-office_excel_to_pdf.pdf / 2013 B | pages=1; audit_office_excel_output | 0.035s |
| `powerpoint_to_pdf` | completed | audit-office_powerpoint_to_pdf.pdf / 27868 B | pages=1; audit_office_powerpoint_output | 6.548s |
| `html_to_pdf` | blocked_by_ssrf_guard | — / — B | pages=—; Localhost URL was refused by the SSRF guard. | 0.037s |
| `pdf_to_jpg` | completed | audit-sample_pdf_to_jpg.zip / 59525 B | pages=—; verified=True | 0.177s |
| `pdf_to_word` | completed | notes-69page_pdf_to_word.docx / 4960304 B | pages=—;  Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throu | 4.332s |
| `pdf_to_excel` | completed | notes-69page_pdf_to_excel.xlsx / 14475 B | pages=—; verified=True | 3.255s |
| `pdf_to_powerpoint` | completed | notes-69page_pdf_to_powerpoint.pptx / 13809861 B | pages=—; verified=True | 6.554s |
| `pdf_to_pdfa` | completed | notes-69page_pdf_to_pdfa.pdf / 4967498 B | pages=69; Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve automatically throug | 0.239s |
| `pdf_to_text` | completed | notes-69page_pdf_to_text.txt / 129553 B | pages=—; --- Page 1 --- Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that improve autom | 0.079s |
| `pdf_to_markdown` | completed | notes-69page_pdf_to_markdown.md / 130323 B | pages=—; # notes-69page ## Page 1 ## Page 1 of 69 Section 1. Machine learning is the study of computer algorithms that  | 3.487s |
| `edit` | completed | audit-sample_edit.pdf / 2688 B | pages=2; PAPERPLANE_EDITED_TEXT | 0.035s |
| `annotate` | completed | audit-sample_annotate.pdf / 2685 B | pages=2; ANNOTATION_AUDIT_NOTE | 0.020s |
| `crop` | completed | audit-sample_crop.pdf / 2539 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_1 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.022s |
| `redact` | completed | audit-sample_redact.pdf / 1598 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_1 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.021s |
| `watermark` | completed | audit-sample_watermark.pdf / 3018 B | pages=2; AUDIT_WATERMARK | 0.026s |
| `page_numbers` | completed | audit-sample_page_numbers.pdf / 2478 B | pages=2; Page 1 of 2 | 0.022s |
| `protect` | completed | audit-sample_protect.pdf / 3290 B | pages=2; opened_as_pdf=True, encrypted=True, page_count=2, verified=True | 0.053s |
| `unlock` | completed | protect_unlock.pdf / 1442 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_1 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.086s |
| `sign` | completed | audit-sample_sign.pdf / 3210 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_1 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.037s |
| `compare` | completed | audit-sample_compare.txt / 290 B | pages=—; --- audit-sample.pdf +++ audit-sample-changed.pdf @@ -9,5 +9,5 @@ Applicant: [synthetic details redacted] Docu | 0.023s |
| `forms` | completed | audit-form_forms.pdf / 2994 B | pages=1; Paperplane Synthetic Form Audit Audit Applicant audit@example.test Paperplane Output Audit Synthetic form valu | 0.034s |
| `metadata` | completed | audit-sample_metadata.pdf / 3474 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_1 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.019s |
| `ai_chat` | completed | audit-sample_ai_chat.json / 292 B | pages=—; verified=True | 0.012s |
| `ai_extract` | completed | audit-sample_ai_extract.json / 682 B | pages=—; verified=True | 0.014s |
| `summarize` | skipped_unavailable | — / — B | pages=—; Requires the Paperplane AI service to be configured and enabled | 0.000s |
| `translate` | skipped_unavailable | — / — B | pages=—; Requires the Paperplane AI translation service to be configured and enabled | 0.000s |
| `photo_resizer` | completed | audit-photo_photo_resizer.jpg / 35840 B | pages=—; verified=True, dimensions=[350, 450] | 0.050s |
| `mask_aadhaar` | completed | audit-sample_mask_aadhaar.pdf / 2497 B | pages=2; PAPERPLANE_AUDIT_SAMPLE AUDIT_PAGE_1 Applicant: [synthetic details redacted] Document date: 2026-11-07 [synthe | 0.026s |
| `grayscale` | completed | notes-69page_grayscale.pdf / 7162310 B | pages=69;   | 9.733s |
| `flatten` | completed | audit-form_flatten.pdf / 1118 B | pages=1; Paperplane Synthetic Form Audit  | 0.029s |

## Limits

The Translate/Summarize acceptance remains provider-blocked; OCR is unavailable because Tesseract is not installed. The HTML-to-PDF localhost probe was blocked by the SSRF guard as expected. Synthetic output checks do not establish that an operation passes for every file shape. The exact owner form, exact owner file, exact live Drive import, browser UI flows, mobile browser-chrome matrix, and production persistence remain separate acceptance gates.
