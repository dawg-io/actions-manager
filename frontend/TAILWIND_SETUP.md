# Tailwind CSS Integration Guide

## Overview

This project has been configured to use **Tailwind CSS v3** alongside the existing CSS variable system. This allows for gradual migration while maintaining backward compatibility with existing styles.

## Installation

Tailwind CSS has been installed with the following packages:
- `tailwindcss@^3` - Core Tailwind CSS framework
- `postcss@^8` - CSS processor
- `autoprefixer@^10` - CSS vendor prefix automation

## Configuration Files

### 1. `tailwind.config.js`
Located at `/frontend/tailwind.config.js`, this file contains:
- Content paths for scanning Tailwind classes
- Dark mode configuration (class strategy using `.dark-theme`)
- Extended theme with custom colors, spacing, shadows, etc. mapped from existing CSS variables
- Custom color palette that matches the existing design system

### 2. `postcss.config.js`
Located at `/frontend/postcss.config.js`, enables:
- Tailwind CSS processing
- Autoprefixer for browser compatibility

### 3. `src/index.css`
Contains:
- Tailwind directives (`@tailwind base`, `@tailwind components`, `@tailwind utilities`)
- All existing CSS variables preserved for backward compatibility
- Both new Tailwind-style naming (e.g., `--color-primary`) and legacy naming (e.g., `--primary-color`)
- Dark theme support via `.dark-theme` class

## Theme Configuration

### Color System

The Tailwind theme extends the default palette with custom colors that match our design system:

```javascript
// Light mode colors
bg-background      // #f8fafc
bg-container       // #ffffff
bg-primary         // #0066cc
bg-success         // #10b981
bg-danger          // #ef4444
bg-warning         // #f59e0b

// Text colors
text-text-primary     // #0f172a
text-text-secondary   // #64748b
text-text-muted       // #94a3b8

// And more...
```

### Dark Mode

Dark mode is configured using the `class` strategy, which means:
- Add `dark-theme` class to `<body>` element to enable dark mode
- The existing `ThemeContext` handles this automatically
- CSS variables update automatically based on the theme

### Spacing System

Custom spacing scale matching existing design:
- `xs`: 0.25rem (4px)
- `sm`: 0.5rem (8px)
- `md`: 0.75rem (12px)
- `lg`: 1.5rem (24px)
- `xl`: 2rem (32px)
- `2xl`: 3rem (48px)

### Border Radius

Custom border radius values:
- `rounded-sm`: 0.375rem
- `rounded-md`: 0.5rem
- `rounded-lg`: 0.75rem
- `rounded-xl`: 1rem

### Shadows

Custom shadow system:
- `shadow-sm`, `shadow-md`, `shadow-lg`, `shadow-xl`
- Dark mode variants: `shadow-dark-sm`, `shadow-dark-md`, etc.

## Usage Examples

### Before (CSS-in-JS)
```jsx
<div style={{
  backgroundColor: "var(--container-background-color)",
  padding: "3rem",
  borderRadius: "1rem",
  boxShadow: "var(--shadow-xl)",
  border: "1px solid var(--border-color)",
}}>
  Content
</div>
```

### After (Tailwind CSS)
```jsx
<div className="bg-container p-12 rounded-2xl shadow-xl border border-border">
  Content
</div>
```

### Button Example
```jsx
<button className="bg-primary text-white px-8 py-3.5 rounded-lg hover:bg-primary-hover transition-all duration-200 shadow-md">
  Click Me
</button>
```

### Responsive Design
```jsx
<div className="w-full md:w-1/2 lg:w-1/3">
  Responsive width
</div>
```

### Dark Mode Specific Styles
```jsx
<div className="bg-white dark-theme:bg-gray-900">
  Adapts to theme
</div>
```

## Migration Strategy

### Phase 1: Foundation (✅ Complete)
- [x] Install and configure Tailwind CSS
- [x] Set up theme with existing design tokens
- [x] Configure dark mode support
- [x] Preserve all existing CSS variables for compatibility
- [x] Migrate login screen (App.tsx) as proof of concept

### Phase 2: Component Migration (Planned)
- [ ] Migrate common components (buttons, inputs, modals)
- [ ] Update ProjectMgmt component
- [ ] Update Sidebar component
- [ ] Update workflow-related components
- [ ] Create reusable Tailwind component utilities

### Phase 3: Cleanup (Planned)
- [ ] Remove unused CSS files after verification
- [ ] Consolidate duplicate styles
- [ ] Document custom Tailwind utilities
- [ ] Update component documentation

## Best Practices

### 1. Use Tailwind Classes First
For new components, prefer Tailwind utility classes over inline styles or CSS files.

### 2. Create Reusable Components
Extract repeated Tailwind patterns into React components:
```jsx
const Button = ({ variant = 'primary', children, ...props }) => (
  <button 
    className={`px-4 py-2 rounded-lg transition-all ${
      variant === 'primary' ? 'bg-primary hover:bg-primary-hover' : 
      variant === 'danger' ? 'bg-danger hover:bg-danger-dark' : ''
    }`}
    {...props}
  >
    {children}
  </button>
);
```

### 3. Use @layer for Custom Styles
When you need custom CSS, use Tailwind's layer system:
```css
@layer components {
  .btn-primary {
    @apply px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-hover;
  }
}
```

### 4. Maintain Backward Compatibility
During migration:
- Keep existing CSS variables in index.css
- Don't remove CSS files until components are fully migrated
- Test dark mode after each component migration

### 5. Use Tailwind Intellisense
Install the "Tailwind CSS IntelliSense" VS Code extension for:
- Autocomplete for class names
- CSS preview on hover
- Linting and validation

## Testing

### Build Test
```bash
cd frontend
CI=false npm run build
```

### Dev Server
```bash
cd frontend
npm start
```

### Visual Testing Checklist
- [ ] Login screen renders correctly
- [ ] Dark mode toggle works
- [ ] Responsive design functions properly
- [ ] All colors match design system
- [ ] Shadows and borders display correctly

## Troubleshooting

### Issue: Tailwind classes not applying
**Solution**: Make sure:
1. `index.css` is imported in `index.tsx`
2. PostCSS is processing the CSS files
3. Content paths in `tailwind.config.js` include all component files

### Issue: Dark mode not working
**Solution**: 
1. Verify `.dark-theme` class is added to `<body>` element
2. Check that `ThemeContext` is wrapping the app
3. Ensure CSS variables are defined for both light and dark themes

### Issue: Build errors
**Solution**:
1. Clear build cache: `rm -rf build node_modules/.cache`
2. Reinstall dependencies: `npm install`
3. Rebuild: `CI=false npm run build`

## Resources

- [Tailwind CSS Documentation](https://tailwindcss.com/docs)
- [Tailwind CSS Cheat Sheet](https://nerdcave.com/tailwind-cheat-sheet)
- [Tailwind Play (Online Playground)](https://play.tailwindcss.com/)
- [Tailwind CSS IntelliSense](https://marketplace.visualstudio.com/items?itemName=bradlc.vscode-tailwindcss)

## Commit History

- **Initial Setup**: Added Tailwind CSS v3, configured theme, migrated App.tsx login screen
- Future commits will document additional component migrations

## Next Steps

1. Review the migrated login screen
2. Test dark mode functionality
3. Begin migrating common components (buttons, inputs)
4. Create component library documentation
5. Gradually migrate remaining pages
