# Component Migration Guide: CSS to Tailwind

This guide provides step-by-step instructions for migrating components from CSS modules to Tailwind CSS.

## Before You Start

1. Read `TAILWIND_SETUP.md` to understand the theme configuration
2. Ensure you have the Tailwind CSS IntelliSense extension installed in VS Code
3. Test the build process: `CI=false npm run build`

## Migration Checklist

For each component you migrate:

- [ ] Review existing CSS file and understand all styles
- [ ] Identify reusable patterns
- [ ] Convert styles to Tailwind classes
- [ ] Test in both light and dark modes
- [ ] Verify responsive behavior
- [ ] Remove CSS file import (but don't delete CSS file yet)
- [ ] Update documentation
- [ ] Test build process
- [ ] Mark component as migrated in tracking document

## Step-by-Step Process

### Step 1: Analyze Current Styles

Open the component's CSS file and identify:
1. **Static styles** (can be converted directly to Tailwind)
2. **Dynamic styles** (need conditional logic)
3. **Pseudo-states** (hover, focus, active)
4. **Responsive breakpoints**
5. **Dark mode variants**

Example CSS analysis:
```css
/* Static: Direct conversion */
.button {
  padding: 1rem 2rem;
  border-radius: 0.5rem;
  background-color: var(--primary-color);
}

/* Pseudo-state: Use hover: prefix */
.button:hover {
  background-color: var(--primary-hover);
}

/* Responsive: Use md: prefix */
@media (max-width: 768px) {
  .button {
    padding: 0.5rem 1rem;
  }
}

/* Dark mode: Already handled by CSS variables */
```

### Step 2: Create Tailwind Class Mapping

Create a mapping table for your component:

| CSS Property | CSS Value | Tailwind Class |
|--------------|-----------|----------------|
| `padding` | `1rem 2rem` | `px-8 py-4` |
| `border-radius` | `0.5rem` | `rounded-md` |
| `background-color` | `var(--primary-color)` | `bg-primary` |
| `:hover background` | `var(--primary-hover)` | `hover:bg-primary-hover` |
| Mobile padding | `0.5rem 1rem` | `md:px-4 md:py-2` |

### Step 3: Convert Component

**Before:**
```jsx
import './MyComponent.css';

function MyComponent() {
  return (
    <div className="container">
      <button className="button">
        Click me
      </button>
    </div>
  );
}
```

**After:**
```jsx
function MyComponent() {
  return (
    <div className="flex items-center justify-center p-4">
      <button className="bg-primary hover:bg-primary-hover text-white px-8 py-4 md:px-4 md:py-2 rounded-md transition-all">
        Click me
      </button>
    </div>
  );
}
```

### Step 4: Handle Dynamic Styles

For conditional styling, use template literals or className libraries:

**Before:**
```jsx
<button 
  className="button"
  style={{ backgroundColor: isActive ? 'var(--primary-color)' : 'var(--secondary-color)' }}
>
```

**After (Option 1: Template Literal):**
```jsx
<button className={`px-4 py-2 rounded-md ${isActive ? 'bg-primary' : 'bg-secondary'}`}>
```

**After (Option 2: clsx library):**
```jsx
import clsx from 'clsx';

<button className={clsx(
  'px-4 py-2 rounded-md',
  isActive ? 'bg-primary' : 'bg-secondary'
)}>
```

### Step 5: Handle Complex Styles

For complex or frequently repeated patterns, use composition:

**Option 1: Extract to Component**
```jsx
const Button = ({ variant = 'primary', children, ...props }) => {
  const baseClasses = 'px-4 py-2 rounded-md transition-all font-medium';
  const variantClasses = {
    primary: 'bg-primary hover:bg-primary-hover text-white',
    secondary: 'bg-secondary hover:bg-secondary-hover text-white',
    danger: 'bg-danger hover:bg-red-700 text-white',
  };
  
  return (
    <button className={`${baseClasses} ${variantClasses[variant]}`} {...props}>
      {children}
    </button>
  );
};
```

**Option 2: Use @apply in CSS (for very complex patterns)**
```css
@layer components {
  .btn-primary {
    @apply px-4 py-2 rounded-md bg-primary hover:bg-primary-hover;
    @apply text-white font-medium transition-all duration-200;
    @apply shadow-md hover:shadow-lg;
  }
}
```

### Step 6: Test Dark Mode

Always test components in dark mode:

```jsx
// In your browser console or React DevTools:
document.body.classList.add('dark-theme');    // Enable dark mode
document.body.classList.remove('dark-theme'); // Disable dark mode
```

For dark mode specific styles:
```jsx
<div className="bg-white dark-theme:bg-gray-900 text-black dark-theme:text-white">
  Content
</div>
```

### Step 7: Test Responsiveness

Test at different breakpoints:
- Mobile: < 640px
- Tablet: 640px - 1024px
- Desktop: > 1024px

Use Tailwind's responsive prefixes:
```jsx
<div className="w-full md:w-1/2 lg:w-1/3">
  Responsive width
</div>
```

## Common Patterns

### Layout Patterns

**Flexbox Container:**
```jsx
// Horizontal center
<div className="flex items-center justify-center">

// Vertical stack with gap
<div className="flex flex-col gap-4">

// Space between
<div className="flex justify-between items-center">
```

**Grid Layout:**
```jsx
// Responsive grid
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

// Auto-fit grid
<div className="grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-4">
```

### Typography

```jsx
// Heading
<h1 className="text-3xl font-bold text-text-primary">

// Body text
<p className="text-base text-text-secondary leading-relaxed">

// Small text
<small className="text-xs text-text-muted">
```

### Spacing

```jsx
// Padding
<div className="p-4">              // All sides: 1rem
<div className="px-4 py-2">        // Horizontal/Vertical
<div className="pt-4 pb-2">        // Top/Bottom specific

// Margin
<div className="mt-4 mb-2">        // Top/Bottom margin
<div className="mx-auto">          // Horizontal center
```

### Borders & Shadows

```jsx
// Border
<div className="border border-border rounded-lg">

// Shadow
<div className="shadow-md hover:shadow-lg transition-shadow">

// Focus ring
<input className="focus:ring-2 focus:ring-primary focus:outline-none">
```

### Transitions

```jsx
// All properties
<div className="transition-all duration-200">

// Specific properties
<div className="transition-colors duration-300 ease-in-out">

// Transforms
<button className="transform hover:scale-105 active:scale-95">
```

## Migration Examples

### Example 1: Simple Button

**CSS Version:**
```css
.button {
  padding: 0.5rem 1rem;
  background-color: var(--primary-color);
  color: white;
  border-radius: 0.5rem;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
}

.button:hover {
  background-color: var(--primary-hover);
  box-shadow: var(--shadow-md);
}
```

**Tailwind Version:**
```jsx
<button className="px-4 py-2 bg-primary text-white rounded-md border-0 cursor-pointer transition-all duration-200 hover:bg-primary-hover hover:shadow-md">
  Click me
</button>
```

### Example 2: Card Component

**CSS Version:**
```css
.card {
  background-color: var(--container-background-color);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  box-shadow: var(--shadow-sm);
  transition: all 0.2s ease;
}

.card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--primary-light);
}
```

**Tailwind Version:**
```jsx
<div className="bg-container border border-border rounded-lg p-lg shadow-sm transition-all duration-200 ease-in-out hover:shadow-md hover:border-primary-light">
  Card content
</div>
```

### Example 3: Form Input

**CSS Version:**
```css
.input {
  width: 100%;
  padding: var(--spacing-md);
  border: 1px solid var(--input-border);
  border-radius: var(--radius-md);
  background-color: var(--input-background-color);
  color: var(--text-primary);
  transition: all 0.2s ease;
}

.input:focus {
  outline: none;
  border-color: var(--input-focus);
  box-shadow: 0 0 0 3px rgba(0, 102, 204, 0.1);
}
```

**Tailwind Version:**
```jsx
<input 
  className="w-full p-md border border-input-border rounded-md bg-input-bg text-text-primary transition-all duration-200 focus:outline-none focus:border-input-focus focus:ring-2 focus:ring-primary/10"
  type="text"
/>
```

## Troubleshooting

### Issue: Styles not applying

**Check:**
1. Is the class name spelled correctly?
2. Is Tailwind CSS properly imported in index.tsx?
3. Are there conflicting styles from CSS modules?
4. Is the component file path included in tailwind.config.js content array?

**Solution:**
```bash
# Rebuild to clear cache
rm -rf build node_modules/.cache
CI=false npm run build
```

### Issue: Dark mode not working

**Check:**
1. Is `.dark-theme` class on body element?
2. Are you using the dark mode prefix correctly?
3. Is darkMode configured correctly in tailwind.config.js?

**Solution:**
```jsx
// Verify class is present
console.log(document.body.className); // Should include 'dark-theme' when dark

// Use correct prefix in Tailwind v3.4+
<div className="dark-theme:bg-gray-900">
```

### Issue: Custom colors not available

**Check:**
1. Are colors defined in tailwind.config.js theme.extend.colors?
2. Is color name correctly referenced?

**Solution:**
Use colors exactly as defined in config:
```jsx
// Correct
<div className="bg-primary">

// Incorrect
<div className="bg-primary-color">
```

## Best Practices

1. **Keep class names readable**: Break long class strings across lines
   ```jsx
   <div className="
     flex items-center justify-center
     bg-container border border-border
     p-4 rounded-lg shadow-md
     hover:shadow-lg transition-all
   ">
   ```

2. **Use consistent ordering**: Group related utilities
   - Layout (flex, grid, display)
   - Spacing (padding, margin)
   - Sizing (width, height)
   - Typography (font, text)
   - Colors (bg, text, border)
   - Effects (shadow, opacity)
   - Interactions (hover, focus)

3. **Extract reusable components**: Don't repeat long class strings

4. **Use semantic naming**: Create descriptive components
   ```jsx
   const PrimaryButton = ({ children, ...props }) => (
     <button className="bg-primary hover:bg-primary-hover..." {...props}>
       {children}
     </button>
   );
   ```

5. **Document custom patterns**: Add comments for complex class combinations

## Testing Checklist

After migrating a component:

- [ ] Component renders correctly
- [ ] All states work (hover, focus, active, disabled)
- [ ] Responsive behavior functions properly
- [ ] Dark mode displays correctly
- [ ] No console errors or warnings
- [ ] Build succeeds without errors
- [ ] Visual appearance matches original design
- [ ] Accessibility maintained (focus indicators, etc.)

## Reference

- [Tailwind CSS Documentation](https://tailwindcss.com/docs)
- [Tailwind CSS Cheat Sheet](https://nerdcave.com/tailwind-cheat-sheet)
- Project-specific config: `frontend/tailwind.config.js`
- Theme reference: `frontend/TAILWIND_SETUP.md`

---

**Last Updated**: 2025-12-03
