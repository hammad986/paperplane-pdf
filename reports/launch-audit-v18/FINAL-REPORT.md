# Paperplane v18 verification report

**Verdict: NOT READY.** This branch is not proven deployment-ready. The 282-item list is not fully implemented or reverified; this report makes the outstanding work explicit rather than presenting local evidence as a release pass.

- Checklist authority: `reports/launch-audit-v18-prompt.txt` (Part 2, v18 single elite list; 282 IDs, excluding unassigned 169, 179, 226, and 238).
- Branch: `launch-audit-v18`; changes remain uncommitted. No push, deploy, or real payment was performed.
- Reproduction/evidence log: `reports/launch-audit-v18/REPRODUCTION-LOG.md`.
- Final full-suite runs after the latest code changes: **465 passed** twice (92.26s and 90.71s), one existing Starlette/httpx deprecation warning each. Logs: `pytest-phase5-final-run1.log`, `pytest-phase5-final-run2.log`.
- Local Chromium: targeted runs cover only the listed fixes/evidence scripts; the required complete A–Z 44-tool content-checked download pass and all 72 do-not-regress IDs were not completed.

## Exact outstanding release gates

1. All IDs marked `OPEN / NOT VERIFIED` below need implementation and/or the per-item controlled reproduction and retest required by v18. The current evidence does not meet the complete checklist or Phase 5 standard.
2. P0 live/owner evidence remains outstanding for provider-backed translation and 69-page summary (IDs 1–2), the exact Drive file (ID 4, whose current shared URL returns a PNG), owner-shaped 60 MiB merge (ID 207), production feedback topology (ID 102), production data survival across redeploy (ID 93), and a real production payment/entitlement check (ID 98; owner-only).
3. ID 101 still needs owner credential rotation and coordinated history rewrite/publish. The purge preparation is isolated at `C:\Users\mdham\Downloads\paperplane-history-purge-v18.git`; the prohibited mirrors were not accessed. Gitleaks CI was not executed locally.
4. ID 220 needs a successful Ghostscript conversion plus veraPDF conformance validation. Docker Desktop's Linux daemon was unavailable, so this proof is missing.
5. The settled `Under 100 KB Govt/SSC` compression default was retained. The extreme-reduction warning and Balanced recommendation exist; owner should decide whether the default remains appropriate for image-heavy PDFs.

## Per-ID disposition

`NOT VERIFIED` means this run has no adequate current-round evidence to close that checklist ID. Items already marked fixed in older rounds are not treated as reverified unless a current-round result is recorded below.

| ID | Disposition | Evidence / remaining check |
|---:|---|---|
| 1 | PARTIAL; LIVE PROVIDER RETEST REQUIRED | Bounded Retry-After-aware backoff is implemented and tested. Live rate limits, fallback provider configuration, quota-status UX, both-language provider quality, and provider-tier suitability remain unresolved. |
| 2 | PARTIAL; LIVE PROVIDER RETEST REQUIRED | Bounded page-labelled chunk summaries and timeouts are in code; controlled 69-page summary passed. The live provider's 69-page behavior remains unproven. |
| 3 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 4 | PARTIAL; INPUT MISMATCH / LIVE RETEST REQUIRED | A different public Drive PDF and corrected W3C direct PDF each imported twice. The exact owner URL returned image/png (35,874 bytes) twice, not the claimed PDF; the supplied W3C URL is 404, corrected URL works. |
| 5 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 6 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 7 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 8 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 9 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 10 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 11 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 12 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 13 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 14 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 15 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 16 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 17 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 18 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 19 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 20 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 21 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 22 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 23 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 24 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 25 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 26 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 27 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 28 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 29 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 30 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 31 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 32 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 33 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 34 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 35 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 36 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 37 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 38 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 39 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 40 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 41 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 42 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 43 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 44 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 45 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 46 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 47 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 48 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 49 | FIXED LOCALLY; LIVE RETEST REQUIRED | Two consecutive edited Studio export downloads were reopened and page order/content checked; see browser_studio_export.py/json. |
| 50 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 51 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 52 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 53 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 54 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 55 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 56 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 57 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 58 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 59 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 60 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 61 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 62 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 63 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 64 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 65 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 66 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 67 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 68 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 69 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 70 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 71 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 72 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 73 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 74 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 75 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 76 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 77 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 78 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 79 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 80 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 81 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 82 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 83 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 84 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 85 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 86 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 87 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 88 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 89 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 90 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 91 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 92 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 93 | OWNER DEPLOYMENT CHECK REQUIRED | Local data-volume preflight exists; a production create-account → redeploy → login proof is not available without deployment. |
| 94 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 95 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 96 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 97 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 98 | OWNER REAL-PAYMENT CHECK REQUIRED | Production simulation is denied in controlled browser checks; no real payment was attempted. Owner must perform the real production payment and verify entitlement. |
| 99 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 100 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 101 | OWNER STEPS REQUIRED | Code fails closed without admin credentials; Gitleaks workflow and isolated history-purge preparation exist. Production credential rotation and coordinated history rewrite/push are owner-controlled; scanner CI did not run locally. |
| 102 | PARTIAL; PRODUCTION TOPOLOGY RETEST REQUIRED | Local feedback submission appeared in the open admin list without manual refresh. Production database write/read topology is unverified. |
| 103 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 104 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 105 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 106 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 107 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 108 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 109 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 110 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 111 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 112 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 113 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 114 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 115 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 116 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 117 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 118 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 119 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 120 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 121 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 122 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 123 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 124 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 125 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 126 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 127 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 128 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 129 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 130 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 131 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 132 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 133 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 134 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 135 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 136 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 137 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 138 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 139 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 140 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 141 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 142 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 143 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 144 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 145 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 146 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 147 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 148 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 149 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 150 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 151 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 152 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 153 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 154 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 155 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 156 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 157 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 158 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 159 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 160 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 161 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 162 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 163 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 164 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 165 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 166 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 167 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 168 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 170 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 171 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 172 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 173 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 174 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 175 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 176 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 177 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 178 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 180 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 181 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 182 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 183 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 184 | FIXED LOCALLY; LIVE NETWORK RETEST REQUIRED | Signed HttpOnly per-browser quota identity; two isolated Chromium profiles on the same IP each received independent quota. Proxy real-IP chain still needs deployment verification. |
| 185 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 186 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 187 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 188 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 189 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 190 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 191 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 192 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 193 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 194 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 195 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 196 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 197 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 198 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 199 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 200 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 201 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 202 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 203 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 204 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 205 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 206 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 207 | PARTIAL; EXACT FIXTURE RETEST REQUIRED | A synthetic 60 MiB/769-page merge completed in repeated local Chromium runs and output was content-checked. The owner's image-heavy fixture was unavailable; validation stall on that structure is not disproved. |
| 208 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 209 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 210 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 211 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 212 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 213 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 214 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 215 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 216 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 217 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 218 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 219 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 220 | PARTIAL; CONFORMANCE TOOLING REQUIRED | Fake metadata relabel fallback removed; conversion now requires Ghostscript/profile and validates markers. No Ghostscript output or veraPDF result could be produced because Docker Desktop's Linux daemon was unavailable. |
| 221 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 222 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 223 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 224 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 225 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 227 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 228 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 229 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 230 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 231 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 232 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 233 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 234 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 235 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 236 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 237 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 239 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 240 | PARTIAL | Typed signer text and visible box covered by regression test; qpdf CLI validation was unavailable. |
| 241 | FIXED LOCALLY | Page n of total output uses writer-owned pages; six-page exact test and browser text-layer verification passed. |
| 242 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 243 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 244 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 245 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 246 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 247 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 248 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 249 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 250 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 251 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 252 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 253 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 254 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 255 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 256 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 257 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 258 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 259 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 260 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 261 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 262 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 263 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 264 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 265 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 266 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 267 | FIXED LOCALLY | Toolbar deletion checked twice in Chromium; 10 pages became 9 with a valid response and no false final-page error. |
| 268 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 269 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 270 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 271 | FIXED LOCALLY; LIVE PROVIDER RETEST REQUIRED | Spanish/Hindi controlled-provider Chromium runs twice; downloaded PDFs rendered and exact Unicode text layer checked. |
| 272 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 273 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 274 | VERIFIED LOCALLY | Chromium twice confirmed one cloud dialog and the same open handler for both entry points; the reported two-dialog behavior was not reproduced on this branch. |
| 275 | FIXED LOCALLY | Mode switch labels and accessible labels now use Local Processing / Server Processing; Chromium verified both labels twice. |
| 276 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 277 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 278 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 279 | FIXED LOCALLY | Ordered citation de-duplication; served Chromium twice confirmed repeated/invalid inputs yield unique Page 3 and Page 4 chips. |
| 280 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 281 | OPEN / NOT VERIFIED | No sufficient current-round implementation and acceptance evidence recorded; reproduce, fix, and verify this item. |
| 282 | FIXED LOCALLY | Compare output uses original filenames rather than internal staging names; regression test passed. |
| 283 | PARTIAL; OWNER DEFAULT RETAINED | Extreme-compression warning and Balanced recommendation added; 27.7 MB image-PDF output reopened, 8 pages rendered nonblank. Detailed visual-quality comparison remains open. |
| 284 | FIXED LOCALLY | Unicode TrueType text layers added for Edit, stamps, signatures, watermark and page numbers; extraction and browser downloads checked. |
| 285 | FIXED LOCALLY | HTML-to-PDF file intake rejects attached HTML with a URL-only explanation; Chromium checked twice. |
| 286 | FIXED LOCALLY | Metadata questions now use verified PDF metadata in normal and streaming chat; Chromium checked both endpoints. |
