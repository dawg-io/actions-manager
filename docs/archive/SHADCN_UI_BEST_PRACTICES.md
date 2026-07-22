# shadcn/ui Best Practices for Actions Manager

This document outlines coding standards, patterns, and best practices when working with shadcn/ui components in the Actions Manager project.

## Table of Contents

1. [Import Patterns](#import-patterns)
2. [Component Composition](#component-composition)
3. [Styling Guidelines](#styling-guidelines)
4. [Accessibility Standards](#accessibility-standards)
5. [TypeScript Usage](#typescript-usage)
6. [Testing Practices](#testing-practices)
7. [Common Patterns](#common-patterns)
8. [Anti-Patterns to Avoid](#anti-patterns-to-avoid)

## Import Patterns

### ✅ DO: Use Relative Imports

```tsx
// ✅ Correct
import { Button } from '../components/ui/button';
import { Dialog, DialogContent, DialogHeader } from '../components/ui/dialog';
```

### ❌ DON'T: Use Path Aliases

```tsx
// ❌ Incorrect - CRA doesn't support this
import { Button } from '@/components/ui/button';
```

**Why**: Create React App doesn't support custom path aliases without ejecting. Use relative imports for maximum compatibility.

### Group Imports Logically

```tsx
// ✅ Good organization
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Button } from '../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';

import { createProject } from '../api/projects';
import { cn } from '../lib/utils';
```

## Component Composition

### Use Semantic Component Structure

```tsx
// ✅ Good - clear semantic hierarchy
<Card>
  <CardHeader>
    <CardTitle>Project Settings</CardTitle>
    <CardDescription>Configure your project</CardDescription>
  </CardHeader>
  <CardContent>
    {/* Main content */}
  </CardContent>
  <CardFooter className="flex justify-end gap-2">
    <Button variant="outline">Cancel</Button>
    <Button>Save</Button>
  </CardFooter>
</Card>

// ❌ Bad - flat structure loses meaning
<Card>
  <div>
    <h3>Project Settings</h3>
    <p>Configure your project</p>
    {/* content */}
    <div>
      <button>Cancel</button>
      <button>Save</button>
    </div>
  </div>
</Card>
```

### Compose Dialogs Properly

```tsx
// ✅ Good - proper dialog structure
<Dialog open={isOpen} onOpenChange={setIsOpen}>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Delete Project?</DialogTitle>
      <DialogDescription>
        This action cannot be undone.
      </DialogDescription>
    </DialogHeader>
    
    <div className="py-4">
      {/* Dialog body content */}
    </div>
    
    <DialogFooter>
      <Button variant="outline" onClick={() => setIsOpen(false)}>
        Cancel
      </Button>
      <Button variant="destructive" onClick={handleDelete}>
        Delete
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>

// ❌ Bad - missing structure and handlers
<Dialog open={isOpen}>
  <div>
    <h2>Delete Project?</h2>
    <button>Delete</button>
  </div>
</Dialog>
```

## Styling Guidelines

### Use Semantic Button Variants

```tsx
// ✅ Good - semantic meaning is clear
<Button variant="destructive">Delete Project</Button>
<Button variant="outline">Cancel</Button>
<Button variant="secondary">Maybe Later</Button>
<Button variant="ghost">Close</Button>
<Button>Save Changes</Button>

// ❌ Bad - generic styling doesn't convey meaning
<Button className="bg-red-500">Delete Project</Button>
<Button className="border">Cancel</Button>
```

### Use cn() for Class Merging

```tsx
import { cn } from '../../lib/utils';

// ✅ Good - properly merged classes
<Button 
  className={cn(
    "w-full",
    isLoading && "opacity-50 cursor-wait",
    isError && "ring-2 ring-red-500"
  )}
>
  {isLoading ? 'Submitting...' : 'Submit'}
</Button>

// ❌ Bad - string concatenation can cause conflicts
<Button className={`w-full ${isLoading ? 'opacity-50' : ''} ${isError ? 'ring-2' : ''}`}>
  Submit
</Button>
```

### Prefer Tailwind Utilities Over Inline Styles

```tsx
// ✅ Good - Tailwind utilities
<div className="flex flex-col gap-4 p-6">
  <div className="text-lg font-semibold">Title</div>
  <div className="text-sm text-text-secondary">Description</div>
</div>

// ❌ Bad - inline styles
<div style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '24px' }}>
  <div style={{ fontSize: '18px', fontWeight: 600 }}>Title</div>
  <div style={{ fontSize: '14px', color: '#666' }}>Description</div>
</div>
```

### Use Theme-Aware Classes

```tsx
// ✅ Good - uses theme variables and dark mode classes
<div className="bg-container-background-color dark-theme:bg-container-dark-background">
  <p className="text-text-primary dark-theme:text-text-primary-dark">
    Content that adapts to theme
  </p>
</div>

// ❌ Bad - hardcoded colors
<div className="bg-white dark:bg-gray-800">
  <p className="text-black dark:text-white">Content</p>
</div>
```

## Accessibility Standards

### Always Provide Dialog Descriptions

```tsx
// ✅ Good - accessible
<Dialog open={isOpen} onOpenChange={setIsOpen}>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Delete Project</DialogTitle>
      <DialogDescription>
        This will permanently delete your project and all associated data.
        This action cannot be undone.
      </DialogDescription>
    </DialogHeader>
    {/* content */}
  </DialogContent>
</Dialog>

// ❌ Bad - missing description
<Dialog open={isOpen} onOpenChange={setIsOpen}>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Delete Project</DialogTitle>
    </DialogHeader>
    {/* content */}
  </DialogContent>
</Dialog>
```

### Use Proper Labels for Form Inputs

```tsx
// ✅ Good - proper label association
<div className="space-y-2">
  <Label htmlFor="email">Email Address</Label>
  <Input 
    id="email"
    type="email"
    placeholder="your@email.com"
    aria-describedby="email-description"
  />
  <p id="email-description" className="text-sm text-text-muted">
    We'll never share your email.
  </p>
</div>

// ❌ Bad - no label, no association
<div>
  <span>Email</span>
  <Input type="email" placeholder="your@email.com" />
</div>
```

### Maintain Keyboard Navigation

```tsx
// ✅ Good - maintains proper tab order
<DialogFooter>
  <Button 
    variant="outline" 
    onClick={handleCancel}
    tabIndex={0}
  >
    Cancel
  </Button>
  <Button 
    variant="destructive"
    onClick={handleDelete}
    tabIndex={0}
  >
    Delete
  </Button>
</DialogFooter>

// ❌ Bad - breaks keyboard navigation
<div onClick={handleCancel}>Cancel</div>
<div onClick={handleDelete}>Delete</div>
```

### Provide Loading States

```tsx
// ✅ Good - clear loading indication
<Button disabled={isLoading}>
  {isLoading ? (
    <>
      <span className="animate-spin mr-2">⏳</span>
      Saving...
    </>
  ) : (
    'Save Project'
  )}
</Button>

// ❌ Bad - no loading feedback
<Button onClick={handleSave}>
  Save Project
</Button>
```

## TypeScript Usage

### Use Proper Type Definitions

```tsx
// ✅ Good - proper types
interface ProjectCardProps {
  project: {
    id: string;
    name: string;
    description?: string;
  };
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
}

const ProjectCard: React.FC<ProjectCardProps> = ({ project, onEdit, onDelete }) => {
  return (
    <Card>
      {/* component implementation */}
    </Card>
  );
};

// ❌ Bad - any types
const ProjectCard = ({ project, onEdit, onDelete }: any) => {
  // implementation
};
```

### Use ButtonProps for Extended Buttons

```tsx
import { ButtonProps } from '../components/ui/button';

// ✅ Good - extends ButtonProps
interface LoadingButtonProps extends ButtonProps {
  isLoading: boolean;
  loadingText?: string;
}

const LoadingButton: React.FC<LoadingButtonProps> = ({ 
  isLoading, 
  loadingText = 'Loading...',
  children,
  ...props 
}) => {
  return (
    <Button disabled={isLoading} {...props}>
      {isLoading ? loadingText : children}
    </Button>
  );
};
```

### Use Discriminated Unions for Variants

```tsx
// ✅ Good - type-safe variant handling
type AlertVariant = 'success' | 'error' | 'warning' | 'info';

interface AlertProps {
  variant: AlertVariant;
  title: string;
  message: string;
}

const getAlertStyles = (variant: AlertVariant): string => {
  switch (variant) {
    case 'success': return 'bg-green-50 text-green-800';
    case 'error': return 'bg-red-50 text-red-800';
    case 'warning': return 'bg-yellow-50 text-yellow-800';
    case 'info': return 'bg-blue-50 text-blue-800';
  }
};
```

## Testing Practices

### Test Component Rendering

```tsx
import { render, screen } from '@testing-library/react';
import { Button } from '../components/ui/button';

describe('Button', () => {
  it('renders with correct text', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button')).toHaveTextContent('Click me');
  });

  it('handles click events', () => {
    const handleClick = jest.fn();
    render(<Button onClick={handleClick}>Click me</Button>);
    
    screen.getByRole('button').click();
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('respects disabled state', () => {
    render(<Button disabled>Disabled</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
```

### Test Dialog Interactions

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('DeleteModal', () => {
  it('opens and closes correctly', async () => {
    const user = userEvent.setup();
    render(<DeleteModal />);
    
    // Open dialog
    await user.click(screen.getByText('Delete'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    
    // Close dialog
    await user.click(screen.getByText('Cancel'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('calls onConfirm when confirmed', async () => {
    const handleConfirm = jest.fn();
    const user = userEvent.setup();
    
    render(<DeleteModal onConfirm={handleConfirm} />);
    await user.click(screen.getByText('Delete'));
    await user.click(screen.getByText('Confirm'));
    
    expect(handleConfirm).toHaveBeenCalled();
  });
});
```

## Common Patterns

### Confirmation Dialog Pattern

```tsx
interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  description: string;
  onConfirm: () => void;
  onCancel: () => void;
  variant?: 'destructive' | 'default';
}

const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  title,
  description,
  onConfirm,
  onCancel,
  variant = 'default'
}) => {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button 
            variant={variant === 'destructive' ? 'destructive' : 'default'}
            onClick={() => {
              onConfirm();
              onCancel();
            }}
          >
            Confirm
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

### Form with Validation Pattern

```tsx
import { useState } from 'react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { cn } from '../lib/utils';

interface FormData {
  name: string;
  email: string;
}

interface FormErrors {
  name?: string;
  email?: string;
}

const ProjectForm = () => {
  const [formData, setFormData] = useState<FormData>({ name: '', email: '' });
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const validate = (): boolean => {
    const newErrors: FormErrors = {};
    
    if (!formData.name.trim()) {
      newErrors.name = 'Name is required';
    }
    
    if (!formData.email.includes('@')) {
      newErrors.email = 'Valid email is required';
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validate()) return;
    
    setIsSubmitting(true);
    try {
      // Submit form
      await submitForm(formData);
    } catch (error) {
      setErrors({ name: 'Submission failed' });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="name">Name</Label>
        <Input
          id="name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          className={cn(errors.name && "border-red-500")}
        />
        {errors.name && (
          <p className="text-sm text-red-500">{errors.name}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          value={formData.email}
          onChange={(e) => setFormData({ ...formData, email: e.target.value })}
          className={cn(errors.email && "border-red-500")}
        />
        {errors.email && (
          <p className="text-sm text-red-500">{errors.email}</p>
        )}
      </div>

      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Submitting...' : 'Submit'}
      </Button>
    </form>
  );
};
```

### List with Actions Pattern

```tsx
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';

interface Project {
  id: string;
  name: string;
  description: string;
  updatedAt: string;
}

interface ProjectListProps {
  projects: Project[];
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
  onView: (id: string) => void;
}

const ProjectList: React.FC<ProjectListProps> = ({ projects, onEdit, onDelete, onView }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {projects.map((project) => (
        <Card key={project.id}>
          <CardHeader>
            <CardTitle>{project.name}</CardTitle>
            <CardDescription>{project.description}</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-text-muted">
              Updated: {new Date(project.updatedAt).toLocaleDateString()}
            </p>
          </CardContent>
          <CardFooter className="flex gap-2">
            <Button 
              variant="outline" 
              size="sm"
              onClick={() => onView(project.id)}
            >
              View
            </Button>
            <Button 
              variant="outline" 
              size="sm"
              onClick={() => onEdit(project.id)}
            >
              Edit
            </Button>
            <Button 
              variant="destructive" 
              size="sm"
              onClick={() => onDelete(project.id)}
            >
              Delete
            </Button>
          </CardFooter>
        </Card>
      ))}
    </div>
  );
};
```

## Anti-Patterns to Avoid

### ❌ Don't Mix Styling Approaches

```tsx
// ❌ Bad - mixing inline styles, custom classes, and Tailwind
<Button 
  className="custom-button-class"
  style={{ backgroundColor: 'blue' }}
>
  <span className="text-white">Click me</span>
</Button>

// ✅ Good - consistent Tailwind/shadcn approach
<Button variant="default">
  Click me
</Button>
```

### ❌ Don't Bypass Component APIs

```tsx
// ❌ Bad - bypassing Dialog API
<div className="fixed inset-0 bg-black/50" onClick={handleClose}>
  <div className="bg-white p-4">
    {/* custom modal */}
  </div>
</div>

// ✅ Good - using proper Dialog component
<Dialog open={isOpen} onOpenChange={setIsOpen}>
  <DialogContent>
    {/* content */}
  </DialogContent>
</Dialog>
```

### ❌ Don't Ignore Accessibility

```tsx
// ❌ Bad - not accessible
<div onClick={handleClick}>Submit</div>

// ✅ Good - proper button
<Button onClick={handleClick}>Submit</Button>
```

### ❌ Don't Create Duplicate Components

```tsx
// ❌ Bad - custom button that duplicates shadcn Button
const MyButton = ({ children, onClick }) => {
  return (
    <button 
      className="px-4 py-2 bg-blue-500 text-white rounded"
      onClick={onClick}
    >
      {children}
    </button>
  );
};

// ✅ Good - use shadcn Button or extend it
import { Button } from '../components/ui/button';
// Use directly or create variant if needed
```

### ❌ Don't Over-Customize

```tsx
// ❌ Bad - fighting the component system
<Button 
  className="!bg-purple-500 !text-yellow-300 !border-green-400 !rounded-none"
>
  Weird Button
</Button>

// ✅ Good - work with the system or create a proper variant
<Button variant="secondary">
  Normal Button
</Button>
```

## Summary Checklist

When working with shadcn/ui components:

- ✅ Use relative imports (`../components/ui/...`)
- ✅ Use semantic component composition (CardHeader, DialogTitle, etc.)
- ✅ Use semantic button variants (`destructive`, `outline`, etc.)
- ✅ Use `cn()` utility for class merging
- ✅ Prefer Tailwind utilities over inline styles
- ✅ Always provide Dialog descriptions for accessibility
- ✅ Use proper Label components for form inputs
- ✅ Maintain keyboard navigation and focus management
- ✅ Provide loading states and feedback
- ✅ Write proper TypeScript types
- ✅ Test component rendering and interactions
- ✅ Use established patterns (confirmation dialogs, forms, lists)
- ❌ Don't mix styling approaches
- ❌ Don't bypass component APIs
- ❌ Don't ignore accessibility
- ❌ Don't create duplicate components
- ❌ Don't over-customize with !important

Following these practices will ensure a consistent, accessible, and maintainable UI across the Actions Manager application.
