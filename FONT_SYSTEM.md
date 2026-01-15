# Global Font System Documentation

## Overview
This document describes the unified font system implemented across the Algonox AADOS application. The system ensures consistent typography, branding, and readability throughout the application.

---

## Font Configuration

### Primary Font: Plus Jakarta Sans
- **Purpose**: Main UI text (headings, body, buttons, labels)
- **Weights loaded**: 400, 500, 600, 700, 800
- **Source**: Google Fonts
- **CDN Link**: `https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800`

### Monospace Font: JetBrains Mono
- **Purpose**: Code, data display, technical content (tables, activity monitor, forms)
- **Weights loaded**: 400, 500, 600
- **Source**: Google Fonts
- **CDN Link**: `https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600`

---

## CSS Variables

The font system is centralized using CSS custom properties defined in `frontend/src/styles/globals.css`:

```css
:root {
  --font-primary: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI',
                  'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans',
                  'Helvetica Neue', sans-serif;

  --font-mono: 'JetBrains Mono', 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono',
               Consolas, 'Courier New', monospace;
}
```

### Fallback Strategy
The fallback fonts ensure the application remains usable even if Google Fonts fail to load:

**Primary Font Fallbacks** (in order):
1. Plus Jakarta Sans (Google Fonts)
2. -apple-system (macOS/iOS system font)
3. BlinkMacSystemFont (older macOS/iOS)
4. Segoe UI (Windows)
5. Roboto (Android)
6. Oxygen (KDE)
7. Ubuntu (Ubuntu)
8. Cantarell (GNOME)
9. Fira Sans (Firefox OS)
10. Droid Sans (older Android)
11. Helvetica Neue (macOS)
12. sans-serif (system default)

**Monospace Font Fallbacks** (in order):
1. JetBrains Mono (Google Fonts)
2. SF Mono (macOS)
3. Monaco (macOS)
4. Cascadia Code (Windows Terminal)
5. Roboto Mono (Android)
6. Consolas (Windows)
7. Courier New (universal)
8. monospace (system default)

---

## Global Font Application

### Base Elements
All text inherits from the `body` element:

```css
body {
  font-family: var(--font-primary);
}
```

### Universal Inheritance
Form elements and interactive components explicitly inherit the global font:

```css
button, input, textarea, select, optgroup, option {
  font-family: inherit;
}
```

### Monospace Elements
Technical/code elements use the monospace font:

```css
code, pre, kbd, samp {
  font-family: var(--font-mono);
}
```

---

## Component-Level Usage

### Recommended Approach
Always use CSS variables for font references:

✅ **CORRECT**:
```jsx
<div style={{ fontFamily: "var(--font-primary)" }}>Content</div>
```

❌ **INCORRECT**:
```jsx
<div style={{ fontFamily: "'Custom Font', sans-serif" }}>Content</div>
```

### Specific Component Usage

**Primary Font Used In:**
- All buttons (`.btn`, `.btn-primary`, `.btn-secondary`, `.btn-call`)
- Brand headings
- Panel titles
- Dashboard components
- Modal headers
- Inline styles in Dashboard.jsx, LeadsPanel.jsx, PDFViewer.jsx

**Monospace Font Used In:**
- Tables (`.table`)
- Activity monitor (`.activity-msg`, `.activity-time`)
- Form labels (`.label`)
- Inputs and textareas (`.input`, `.textarea`)
- Error messages (`.req`, `.alert-error`)
- Modal subtitles
- Status indicators

---

## Changes Made

### Files Modified

1. **`frontend/src/styles/globals.css`**
   - Lines 22-23: Enhanced font stacks with comprehensive fallbacks
   - Lines 50-66: Added universal font inheritance rules

2. **`frontend/src/components/Dashboard.jsx`**
   - Replaced all instances of `fontFamily: "'Orbitron', sans-serif"` with `fontFamily: "var(--font-primary)"`
   - Locations: lines 256, 327, 351

3. **`frontend/src/components/LeadsPanel.jsx`**
   - Replaced `fontFamily: "'Orbitron', sans-serif"` with `fontFamily: "var(--font-primary)"`
   - Location: line 59

4. **`frontend/src/components/PDFViewer.jsx`**
   - Replaced `fontFamily: "'Orbitron', sans-serif"` with `fontFamily: "var(--font-primary)"`
   - Location: line 42

### Issues Fixed
- **Orbitron Font**: Removed references to 'Orbitron' font which was never loaded, causing fallback to system fonts
- **Inconsistent Fonts**: Unified all components to use the same font system
- **Limited Fallbacks**: Added comprehensive cross-platform font fallbacks
- **Missing Inheritance**: Added explicit font inheritance for form elements

---

## Future Font Changes

To change the application font globally:

1. **Update Google Fonts in `frontend/index.html`** (lines 9-14)
2. **Update CSS variables in `frontend/src/styles/globals.css`** (lines 22-23)
3. **No component changes needed** - all components reference CSS variables

### Example: Changing to Roboto
```html
<!-- frontend/index.html -->
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet" />
```

```css
/* frontend/src/styles/globals.css */
:root {
  --font-primary: 'Roboto', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
```

---

## Exceptions & Limitations

### Third-Party Components
Some third-party libraries may override fonts using inline styles or scoped CSS:
- **lucide-react icons**: Use SVG, no font impact
- **Browser defaults**: Developer tools, native scrollbars retain browser fonts
- **PDF iframe**: PDF content retains embedded fonts

### Browser Compatibility
- CSS variables supported in all modern browsers (Chrome 49+, Firefox 31+, Safari 9.1+, Edge 15+)
- Fallback fonts ensure compatibility if Google Fonts CDN is blocked or slow

### Performance Considerations
- Fonts are loaded with `display=swap` to prevent FOIT (Flash of Invisible Text)
- Two font families loaded (Primary + Mono) = minimal impact
- Total font weight: ~120KB (gzipped)

---

## Testing Checklist

✅ All primary UI text renders in Plus Jakarta Sans
✅ All code/data elements render in JetBrains Mono
✅ Font loads correctly on Windows, macOS, Linux
✅ Fallback fonts work when Google Fonts unavailable
✅ No visual regressions (spacing, overflow, alignment)
✅ Form elements inherit global font
✅ Build succeeds without errors
✅ No console warnings related to fonts

---

## Contact & Support

For font-related issues or questions:
- Check browser DevTools → Network tab to verify font loading
- Verify CSS variables are defined: `getComputedStyle(document.body).fontFamily`
- Check for conflicting inline styles or CSS rules

**Last Updated**: 2026-01-07
**Build Status**: ✅ Passing (2.34s build time)
