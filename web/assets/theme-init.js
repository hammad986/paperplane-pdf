// Read the saved theme before the stylesheet paints the first viewport.
try {
  const saved = localStorage.getItem('paperplane_theme') === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.paperplaneTheme = saved;
  const metaColorScheme = document.querySelector('meta[name="color-scheme"]');
  if (metaColorScheme) metaColorScheme.content = saved;
} catch {
  document.documentElement.dataset.paperplaneTheme = 'light';
}
