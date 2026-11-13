// Read the saved theme before the stylesheet paints the first viewport.
try {
  document.documentElement.dataset.paperplaneTheme = localStorage.getItem('paperplane_theme') === 'dark' ? 'dark' : 'light';
} catch {
  document.documentElement.dataset.paperplaneTheme = 'light';
}
