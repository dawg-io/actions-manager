# TypeScript Development Guide

## Overview

TypeScript support has been enabled in the React frontend project to allow gradual migration from JavaScript to TypeScript. This document explains how to work with TypeScript components and gradually migrate existing components.

## Setup

TypeScript is now configured with the following dependencies:

- `typescript`: Core TypeScript compiler (version 4.9.5 for compatibility with react-scripts 5.0.1)
- `@types/react`: Type definitions for React
- `@types/react-dom`: Type definitions for React DOM
- `@typescript-eslint/parser`: ESLint parser for TypeScript
- `@typescript-eslint/eslint-plugin`: ESLint plugin for TypeScript rules

### Version Compatibility

The project uses TypeScript 4.9.5 to maintain compatibility with `react-scripts@5.0.1`, which requires TypeScript `^3.2.1 || ^4`. This ensures that Docker builds and CI/CD pipelines work without dependency conflicts.

## Configuration

### tsconfig.json
The project uses a strict TypeScript configuration with the following key settings:

```json
{
  "compilerOptions": {
    "target": "es2015",
    "strict": true,
    "jsx": "react-jsx",
    "downlevelIteration": true
  }
}
```

### ESLint Configuration
ESLint has been configured to handle TypeScript files through package.json overrides:

```json
{
  "eslintConfig": {
    "overrides": [
      {
        "files": ["**/*.ts", "**/*.tsx"],
        "parser": "@typescript-eslint/parser",
        "plugins": ["@typescript-eslint"]
      }
    ]
  }
}
```

## Adding New TypeScript Components

### 1. Create .tsx Files
Create new React components with `.tsx` extension instead of `.jsx`:

```typescript
// components/MyComponent.tsx
import React from 'react';

interface MyComponentProps {
  title: string;
  count?: number;
  onUpdate: (value: string) => void;
}

const MyComponent: React.FC<MyComponentProps> = ({ title, count = 0, onUpdate }) => {
  const handleClick = () => {
    onUpdate(`Updated: ${title}`);
  };

  return (
    <div>
      <h2>{title}</h2>
      <p>Count: {count}</p>
      <button onClick={handleClick}>Update</button>
    </div>
  );
};

export default MyComponent;
```

### 2. Define Interfaces
Use TypeScript interfaces to define component props and data structures:

```typescript
interface User {
  id: number;
  name: string;
  email?: string;
}

interface UserListProps {
  users: User[];
  onUserSelect: (user: User) => void;
}
```

### 3. Type Event Handlers
Properly type event handlers:

```typescript
const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
  setValue(e.target.value);
};

const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
  e.preventDefault();
  // Handle form submission
};
```

## Migrating Existing Components

### Step-by-Step Migration

1. **Rename the file**: Change `.js` or `.jsx` to `.tsx`
2. **Add TypeScript types**: Define interfaces for props
3. **Remove PropTypes**: Replace with TypeScript interfaces
4. **Type state and variables**: Add explicit types where needed
5. **Fix type errors**: Address any TypeScript compilation errors

### Example Migration

**Before (JavaScript)**:
```javascript
import PropTypes from 'prop-types';

const EnvVars = ({ user, projectName, selectedRepos, envVars, setEnvVars }) => {
  // Component logic
};

EnvVars.propTypes = {
  user: PropTypes.string,
  projectName: PropTypes.string,
  selectedRepos: PropTypes.array,
  envVars: PropTypes.array,
  setEnvVars: PropTypes.func
};
```

**After (TypeScript)**:
```typescript
interface EnvVar {
  env_key: string;
  value?: string;
  repo: string;
}

interface EnvVarsProps {
  user?: string;
  projectName?: string;
  selectedRepos?: string[];
  envVars?: EnvVar[];
  setEnvVars?: (envVars: EnvVar[] | ((prev: EnvVar[]) => EnvVar[])) => void;
}

const EnvVars: React.FC<EnvVarsProps> = ({ user, projectName, selectedRepos, envVars, setEnvVars }) => {
  // Component logic
};
```

## Common TypeScript Patterns

### Optional Props
```typescript
interface ComponentProps {
  required: string;
  optional?: number;
}
```

### Union Types
```typescript
interface Status {
  type: 'loading' | 'success' | 'error';
  message?: string;
}
```

### Function Props
```typescript
interface Props {
  onClick: () => void;
  onUpdate: (value: string) => void;
  onSelect: (item: Item) => Promise<void>;
}
```

### Generic Types
```typescript
interface ApiResponse<T> {
  data: T;
  success: boolean;
  message?: string;
}
```

## Building and Testing

### Development
```bash
npm start
```
TypeScript files are compiled automatically by react-scripts during development.

### Production Build
```bash
CI=false npm run build
```
The build process includes TypeScript compilation and type checking.

### Type Checking
```bash
npx tsc --noEmit
```
Run type checking without emitting files to catch TypeScript errors.

## Best Practices

1. **Start with interfaces**: Define clear interfaces for all props and data structures
2. **Use strict mode**: Keep strict TypeScript settings enabled
3. **Avoid `any` type**: Use specific types or `unknown` when type is unclear
4. **Type external libraries**: Create `.d.ts` files for untyped libraries
5. **Gradual migration**: Convert components one at a time
6. **Test thoroughly**: Ensure TypeScript components work correctly after conversion

## Troubleshooting

### Common Issues

**Map iteration errors**: Use `Array.from()` instead of spread operator for Map values:
```typescript
// Instead of: [...map.values()]
Array.from(map.values())
```

**Import errors**: Ensure proper import/export syntax:
```typescript
// Named exports
export { ComponentA, ComponentB };

// Default export
export default Component;

// Import
import Component, { namedExport } from './module';
```

**Type declaration files**: Create `.d.ts` files for JavaScript modules without types:
```typescript
// utils/copyUtils.d.ts
export interface CopyButtonProps {
  textToCopy: string;
  className?: string;
  title?: string;
}

export const CopyButton: React.FC<CopyButtonProps>;
```

## Resources

- [TypeScript Documentation](https://www.typescriptlang.org/docs/)
- [React TypeScript Cheatsheet](https://react-typescript-cheatsheet.netlify.app/)
- [TypeScript ESLint Rules](https://typescript-eslint.io/rules/)