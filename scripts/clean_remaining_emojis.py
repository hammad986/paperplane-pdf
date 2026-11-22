#!/usr/bin/env python3
"""
Exhaustive UI sanitizer:
Removes all remaining emojis and replaces them with clean SVG icons, badges, or clear text.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

SVG_CLOSE = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
SVG_LOCK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
SVG_UNLOCK = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>'
SVG_CHECK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>'
SVG_DOC = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>'
SVG_TRASH = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>'

def clean_index_html():
    p = ROOT / "web" / "index.html"
    t = p.read_text(encoding="utf-8")
    
    # Close modal buttons
    t = t.replace(">✕</button>", f">{SVG_CLOSE}</button>")
    t = t.replace('id="resize-orient-portrait">Portrait 📄</button>', 'id="resize-orient-portrait">Portrait</button>')
    t = t.replace('id="resize-orient-landscape">Landscape 📑</button>', 'id="resize-orient-landscape">Landscape</button>')
    t = t.replace('id="insert-orient-portrait">Portrait 📄</button>', 'id="insert-orient-portrait">Portrait</button>')
    t = t.replace('id="insert-orient-landscape">Landscape 📑</button>', 'id="insert-orient-landscape">Landscape</button>')
    t = t.replace('data-action="delete">🗑️ Delete Selected</button>', 'data-action="delete">Delete Selected</button>')
    t = t.replace('id="btn-apply-form-flatten" title="Bake interactive forms into static page vectors">🔒 Flatten Form Fields', 'id="btn-apply-form-flatten" title="Bake interactive forms into static page vectors">Flatten Form Fields')
    t = t.replace('id="btn-run-verify-signatures">Re-Verify Signatures 🔄', 'id="btn-run-verify-signatures">Re-Verify Signatures')
    t = t.replace('Verified ✓', 'Verified')
    
    p.write_text(t, encoding="utf-8")

def clean_app_js():
    p = ROOT / "web" / "assets" / "app.js"
    t = p.read_text(encoding="utf-8")
    
    t = t.replace("<span>🔒</span> Pay ₹250 / month with Cashfree →", "Pay ₹250 / month with Cashfree →")
    t = t.replace("<span>🔒</span> Pay ₹750 / month with Cashfree →", "Pay ₹750 / month with Cashfree →")
    t = t.replace("onclick=\"revokeKey('${k.id}')\" title=\"Revoke API Key\">✕</button>", "onclick=\"revokeKey('${k.id}')\" title=\"Revoke API Key\">" + SVG_CLOSE + "</button>")
    t = t.replace("onclick=\"removeFile(${idx})\" title=\"Remove file\">✕</button>", "onclick=\"removeFile(${idx})\" title=\"Remove file\">" + SVG_CLOSE + "</button>")
    t = t.replace('<span style="font-size: 18px;">⚡</span>', '<span style="font-weight: 700; color: var(--brand-accent);">API</span>')
    t = t.replace('<span class="file-row-icon">📄</span>', f'<span class="file-row-icon">{SVG_DOC}</span>')
    t = t.replace("icon: '🔑',", "icon: '',")
    t = t.replace("{ icon: '📊' }", "{ icon: '' }")
    t = t.replace("<span>⚡</span> Connecting to Cashfree…", "Connecting to Cashfree…")
    t = t.replace("<span>✓</span> Copied!", "Copied!")
    
    p.write_text(t, encoding="utf-8")

def clean_conversion_engine_js():
    p = ROOT / "web" / "assets" / "conversion_engine.js"
    t = p.read_text(encoding="utf-8")
    
    t = t.replace('<span class="format-icon">📊</span>', '<span class="format-icon">XLS</span>')
    t = t.replace('<span class="format-icon">📽️</span>', '<span class="format-icon">PPT</span>')
    t = t.replace('<span class="format-icon">🖼️</span>', '<span class="format-icon">IMG</span>')
    t = t.replace('<span class="format-icon">🎨</span>', '<span class="format-icon">SVG</span>')
    t = t.replace('<span class="format-icon">🌐</span>', '<span class="format-icon">HTML</span>')
    t = t.replace('<span class="format-icon">📄</span>', '<span class="format-icon">DOC</span>')
    t = t.replace('<span class="format-icon">🏛️</span>', '<span class="format-icon">PDFA</span>')
    
    t = t.replace("iconEl.textContent = '📕'", "iconEl.textContent = 'PDF'")
    t = t.replace("iconEl.textContent = '🖼️'", "iconEl.textContent = 'IMG'")
    t = t.replace("iconEl.textContent = '📊'", "iconEl.textContent = 'XLS'")
    t = t.replace("iconEl.textContent = '📽️'", "iconEl.textContent = 'PPT'")
    t = t.replace("iconEl.textContent = '📄'", "iconEl.textContent = 'FILE'")
    
    p.write_text(t, encoding="utf-8")

def clean_editor_js():
    p = ROOT / "web" / "assets" / "editor.js"
    t = p.read_text(encoding="utf-8")
    t = t.replace("<span>⏳</span> Exporting…", "Exporting…")
    p.write_text(t, encoding="utf-8")

def clean_opt_js():
    p = ROOT / "web" / "assets" / "optimization_engine.js"
    t = p.read_text(encoding="utf-8")
    t = t.replace('`💡 ${a.opportunity_analysis}`', '`${a.opportunity_analysis}`')
    t = t.replace('Selected Pages (${this.selectedOcrPages.length}) 🎯', 'Selected Pages (${this.selectedOcrPages.length})')
    t = t.replace('Selected Pages (0) 🎯', 'Selected Pages (0)')
    t = t.replace("'⚠ Corrupted PDF: '", "'Corrupted PDF: '")
    p.write_text(t, encoding="utf-8")

def clean_security_js():
    p = ROOT / "web" / "assets" / "security_forms.js"
    t = p.read_text(encoding="utf-8")
    t = t.replace('<div style="font-size: 32px; margin-bottom: 8px;">🔓</div>', f'<div style="margin-bottom: 8px;">{SVG_UNLOCK}</div>')
    t = t.replace('⚠️ TAMPER WARNING:', 'TAMPER WARNING:')
    t = t.replace("'Active (Potential Risk) ⚠️'", "'Active (Potential Risk)'")
    t = t.replace("'Clean / None ✓'", "'Clean / None'")
    t = t.replace("'Yes ✓'", "'Yes'")
    t = t.replace("'No'", "'No'")
    t = t.replace("'Allowed ✓'", "'Allowed'")
    t = t.replace("'Blocked ✕'", "'Blocked'")
    p.write_text(t, encoding="utf-8")

if __name__ == "__main__":
    clean_index_html()
    clean_app_js()
    clean_conversion_engine_js()
    clean_editor_js()
    clean_opt_js()
    clean_security_js()
    print("Cleaned all remaining emojis.")
