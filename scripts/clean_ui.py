#!/usr/bin/env python3
"""
Sanitizes UI components to strictly adhere to:
1. No emojis in UI (replaced by SVG or text)
2. No em-dashes (— replaced by - or :)
3. Removal of unverified claims like 'Zero-Knowledge'
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Replaces em dashes in text/comments
def replace_em_dashes(text: str) -> str:
    return text.replace("—", " - ")

# SVG Icon helpers
SVG_CHECK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>'
SVG_LOCK = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
SVG_KEY = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="7.5" cy="15.5" r="4.5"/><path d="M21 2l-9.6 9.6M15.5 7.5l2.5 2.5"/></svg>'
SVG_DOC = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>'
SVG_USER = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
SVG_GEAR = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>'
SVG_SHIELD = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
SVG_WARN = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
SVG_SEARCH = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
SVG_TRASH = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>'
SVG_CROP = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>'
SVG_SUN = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
SVG_MOON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'

def clean_index_html():
    p = ROOT / "web" / "index.html"
    text = p.read_text(encoding="utf-8")
    
    # Em dashes
    text = replace_em_dashes(text)
    
    # Remove unsupported "Zero-Knowledge" claims
    text = text.replace("Zero-Knowledge Architecture", "Ephemeral Local Processing")
    text = text.replace("Zero-Knowledge Storage", "Ephemeral Encrypted Storage")
    
    # Specific emoji replacements in markup
    replacements = [
        ("<span>⚡</span> Interactive Swagger OpenAPI ↗", '<span>API</span> Swagger OpenAPI ↗'),
        ("<span>📖</span> ReDoc Specifications ↗", '<span>Doc</span> ReDoc Specifications ↗'),
        ("<span>⚿</span> Manage API Keys →", f'<span>{SVG_KEY}</span> Manage API Keys →'),
        ("<span>📋</span> Copy Snippet", '<span>Copy</span> Copy Snippet'),
        ("<span>🔍</span>", f'<span>{SVG_SEARCH}</span>'),
        ('<span style="font-size: 22px;">⚙️</span>', f'<span class="header-icon-svg">{SVG_GEAR}</span>'),
        ("<span>👤</span> Account", f'<span>{SVG_USER}</span> Account'),
        ("<span>🌓</span> Appearance", f'<span>Theme</span> Appearance'),
        ("<span>💎</span> Billing & Plans", f'<span>Tier</span> Billing & Plans'),
        ("<span>⚿</span> Developer API", f'<span>{SVG_KEY}</span> Developer API'),
        ("<span>🚪</span> Sign Out of Paperplane", '<span>Sign Out</span> Sign Out of Paperplane'),
        ('<span class="theme-swatch dark-swatch">🌙</span>', f'<span class="theme-swatch dark-swatch">{SVG_MOON}</span>'),
        ('<span class="theme-swatch light-swatch">☀️</span>', f'<span class="theme-swatch light-swatch">{SVG_SUN}</span>'),
        ("<span>⚡ Operations Today</span>", "<span>Operations Today</span>"),
        ('<span>👑</span> View Pricing Tiers & Upgrade →', '<span>Upgrade</span> View Pricing Tiers & Upgrade →'),
        ('<div class="api-info-icon">💡</div>', '<div class="api-info-icon">Info</div>'),
        ('<span>📖</span> Open Dedicated REST API Documentation Workspace →', '<span>API</span> Open Dedicated REST API Documentation Workspace →'),
        ('<span style="font-size: 28px;">👑</span>', '<span style="font-size: 16px; font-weight: 700; color: var(--brand-accent);">PRO</span>'),
        ('<span style="font-size: 28px;">⚿</span>', f'<span style="font-size: 24px;">{SVG_KEY}</span>'),
        ('<span>✓</span>', f'<span>{SVG_CHECK}</span>'),
        ('<span>🔒</span> Pay ₹250 / month with Cashfree →', f'<span>{SVG_LOCK}</span> Pay ₹250 / month with Cashfree →'),
        ('⚡ Instant Demo Upgrade', 'Instant Local Upgrade'),
        ('<span>🔒</span> Pay ₹750 / month with Cashfree →', f'<span>{SVG_LOCK}</span> Pay ₹750 / month with Cashfree →'),
        ('<span>🔒 Secure Cashfree checkout. Cancel anytime in 1 click.', f'<span>{SVG_LOCK}</span> Encrypted Cashfree checkout. Instant activation after verification.'),
        ('<div class="error-dialog-icon" id="error-dialog-icon">⚠️</div>', f'<div class="error-dialog-icon" id="error-dialog-icon">{SVG_WARN}</div>'),
        ('<span>🔤</span>', '<span>Text</span>'),
        ('<span style="font-size: 24px;">✍️</span>', f'<span style="font-size: 20px;">Draw</span>'),
        ('<span style="font-size: 24px;">📑</span>', f'<span style="font-size: 20px;">{SVG_DOC}</span>'),
        ('<span style="font-size: 24px;">📐</span>', f'<span style="font-size: 20px;">Resize</span>'),
        ('<span style="font-size: 24px;">✂️</span>', f'<span style="font-size: 20px;">{SVG_CROP}</span>'),
        ('<span>📦 Multiple split files', '<span>Multiple split files'),
        ('<span style="font-size: 24px;">➕</span>', '<span style="font-size: 20px;">+</span>'),
        ('<span style="font-size: 24px;">📥</span>', '<span style="font-size: 20px;">Import</span>'),
        ('<div style="font-size: 28px; margin-bottom: 6px;">📂</div>', f'<div style="font-size: 24px; margin-bottom: 6px;">{SVG_DOC}</div>'),
        ('<span style="font-size: 24px;">⚡</span>', '<span style="font-size: 20px;">Optimize</span>'),
        ('<span style="font-size: 24px;">🔍</span>', f'<span style="font-size: 20px;">{SVG_SEARCH}</span>'),
        ('<span>📸</span>', '<span>Scan</span>'),
        ('Scanned Only 📸', 'Scanned Only'),
        ('All Pages 📑', 'All Pages'),
        ('Selected Pages 🎯', 'Selected Pages'),
        ('<span style="font-size: 24px;">🩹</span>', '<span style="font-size: 20px;">Repair</span>'),
        ('<h3 style="margin: 0; font-size: 16px;">🔄 Document Conversion Center</h3>', '<h3 style="margin: 0; font-size: 16px;">Document Conversion Center</h3>'),
        ('<span style="font-size: 20px;" id="convert-source-icon">📄</span>', f'<span style="font-size: 20px;" id="convert-source-icon">{SVG_DOC}</span>'),
        ('<span class="format-icon">📝</span>', '<span class="format-icon">DOC</span>'),
        ('<span class="format-icon">📊</span>', '<span class="format-icon">XLS</span>'),
        ('<span class="format-icon">📽️</span>', '<span class="format-icon">PPT</span>'),
        ('<span class="format-icon">🖼️</span>', '<span class="format-icon">IMG</span>'),
        ('<span class="format-icon">🎨</span>', '<span class="format-icon">SVG</span>'),
        ('<span class="format-icon">🌐</span>', '<span class="format-icon">HTML</span>'),
        ('<span class="format-icon">📋</span>', '<span class="format-icon">TXT</span>'),
        ('<span class="format-icon">📄</span>', '<span class="format-icon">MD</span>'),
        ('<span class="format-icon">🏛️</span>', '<span class="format-icon">PDF/A</span>'),
        ('📋 Duplicate Page', 'Duplicate Page'),
        ('📤 Extract to New PDF', 'Extract to New PDF'),
        ('✂️ Crop Page...', 'Crop Page...'),
        ('📐 Resize Page...', 'Resize Page...'),
        ('➕ Insert Blank Page Before', 'Insert Blank Page Before'),
        ('➕ Insert Blank Page After', 'Insert Blank Page After'),
        ('📥 Import Pages from PDF...', 'Import Pages from PDF...'),
        ('🗑️ Delete Selected', 'Delete Selected'),
        ('<span style="font-size: 24px;">📝</span>', '<span style="font-size: 20px;">Form</span>'),
        ('<span style="font-size: 24px;">🔏</span>', f'<span style="font-size: 20px;">{SVG_LOCK}</span>'),
        ('🔐 Signs document', f'{SVG_SHIELD} Signs document'),
        ('<span style="font-size: 24px;">🛡️</span>', f'<span style="font-size: 20px;">{SVG_SHIELD}</span>'),
        ('⚠️ <strong>Hardened Irreversible Redaction:</strong>', f'{SVG_WARN} <strong>Irreversible Redaction:</strong>'),
        ('👁️', 'Show'),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
        
    p.write_text(text, encoding="utf-8")
    print("Updated web/index.html")

def clean_js_files():
    for f in (ROOT / "web" / "assets").glob("*.js"):
        if f.name.endswith(".min.js"):
            continue
        text = f.read_text(encoding="utf-8")
        text = replace_em_dashes(text)
        
        # Specific emoji cleanup in JS strings
        text = re.sub(r'["\']⚠️["\']', '"Warning"', text)
        text = text.replace("🔒 ", "")
        text = text.replace("🟢 ", "")
        text = text.replace("👑 ", "")
        text = text.replace("⚿ ", "")
        text = text.replace("✓ ", "")
        text = text.replace("📋", "")
        text = text.replace("👁️", "Show")
        text = text.replace("🙈", "Hide")
        text = text.replace("🎉", "Success")
        text = text.replace("📦", "Archive")
        text = text.replace("🔍", "Search")
        text = text.replace("⚡ ", "")
        text = text.replace("✂️", "Cut")
        text = text.replace("🗑️", "Delete")
        text = text.replace("📝", "Note")
        
        f.write_text(text, encoding="utf-8")
        print(f"Updated {f.name}")

def clean_css_files():
    for f in (ROOT / "web" / "assets").glob("*.css"):
        text = f.read_text(encoding="utf-8")
        text = replace_em_dashes(text)
        f.write_text(text, encoding="utf-8")
        print(f"Updated {f.name}")

if __name__ == "__main__":
    clean_index_html()
    clean_js_files()
    clean_css_files()
