# shadcn/ui Integration & Migration Plan

## Recent Migrations

### ✅ Phase 1 Complete: Core Components Migrated (January 2025)

The following components have been successfully migrated to shadcn/ui:

#### UserAvatar Component ✅
**Date**: December 2024

- ✅ Replaced custom dropdown implementation with `DropdownMenu` component from shadcn/ui
- ✅ Migrated avatar display to use `Avatar`, `AvatarImage`, and `AvatarFallback` components
- ✅ Integrated Lucide React icons (`ChevronDown`, `Sun`, `Moon`, `LogOut`)
- ✅ Removed manual click-outside and escape key handling (now handled by Radix UI)
- ✅ Maintained all existing functionality: theme toggle, logout, account info, rate limit display
- ✅ Updated all tests to work with new component structure
- ✅ Removed 315+ lines of custom CSS from `projectMgmt.css`

#### Modal Components ✅
**Date**: January 2025

- ✅ **DeleteProjectModal**: Now uses `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogFooter` from shadcn/ui
- ✅ **SaveResultsModal**: Fully migrated to shadcn/ui Dialog with proper semantic structure
- ✅ **WorkflowCreationDialog**: Migrated to shadcn/ui Dialog components
- ✅ **TemplateSelectionModal**: Using shadcn/ui Dialog and Button components
- ✅ Removed 1,187 lines of unused CSS (DeleteProjectModal.css, SaveResultsModal.css, AIWorkflowChat.css)

#### Card Components ✅
**Date**: January 2025

- ✅ **ProjectList**: Using shadcn/ui `Card`, `CardHeader`, `CardTitle`, `CardContent`, `CardFooter`
- ✅ **WorkflowsList**: Migrated to shadcn/ui Card components with collapse functionality
- ✅ All card components now use consistent styling and semantic structure

#### Button Components ✅
**Date**: January 2025

- ✅ **CreateRepo**: Using shadcn/ui `Button` component
- ✅ Most action buttons across the app now use shadcn/ui Button with proper variants

**Benefits:**
- **Better Accessibility**: Radix UI primitives provide WAI-ARIA compliant behavior
- **Cleaner Code**: Reduced complexity and improved maintainability
- **Consistent Styling**: Uses Tailwind CSS classes matching the rest of the application
- **Less Maintenance**: No need to maintain custom dialog and button logic
- **Better UX**: Smooth animations and proper focus management out of the box
- **Smaller Bundle**: Removed ~1,500 lines of CSS that are no longer needed

## Overview

This document outlines the integration of shadcn/ui into the Actions Manager project and provides a comprehensive plan for migrating existing custom UI components to shadcn/ui components.

## What is shadcn/ui?

shadcn/ui is a collection of re-usable components built using Radix UI primitives and styled with Tailwind CSS. Unlike traditional component libraries, shadcn/ui components are copied directly into your project, giving you full control and ownership over the code.

### Key Benefits

- **Full Control**: Components are copied into your codebase, not installed as dependencies
- **Customizable**: Built with Tailwind CSS and CSS variables for easy theming
- **Accessible**: Built on Radix UI primitives with WAI-ARIA compliant components
- **Type-Safe**: Written in TypeScript with full type support
- **Modern**: Uses React hooks and modern patterns
- **Dark Mode**: Built-in dark mode support using CSS variables

## Installation & Setup

### Dependencies Installed

The following packages have been installed to support shadcn/ui:

```json
{
  "dependencies": {
    "class-variance-authority": "^latest",
    "clsx": "^latest",
    "tailwind-merge": "^latest",
    "lucide-react": "^latest",
    "@radix-ui/react-slot": "^latest",
    "@radix-ui/react-dialog": "^latest",
    "@radix-ui/react-dropdown-menu": "^latest"
  }
}
```

### Configuration Files

1. **`components.json`**: shadcn/ui configuration
2. **`tsconfig.json`**: Updated with path aliases (`@/*` → `./src/*`)
3. **`tailwind.config.js`**: Enhanced with animations and keyframes
4. **`src/lib/utils.ts`**: Utility functions for class merging

## Available Components

### Base Components Scaffolded

The following shadcn/ui components have been implemented:

1. **Avatar** (`src/components/ui/avatar.tsx`) ✅
   - Components: Avatar, AvatarImage, AvatarFallback
   - Automatically falls back to initials when image fails to load
   - Fully responsive and accessible

2. **Button** (`src/components/ui/button.tsx`)
   - Variants: default, destructive, outline, secondary, ghost, link
   - Sizes: default, sm, lg, icon
   - Full dark mode support

3. **Card** (`src/components/ui/card.tsx`)
   - Components: Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter
   - Fully styled and responsive

4. **Dialog** (`src/components/ui/dialog.tsx`)
   - Components: Dialog, DialogTrigger, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription
   - Modal overlay with animations
   - Accessible with keyboard navigation

5. **DropdownMenu** (`src/components/ui/dropdown-menu.tsx`) ✅
   - Components: DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, etc.
   - Full menu system with submenus, checkboxes, radio items
   - Keyboard navigation support
   - Used in UserAvatar component

## Migration Strategy

### ✅ Phase 1: Foundation (COMPLETED)
- [x] Install shadcn/ui dependencies
- [x] Configure path aliases
- [x] Create utility functions
- [x] Scaffold base components (Button, Card, Dialog, DropdownMenu, Avatar, Input, Label, Select, Checkbox)
- [x] Document migration plan

### Phase 2: Replace Custom Buttons ✅ COMPLETED
**Completed Components:**
- ✅ `CreateRepo.tsx` - Using shadcn/ui Button
- ✅ `DeleteProjectModal.tsx` - Using shadcn/ui Button with destructive variant
- ✅ `SaveResultsModal.tsx` - Using shadcn/ui Button components
- ✅ `ProjectList.tsx` - Using shadcn/ui Button components
- ✅ `WorkflowsList.tsx` - Using shadcn/ui Button components

**Remaining Work:**
- Some complex components still use `<button>` elements (EventPicker, GUIWorkflowEditor, etc.)
- These components have specialized interactions and can be migrated as needed during future updates

### Phase 3: Replace Custom Modals ✅ COMPLETED
**Completed Components:**
- ✅ `DeleteProjectModal.tsx` - Fully migrated to shadcn/ui Dialog
- ✅ `SaveResultsModal.tsx` - Fully migrated to shadcn/ui Dialog
- ✅ `WorkflowCreationDialog.tsx` - Using shadcn/ui Dialog
- ✅ `TemplateSelectionModal.tsx` - Using shadcn/ui Dialog

**CSS Cleanup:**
- ✅ Removed `DeleteProjectModal.css` (420 lines)
- ✅ Removed `SaveResultsModal.css` (326 lines)
- ✅ Removed `AIWorkflowChat.css` (438 lines)

### Phase 4: Replace Custom Cards ✅ COMPLETED
### Phase 4: Replace Custom Cards ✅ COMPLETED
**Completed Components:**
- ✅ `ProjectList.tsx` - Using shadcn/ui Card components
- ✅ `WorkflowsList.tsx` - Using shadcn/ui Card components
- ✅ `JobCard.tsx` - Using shadcn/ui components where applicable

**Status:**
All primary card-based components have been migrated. Some specialized cards in complex editors remain but use consistent styling patterns.

### Phase 5: Component-Specific Replacements (OPTIONAL - FUTURE WORK)

The following components still use custom CSS but are **not required** for this migration:

**Complex Components (OK to keep custom CSS):**
- `GUIWorkflowEditor.tsx` - Specialized workflow editor with custom interactions
- `EventPicker.tsx` - Complex form with dynamic fields
- `ReusableEventPicker.tsx` - Similar to EventPicker
- `StepCard.tsx` - Workflow step editor with many custom controls
- `JobCard.tsx` - Partially migrated, some custom controls remain

**Specialized Components (OK to keep custom CSS):**
- `Sidebar.tsx` - Navigation sidebar with unique layout (mostly Tailwind already)
- `YAMLEditor.tsx` - Monaco editor wrapper with custom styling
- `RulesetManager.tsx` - Repository ruleset management UI
- `UnifiedWorkflows.tsx` - Complex workflow management interface

**Remaining CSS Files (Justified):**
- `GUIWorkflowEditor.css` (829 lines) - Complex editor styles
- `Sidebar.css` (289 lines) - Navigation-specific styles
- `YAMLEditor.css` (305 lines) - Monaco editor customization
- `RulesetManager.css` (481 lines) - Specialized ruleset UI
- `UnifiedWorkflows.css` (789 lines) - Workflow management UI
- `WorkflowsList.css` (603 lines) - Some specialized workflow list features
- `TemplateModal.css` (166 lines) - Template selection styling
- `projectMgmt.css` (1,591 lines) - General project management styles
- `driftDetection.css` (252 lines) - Drift detection UI

**Future Components to Consider Adding:**
- **Toast**: For temporary notifications (when needed)
- **Tooltip**: For hover information (when needed)
- **Tabs**: For tabbed interfaces (when needed)
- **Accordion**: For collapsible sections (when needed)
- **Alert**: For notification messages (when needed)
- **Badge**: For status indicators (when needed)
- **Switch**: For toggle controls (when needed)

**Note**: These components should be added **as needed** when implementing new features, not proactively.

## Component Upgrade Process

### Adding New shadcn/ui Components

When you need a new shadcn/ui component:

1. **Install the component** (if using CLI):
   ```bash
   npx shadcn-ui@latest add [component-name]
   ```

2. **Manual addition** (recommended for this project):
   - Copy component code from [ui.shadcn.com](https://ui.shadcn.com)
   - Place in `src/components/ui/[component-name].tsx`
   - Update imports to use project's theme colors
   - Add to `src/components/ui/index.ts` for easier imports

3. **Install required Radix UI dependencies**:
   ```bash
   npm install --legacy-peer-deps @radix-ui/react-[component]
   ```

4. **Test the component**:
   - Verify light/dark theme support
   - Test accessibility (keyboard navigation, screen readers)
   - Check responsive behavior

### Customizing Components

All shadcn/ui components can be customized:

1. **Modify variants in component file**:
   ```tsx
   const buttonVariants = cva(
     "base-classes",
     {
       variants: {
         variant: {
           custom: "your-custom-classes"
         }
       }
     }
   )
   ```

2. **Extend Tailwind config** for project-specific colors:
   - Already configured with existing color palette
   - Dark mode support via `.dark-theme` class

3. **Override styles** using className prop:
   ```tsx
   <Button className="custom-override-classes">
     Click me
   </Button>
   ```

## Migration Testing Checklist

For each migrated component:

- [ ] Visual appearance matches or improves on original
- [ ] All interactive states work (hover, focus, active, disabled)
- [ ] Dark mode styling is correct
- [ ] Keyboard navigation works
- [ ] Screen reader accessibility maintained
- [ ] Component tests updated and passing
- [ ] No console errors or warnings
- [ ] Responsive behavior on mobile/tablet/desktop

## Best Practices

### Import Pattern
```tsx
// Preferred: Relative imports from components/ui
import { Button, Card, Dialog } from '../ui/button';
import { Card } from '../ui/card';
import { Dialog } from '../ui/dialog';

// Alternative: Individual imports
import { Button } from '../ui/button';
```

**Note**: Due to Create React App limitations, we use relative imports instead of path aliases. If you eject or use a custom webpack config, you can configure `@/` path aliases.

### Styling Pattern
```tsx
// Use cn() utility for class merging
import { cn } from '../../lib/utils'

<Button className={cn("custom-class", isActive && "active-class")}>
  Click me
</Button>
```

### Variant Usage
```tsx
// Use semantic variants
<Button variant="destructive">Delete</Button>
<Button variant="outline">Cancel</Button>
<Button variant="ghost">Dismiss</Button>
```

### Composition Pattern
```tsx
// Build complex UIs by composing components
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Description</CardDescription>
  </CardHeader>
  <CardContent>
    Content here
  </CardContent>
  <CardFooter>
    <Button variant="outline">Cancel</Button>
    <Button>Save</Button>
  </CardFooter>
</Card>
```

## Current Component Inventory

### ✅ Successfully Migrated Components

| Component | Type | Target shadcn Component | Status | Notes |
|-----------|------|------------------------|--------|-------|
| UserAvatar | Avatar + Dropdown | Avatar + DropdownMenu | ✅ **COMPLETED** | Fully migrated with all functionality |
| DeleteProjectModal | Modal | Dialog | ✅ **COMPLETED** | Using Dialog with destructive buttons |
| SaveResultsModal | Modal | Dialog | ✅ **COMPLETED** | Full Dialog implementation |
| WorkflowCreationDialog | Modal | Dialog | ✅ **COMPLETED** | Workflow creation flow with Dialog |
| TemplateSelectionModal | Modal | Dialog | ✅ **COMPLETED** | Template picker with Dialog |
| CreateRepo | Button | Button | ✅ **COMPLETED** | Using shadcn Button |
| ProjectList | Cards | Card | ✅ **COMPLETED** | Grid of project cards |
| WorkflowsList | Cards | Card | ✅ **COMPLETED** | Workflow display cards |

### 🔧 Partially Migrated Components

| Component | Status | Notes |
|-----------|--------|-------|
| JobCard | 🟡 Partial | Uses some shadcn components, retains custom controls |
| Sidebar | 🟡 Partial | Mostly Tailwind, some custom CSS for layout |

### 📦 Components with Custom CSS (OK to Keep)

| Component | CSS File | Lines | Justification |
|-----------|----------|-------|---------------|
| GUIWorkflowEditor | GUIWorkflowEditor.css | 829 | Complex editor with specialized interactions |
| EventPicker | GUIWorkflowEditor.css | (shared) | Dynamic form with complex state management |
| ReusableEventPicker | GUIWorkflowEditor.css | (shared) | Similar to EventPicker |
| StepCard | GUIWorkflowEditor.css | (shared) | Workflow step editor |
| YAMLEditor | YAMLEditor.css | 305 | Monaco editor wrapper |
| RulesetManager | RulesetManager.css | 481 | Specialized ruleset management |
| UnifiedWorkflows | UnifiedWorkflows.css | 789 | Complex workflow interface |
| Sidebar | Sidebar.css | 289 | Navigation sidebar layout |
| Workflows | WorkflowsList.css | 603 | Specialized workflow features |
| RXWorkflows | TemplateModal.css | 166 | Template selection |
| ProjectMgmt | projectMgmt.css | 1,591 | General project styles |
| DriftDetection | driftDetection.css | 252 | Drift detection UI |

**Total Custom CSS Remaining**: ~5,302 lines (justified for specialized components)
**CSS Removed**: ~1,187 lines (DeleteProjectModal.css, SaveResultsModal.css, AIWorkflowChat.css)

## File Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/                    # shadcn/ui components
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── dialog.tsx
│   │   │   ├── dropdown-menu.tsx
│   │   │   └── index.ts           # Barrel export
│   │   ├── [existing components] # To be migrated gradually
│   │   └── ...
│   ├── lib/
│   │   └── utils.ts               # Utility functions
│   └── ...
├── components.json                # shadcn/ui config
├── tailwind.config.js             # Enhanced Tailwind config
└── tsconfig.json                  # Path aliases configured
```

## Next Steps

### Current Status: ✅ Core Migration Complete

The primary shadcn/ui migration is now **COMPLETE**. The following have been achieved:

1. ✅ **Core components migrated**: All major modals, cards, and buttons are using shadcn/ui
2. ✅ **Unused CSS removed**: Deleted 1,187 lines of deprecated CSS
3. ✅ **Documentation created**: Comprehensive guides for developers
4. ✅ **Consistent styling**: All migrated components use uniform design system
5. ✅ **Accessibility improved**: Better keyboard navigation and screen reader support

### Optional Future Enhancements

These are **NOT required** but can be done opportunistically:

1. **Add components as needed**: When implementing new features, consider adding Toast, Tooltip, Tabs, etc.
2. **Gradually migrate complex components**: EventPicker, GUIWorkflowEditor can be refactored during feature work
3. **Consolidate CSS**: Consider moving shared styles from projectMgmt.css to Tailwind utilities
4. **Update tests**: Ensure all migrated components have comprehensive test coverage

### For New Features

When building new UI features:
- ✅ Use shadcn/ui components from `components/ui/`
- ✅ Follow patterns in migrated components (ProjectList, DeleteProjectModal)
- ✅ Refer to `SHADCN_UI_ONBOARDING.md` for guidelines
- ✅ Use semantic variants and compose components properly

## Resources

- [shadcn/ui Documentation](https://ui.shadcn.com)
- [Radix UI Primitives](https://www.radix-ui.com/primitives)
- [Tailwind CSS Documentation](https://tailwindcss.com)
- [class-variance-authority](https://cva.style/docs)

## Troubleshooting

### Import Errors
If you see "Cannot find module '@/components/ui/button'":
- Ensure tsconfig.json has `baseUrl: "."` and `paths: { "@/*": ["./src/*"] }`
- Restart your development server
- Clear TypeScript cache

### Styling Issues
If components don't look right:
- Verify Tailwind CSS is processing the files
- Check that CSS variables are defined in index.css
- Ensure dark-theme class is applied for dark mode

### Type Errors
If TypeScript shows errors:
- Ensure all Radix UI packages are installed
- Check that component props match the interface
- Verify import paths are correct

## Conclusion

This integration provides a solid foundation for modernizing the UI with accessible, customizable, and well-tested components. The migration can be done incrementally without disrupting existing functionality.
