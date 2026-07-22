# shadcn/ui Component Upgrade Guide

This guide documents the process for adding and upgrading shadcn/ui components in the Actions Manager project.

## Quick Start

### Using Existing Components

```tsx
import { Button } from '../components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';

function MyComponent() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Welcome</CardTitle>
      </CardHeader>
      <CardContent>
        <Button>Click me</Button>
      </CardContent>
    </Card>
  );
}
```

**Note**: We use relative imports instead of `@/` path aliases due to Create React App limitations.

## Adding New Components

There are two methods to add new shadcn/ui components:

### Method 1: Using shadcn CLI (Recommended)

```bash
cd frontend
npx shadcn-ui@latest add [component-name]
```

**Example:**
```bash
npx shadcn-ui@latest add select
npx shadcn-ui@latest add input
npx shadcn-ui@latest add tooltip
```

The CLI will:
- Download the component to `src/components/ui/`
- Install required dependencies
- Update `components.json` if needed

### Method 2: Manual Installation

1. **Visit [ui.shadcn.com](https://ui.shadcn.com/docs/components)**

2. **Copy the component code** from the docs

3. **Create the file** in `src/components/ui/[component-name].tsx`

4. **Install dependencies** if listed:
   ```bash
   npm install --legacy-peer-deps @radix-ui/react-[component]
   ```

5. **Update the barrel export** in `src/components/ui/index.ts`:
   ```typescript
   export * from './[component-name]';
   ```

## Customizing Components

### Adding Custom Variants

Edit the component file to add new variants:

```tsx
// src/components/ui/button.tsx
const buttonVariants = cva(
  "base-classes",
  {
    variants: {
      variant: {
        default: "...",
        // Add your custom variant
        brand: "bg-gradient-to-r from-blue-500 to-purple-500 text-white",
      }
    }
  }
)

// Usage
<Button variant="brand">Custom Button</Button>
```

### Overriding Styles

Use the `className` prop to override or extend styles:

```tsx
import { cn } from '../../lib/utils';

<Button 
  className={cn(
    "rounded-full", // Override border-radius
    isActive && "ring-2 ring-primary" // Conditional styling
  )}
>
  Click me
</Button>
```

### Theme Integration

All components use CSS variables from `src/index.css` and respect the `.dark-theme` class:

```tsx
// Components automatically switch themes
<Button>Works in light mode</Button>
// In .dark-theme, automatically uses dark colors
```

## Available Components

### Currently Implemented

- ✅ **Button** - All variants (default, destructive, outline, secondary, ghost, link)
- ✅ **Card** - Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter
- ✅ **Dialog** - Modal dialogs with animations
- ✅ **DropdownMenu** - Full menu system with submenus

### Recommended Next Components

Based on the codebase, consider adding:

1. **Input** - Form inputs
   ```bash
   npx shadcn-ui@latest add input
   ```

2. **Select** - Dropdowns and selects
   ```bash
   npx shadcn-ui@latest add select
   ```

3. **Textarea** - Multi-line text inputs
   ```bash
   npx shadcn-ui@latest add textarea
   ```

4. **Label** - Form labels
   ```bash
   npx shadcn-ui@latest add label
   ```

5. **Badge** - Status indicators
   ```bash
   npx shadcn-ui@latest add badge
   ```

6. **Alert** - Notification messages
   ```bash
   npx shadcn-ui@latest add alert
   ```

7. **Tabs** - Tabbed interfaces
   ```bash
   npx shadcn-ui@latest add tabs
   ```

8. **Tooltip** - Hover tooltips
   ```bash
   npx shadcn-ui@latest add tooltip
   ```

9. **Switch** - Toggle switches (for dark mode)
   ```bash
   npx shadcn-ui@latest add switch
   ```

10. **Avatar** - User profile images
    ```bash
    npx shadcn-ui@latest add avatar
    ```

## Testing Components

### Writing Tests

```tsx
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { Button } from '../components/ui/button';

describe('Button', () => {
  it('renders correctly', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button')).toBeInTheDocument();
  });
});
```

### Running Tests

```bash
# Run all UI component tests
npm test -- --testPathPattern=ui.test.tsx --watchAll=false

# Run specific test file
npm test -- src/components/ui/button.test.tsx --watchAll=false
```

## Migration Examples

### Migrating Custom Buttons

**Before:**
```tsx
<button className="delete-button" onClick={handleDelete}>
  Delete Project
</button>
```

**After:**
```tsx
import { Button } from '../components/ui/button';

<Button variant="destructive" onClick={handleDelete}>
  Delete Project
</Button>
```

### Migrating Custom Modals

**Before:**
```tsx
<div className="modal-overlay">
  <div className="modal-content">
    <div className="modal-header">
      <h2>Confirm Action</h2>
      <button onClick={onClose}>×</button>
    </div>
    <div className="modal-body">
      {children}
    </div>
    <div className="modal-footer">
      <button onClick={onClose}>Cancel</button>
      <button onClick={onConfirm}>Confirm</button>
    </div>
  </div>
</div>
```

**After:**
```tsx
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle, 
  DialogFooter 
} from '../components/ui/dialog';
import { Button } from '../components/ui/button';

<Dialog open={isOpen} onOpenChange={setIsOpen}>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Confirm Action</DialogTitle>
    </DialogHeader>
    {children}
    <DialogFooter>
      <Button variant="outline" onClick={onClose}>Cancel</Button>
      <Button onClick={onConfirm}>Confirm</Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

### Migrating Custom Cards

**Before:**
```tsx
<div className="project-card">
  <div className="card-header">
    <h3>{project.name}</h3>
  </div>
  <div className="card-body">
    <p>{project.description}</p>
  </div>
  <div className="card-footer">
    <button>View</button>
    <button>Edit</button>
  </div>
</div>
```

**After:**
```tsx
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '../components/ui/card';
import { Button } from '../components/ui/button';

<Card>
  <CardHeader>
    <CardTitle>{project.name}</CardTitle>
  </CardHeader>
  <CardContent>
    <p>{project.description}</p>
  </CardContent>
  <CardFooter className="gap-2">
    <Button variant="outline">View</Button>
    <Button>Edit</Button>
  </CardFooter>
</Card>
```

## Best Practices

### 1. Use Semantic Variants

```tsx
// Good: Semantic meaning
<Button variant="destructive">Delete</Button>
<Button variant="outline">Cancel</Button>

// Avoid: Generic styling
<Button className="bg-red-500">Delete</Button>
```

### 2. Compose Components

```tsx
// Good: Compose for complex UIs
<Card>
  <CardHeader>
    <CardTitle>Settings</CardTitle>
    <CardDescription>Manage your account</CardDescription>
  </CardHeader>
  <CardContent>
    <div className="space-y-4">
      {/* Form fields */}
    </div>
  </CardContent>
  <CardFooter>
    <Button variant="outline">Cancel</Button>
    <Button>Save</Button>
  </CardFooter>
</Card>
```

### 3. Use the cn() Utility

```tsx
import { cn } from '../../lib/utils';

// Good: Merge classes properly
<Button 
  className={cn(
    "w-full", 
    isLoading && "opacity-50 cursor-wait"
  )}
>
  Submit
</Button>

// Avoid: String concatenation
<Button className={`w-full ${isLoading ? 'opacity-50' : ''}`}>
  Submit
</Button>
```

### 4. Maintain Accessibility

```tsx
// Good: Accessible dialog
<Dialog>
  <DialogTrigger asChild>
    <Button>Open</Button>
  </DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Important Action</DialogTitle>
      <DialogDescription>
        This action cannot be undone.
      </DialogDescription>
    </DialogHeader>
    {/* Content */}
  </DialogContent>
</Dialog>

// Components handle ARIA attributes, focus management, keyboard navigation
```

### 5. Leverage TypeScript

```tsx
// Good: Type-safe props
import type { ButtonProps } from '../components/ui/button';

interface MyComponentProps {
  onSave: () => void;
  buttonProps?: ButtonProps;
}

function MyComponent({ onSave, buttonProps }: MyComponentProps) {
  return <Button onClick={onSave} {...buttonProps}>Save</Button>;
}
```

## Troubleshooting

### Import Errors

**Problem:** `Cannot find module '../components/ui/button'`

**Solution:** 
- Ensure tsconfig.json has path aliases configured
- Restart your dev server
- Clear TypeScript cache: `rm -rf node_modules/.cache`

### Styling Issues

**Problem:** Components don't match the theme

**Solution:**
- Verify CSS variables are defined in `src/index.css`
- Check that `.dark-theme` class is applied to `<html>` or `<body>`
- Ensure Tailwind is processing the component files (check `content` in tailwind.config.js)

### Type Errors

**Problem:** TypeScript errors on component props

**Solution:**
- Install missing Radix UI dependencies
- Update `@types` packages if needed
- Check component prop types match the interface

### Test Failures

**Problem:** Tests can't resolve `@/` imports

**Solution:**
- Verify `moduleNameMapper` in package.json jest config:
  ```json
  "jest": {
    "moduleNameMapper": {
      "^@/(.*)$": "<rootDir>/src/$1"
    }
  }
  ```

## Resources

- [shadcn/ui Documentation](https://ui.shadcn.com)
- [Radix UI Documentation](https://www.radix-ui.com)
- [Tailwind CSS Documentation](https://tailwindcss.com)
- [Migration Plan](./SHADCN_UI_MIGRATION.md)
- [Example Component](./frontend/src/components/ShadcnUIExample.tsx)

## Getting Help

- Check the [shadcn/ui Discord](https://discord.gg/shadcn)
- Review [existing components](./frontend/src/components/ui/)
- See [ShadcnUIExample.tsx](./frontend/src/components/ShadcnUIExample.tsx) for usage examples
