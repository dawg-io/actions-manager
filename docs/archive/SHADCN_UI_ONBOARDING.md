# shadcn/ui Onboarding Guide for Actions Manager

Welcome to the Actions Manager project! This guide will help you quickly get up to speed with our shadcn/ui component system and best practices for UI development.

## Table of Contents

1. [What is shadcn/ui?](#what-is-shadcnui)
2. [Quick Start](#quick-start)
3. [Available Components](#available-components)
4. [Common Patterns](#common-patterns)
5. [Migration Guidelines](#migration-guidelines)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)

## What is shadcn/ui?

shadcn/ui is not a traditional component library. Instead, it's a collection of re-usable components that you **copy into your project** and own completely. This gives you:

- ✅ **Full control** over the code
- ✅ **Easy customization** with Tailwind CSS
- ✅ **Built-in accessibility** via Radix UI primitives
- ✅ **TypeScript support** out of the box
- ✅ **Dark mode ready** using CSS variables

### Key Difference from Other Libraries

Instead of:
```tsx
import { Button } from 'some-ui-library'  // External dependency
```

You do:
```tsx
import { Button } from './components/ui/button'  // Your code, your control
```

## Quick Start

### 1. Using Existing Components

All shadcn/ui components are in `frontend/src/components/ui/`. Simply import and use them:

```tsx
import { Button } from '../components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';

function MyComponent() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Hello World</CardTitle>
      </CardHeader>
      <CardContent>
        <Button onClick={() => alert('Clicked!')}>
          Click me
        </Button>
      </CardContent>
    </Card>
  );
}
```

### 2. Component Variants

Most components support variants for different styles:

```tsx
// Buttons
<Button variant="default">Default</Button>
<Button variant="destructive">Delete</Button>
<Button variant="outline">Cancel</Button>
<Button variant="secondary">Secondary</Button>
<Button variant="ghost">Ghost</Button>
<Button variant="link">Link</Button>

// Sizes
<Button size="sm">Small</Button>
<Button size="default">Default</Button>
<Button size="lg">Large</Button>
<Button size="icon">🔍</Button>
```

### 3. Dark Mode Support

All components automatically support dark mode via the `.dark-theme` class on the root element. No extra work needed!

## Available Components

### Core Components

| Component | Location | Usage | Migrated |
|-----------|----------|-------|----------|
| **Button** | `ui/button.tsx` | Primary actions, form submissions | ✅ Yes |
| **Card** | `ui/card.tsx` | Content containers, info panels | ✅ Yes |
| **Dialog** | `ui/dialog.tsx` | Modals, confirmations | ✅ Yes |
| **DropdownMenu** | `ui/dropdown-menu.tsx` | Context menus, user menus | ✅ Yes |
| **Avatar** | `ui/avatar.tsx` | User profile images | ✅ Yes |
| **Input** | `ui/input.tsx` | Text inputs, form fields | ✅ Yes |
| **Label** | `ui/label.tsx` | Form field labels | ✅ Yes |
| **Select** | `ui/select.tsx` | Dropdown selects | ✅ Yes |
| **Checkbox** | `ui/checkbox.tsx` | Checkbox inputs | ✅ Yes |

### Usage Examples

#### Button Component

```tsx
import { Button } from '../components/ui/button';

// Simple button
<Button onClick={handleClick}>Save</Button>

// Destructive action
<Button variant="destructive" onClick={handleDelete}>
  Delete Project
</Button>

// Loading state
<Button disabled={isLoading}>
  {isLoading ? 'Saving...' : 'Save'}
</Button>

// With icon
<Button size="icon" variant="ghost">
  🔍
</Button>
```

#### Card Component

```tsx
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '../components/ui/card';
import { Button } from '../components/ui/button';

<Card>
  <CardHeader>
    <CardTitle>Project Settings</CardTitle>
    <CardDescription>Manage your project configuration</CardDescription>
  </CardHeader>
  <CardContent>
    {/* Your content here */}
  </CardContent>
  <CardFooter className="flex justify-end gap-2">
    <Button variant="outline">Cancel</Button>
    <Button>Save Changes</Button>
  </CardFooter>
</Card>
```

#### Dialog Component

```tsx
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../components/ui/dialog';
import { Button } from '../components/ui/button';
import { useState } from 'react';

function MyComponent() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <Button onClick={() => setIsOpen(true)}>Open Dialog</Button>
      
      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm Action</DialogTitle>
            <DialogDescription>
              Are you sure you want to proceed?
            </DialogDescription>
          </DialogHeader>
          {/* Dialog body content */}
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleConfirm}>
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
```

#### Input & Label Components

```tsx
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';

<div className="space-y-2">
  <Label htmlFor="email">Email</Label>
  <Input 
    id="email"
    type="email" 
    placeholder="your@email.com"
    value={email}
    onChange={(e) => setEmail(e.target.value)}
  />
</div>
```

#### Select Component

```tsx
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';

<Select value={runner} onValueChange={setRunner}>
  <SelectTrigger>
    <SelectValue placeholder="Select runner" />
  </SelectTrigger>
  <SelectContent>
    <SelectItem value="ubuntu-latest">Ubuntu Latest</SelectItem>
    <SelectItem value="windows-latest">Windows Latest</SelectItem>
    <SelectItem value="macos-latest">macOS Latest</SelectItem>
  </SelectContent>
</Select>
```

## Common Patterns

### Form with Multiple Fields

```tsx
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '../components/ui/card';

function ProjectForm() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Create Project</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="name">Project Name</Label>
          <Input id="name" placeholder="My Project" />
        </div>
        <div className="space-y-2">
          <Label htmlFor="description">Description</Label>
          <Input id="description" placeholder="Project description" />
        </div>
      </CardContent>
      <CardFooter className="flex justify-end gap-2">
        <Button variant="outline">Cancel</Button>
        <Button>Create</Button>
      </CardFooter>
    </Card>
  );
}
```

### Confirmation Dialog

```tsx
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Button } from '../components/ui/button';

function DeleteConfirmation({ isOpen, onClose, onConfirm, itemName }) {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete {itemName}?</DialogTitle>
          <DialogDescription>
            This action cannot be undone. This will permanently delete the item.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onConfirm}>
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

### List with Cards

```tsx
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';

function ProjectList({ projects }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {projects.map(project => (
        <Card key={project.id}>
          <CardHeader>
            <CardTitle>{project.name}</CardTitle>
            <CardDescription>{project.description}</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-text-secondary">
              Created: {project.createdAt}
            </p>
          </CardContent>
          <CardFooter className="flex gap-2">
            <Button variant="outline" size="sm">Edit</Button>
            <Button size="sm">View</Button>
          </CardFooter>
        </Card>
      ))}
    </div>
  );
}
```

## Migration Guidelines

### When to Migrate a Component

Consider migrating a component to shadcn/ui when:

1. ✅ You're adding new features to an existing component
2. ✅ You're fixing bugs in UI components
3. ✅ The component uses custom modal/dialog logic
4. ✅ The component has custom button styling
5. ✅ The component has form inputs that could be standardized

### What NOT to Migrate Right Now

- ❌ Components with complex, specialized CSS (e.g., Monaco editor, code highlighters)
- ❌ Components that are working well and rarely change
- ❌ Navigation components with unique layouts (e.g., Sidebar)
- ❌ Third-party library wrappers

### Migration Checklist

When migrating a component:

- [ ] Identify which shadcn/ui components you'll use
- [ ] Import the necessary components
- [ ] Replace HTML elements (`<button>` → `<Button>`)
- [ ] Apply appropriate variants (`variant="destructive"` for delete buttons)
- [ ] Remove custom CSS classes where shadcn/ui provides styling
- [ ] Test in both light and dark modes
- [ ] Verify keyboard navigation still works
- [ ] Update tests if needed
- [ ] Remove unused CSS files

## Best Practices

### 1. Use Semantic Variants

```tsx
// ✅ Good - semantic meaning
<Button variant="destructive">Delete</Button>
<Button variant="outline">Cancel</Button>
<Button>Save</Button>

// ❌ Avoid - generic styling
<Button className="bg-red-500">Delete</Button>
```

### 2. Compose Components

```tsx
// ✅ Good - compose components for structure
<Dialog>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Title</DialogTitle>
    </DialogHeader>
    <p>Content</p>
    <DialogFooter>
      <Button>Action</Button>
    </DialogFooter>
  </DialogContent>
</Dialog>

// ❌ Avoid - flat structure loses semantic meaning
<Dialog>
  <div>
    <h2>Title</h2>
    <p>Content</p>
    <button>Action</button>
  </div>
</Dialog>
```

### 3. Use the cn() Utility for Class Merging

```tsx
import { cn } from '../../lib/utils';

// ✅ Good - properly merged classes
<Button 
  className={cn(
    "w-full",
    isLoading && "opacity-50",
    isError && "ring-2 ring-red-500"
  )}
>
  Submit
</Button>

// ❌ Avoid - string concatenation
<Button className={`w-full ${isLoading ? 'opacity-50' : ''}`}>
  Submit
</Button>
```

### 4. Maintain Accessibility

```tsx
// ✅ Good - accessible dialog
<Dialog>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Delete Project</DialogTitle>
      <DialogDescription>
        This will permanently delete your project.
      </DialogDescription>
    </DialogHeader>
  </DialogContent>
</Dialog>

// ❌ Avoid - missing descriptions
<Dialog>
  <DialogContent>
    <h2>Delete Project</h2>
  </DialogContent>
</Dialog>
```

### 5. Keep Styling Consistent

```tsx
// ✅ Good - use Tailwind spacing utilities
<CardFooter className="flex justify-end gap-2">
  <Button>Action</Button>
</CardFooter>

// ❌ Avoid - inline styles
<div style={{ display: 'flex', gap: '8px' }}>
  <Button>Action</Button>
</div>
```

## Styling Guidelines

### Using Tailwind with shadcn/ui

All components use Tailwind CSS and CSS variables for theming:

```tsx
// Spacing
<div className="space-y-4">  {/* Vertical spacing */}
<div className="flex gap-2">  {/* Horizontal spacing */}

// Colors (uses theme variables)
<div className="bg-container-background-color">  {/* Light mode */}
<div className="dark-theme:bg-container-dark-background">  {/* Dark mode */}

// Text
<p className="text-sm text-text-secondary">
<h2 className="text-lg font-semibold">

// Layout
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
<div className="flex flex-col items-center justify-center">
```

### Theme Colors

The project uses CSS variables defined in `src/index.css`:

```css
/* Light mode */
--primary: /* blue */
--text-primary: /* dark text */
--container-background-color: /* white/light */

/* Dark mode (.dark-theme) */
--primary-dark: /* lighter blue */
--text-primary-dark: /* light text */
--container-dark-background: /* dark gray */
```

## Troubleshooting

### Component Not Found

```tsx
// ❌ Error: Cannot find module
import { Button } from '@/components/ui/button';

// ✅ Solution: Use relative imports
import { Button } from '../components/ui/button';
```

We use relative imports because Create React App doesn't support path aliases out of the box.

### Styles Not Applying

1. Check that Tailwind CSS is processing the file (it should be in `content` array of `tailwind.config.js`)
2. Verify CSS variables are defined in `src/index.css`
3. Check that `.dark-theme` class is applied to root element for dark mode
4. Clear build cache: `rm -rf node_modules/.cache && npm start`

### TypeScript Errors

```tsx
// ❌ Error: Type 'string' is not assignable to type 'ButtonVariant'
<Button variant="danger">Delete</Button>

// ✅ Solution: Use correct variant
<Button variant="destructive">Delete</Button>
```

Check the component's TypeScript definition for valid prop values.

### Dialog Not Closing

```tsx
// ❌ Wrong: Missing onOpenChange
<Dialog open={isOpen}>
  <DialogContent>...</DialogContent>
</Dialog>

// ✅ Correct: Provide onOpenChange handler
<Dialog open={isOpen} onOpenChange={setIsOpen}>
  <DialogContent>...</DialogContent>
</Dialog>
```

## Real-World Examples

### Example 1: Project List Component

See `frontend/src/components/ProjectList.tsx` for a complete example of:
- Using Card components for list items
- Button variants for different actions
- Responsive grid layout
- Conditional rendering

### Example 2: Delete Modal Component

See `frontend/src/components/DeleteProjectModal.tsx` for:
- Dialog component with confirmation flow
- Destructive button variants
- Loading states
- Error handling

### Example 3: User Menu

See `frontend/src/components/UserAvatar.tsx` for:
- DropdownMenu component
- Avatar component
- Icon integration with lucide-react
- Theme toggle implementation

## Additional Resources

- **shadcn/ui Documentation**: https://ui.shadcn.com
- **Radix UI Primitives**: https://www.radix-ui.com/primitives
- **Tailwind CSS**: https://tailwindcss.com
- **Project Migration Plan**: See `SHADCN_UI_MIGRATION.md`
- **Component Guide**: See `SHADCN_UI_COMPONENT_GUIDE.md`

## Getting Help

1. Check existing components in `frontend/src/components/ui/`
2. Review the [shadcn/ui documentation](https://ui.shadcn.com)
3. Look at migrated components for patterns (ProjectList, DeleteProjectModal, UserAvatar)
4. Ask in team chat or create an issue

## Summary

- ✅ Use shadcn/ui components from `components/ui/`
- ✅ Import with relative paths, not `@/` aliases
- ✅ Use semantic variants (`destructive`, `outline`, etc.)
- ✅ Compose components for better structure
- ✅ Use `cn()` utility for class merging
- ✅ Maintain accessibility with proper ARIA labels
- ✅ Test in both light and dark modes
- ✅ Follow Tailwind CSS conventions for spacing and layout

Welcome aboard! Happy coding! 🚀
