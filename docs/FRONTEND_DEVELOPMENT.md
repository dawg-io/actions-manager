# Frontend Development Guide

This guide covers frontend development for Actions Manager, including React, TypeScript, Tailwind CSS, component patterns, and migration guides.

## Table of Contents

- [Technology Stack](#technology-stack)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [TypeScript Development](#typescript-development)
- [Styling with Tailwind CSS](#styling-with-tailwind-css)
- [Component Patterns](#component-patterns)
- [State Management](#state-management)
- [API Integration](#api-integration)
- [Testing](#testing)
- [Migration Guides](#migration-guides)
- [Best Practices](#best-practices)

## Technology Stack

### Core Technologies

- **React 19** - UI framework with hooks and functional components
- **TypeScript 4.9.5** - Type safety (gradual migration in progress)
- **Tailwind CSS v3** - Utility-first CSS framework
- **React Router** - Client-side routing
- **CodeMirror 6** - Code editor for YAML workflow editing
- **Axios** - HTTP client for API calls

### Development Tools

- **Create React App** - Build tooling
- **ESLint** - Code linting
- **Prettier** - Code formatting (optional)
- **VS Code** - Recommended editor with TypeScript and Tailwind extensions

## Getting Started

### Prerequisites

- Node.js 16+
- npm 7+
- Backend running on port 8000

### Installation

```bash
cd frontend
npm install  # Takes 12-13 minutes - be patient!
```

### Development Server

```bash
npm start
```

Application runs on `http://localhost:3000`

### Production Build

```bash
# Always use CI=false to allow ESLint warnings
CI=false npm run build
```

## Project Structure

```
frontend/
├── public/                    # Static assets
│   ├── index.html            # HTML template
│   └── favicon.ico           # Favicon
│
├── src/
│   ├── App.js                # Main application component
│   ├── index.js              # Entry point
│   ├── index.css             # Global styles + Tailwind
│   │
│   ├── components/           # React components
│   │   ├── ProjectsView.js   # Project management UI
│   │   ├── WorkflowEditor.js # Workflow editing
│   │   ├── UserAvatar.tsx    # User avatar (TypeScript)
│   │   └── ...               # Other components
│   │
│   ├── api/                  # API integration
│   │   ├── projects.js       # Project API calls
│   │   ├── workflows.js      # Workflow API calls
│   │   └── ...               # Other API modules
│   │
│   ├── contexts/             # React contexts
│   │   ├── ThemeContext.tsx  # Theme management
│   │   └── UserContext.js    # User state
│   │
│   └── utils/                # Utility functions
│       └── ...
│
├── package.json              # Dependencies
├── tailwind.config.js        # Tailwind configuration
├── postcss.config.js         # PostCSS configuration
└── tsconfig.json             # TypeScript configuration
```

## TypeScript Development

### Overview

TypeScript support is enabled for gradual migration from JavaScript to TypeScript. New components should use TypeScript; existing components can be migrated incrementally.

### Configuration

**TypeScript Version:** 4.9.5

**tsconfig.json highlights:**
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "strict": true,
    "jsx": "react-jsx",
    "downlevelIteration": true,
    "lib": ["dom", "dom.iterable", "ES2020"],
    "allowJs": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true
  }
}
```

Vite client types (including `import.meta.env`) are declared in `src/vite-env.d.ts`.

### Creating TypeScript Components

**Functional Component Example:**

```typescript
import React, { useState, useEffect } from 'react';

interface UserAvatarProps {
  username: string;
  size?: 'small' | 'medium' | 'large';
  showName?: boolean;
}

const UserAvatar: React.FC<UserAvatarProps> = ({ 
  username, 
  size = 'medium',
  showName = true 
}) => {
  const [avatarUrl, setAvatarUrl] = useState<string>('');

  useEffect(() => {
    // Fetch avatar
    fetchAvatar(username).then(setAvatarUrl);
  }, [username]);

  return (
    <div className="flex items-center gap-2">
      <img 
        src={avatarUrl} 
        alt={username}
        className={`rounded-full ${getSizeClass(size)}`}
      />
      {showName && <span>{username}</span>}
    </div>
  );
};

export default UserAvatar;
```

### Type Definitions

**Common types:**

```typescript
// API Response types
interface Project {
  id: number;
  name: string;
  description: string;
  repositories: Repository[];
}

interface Repository {
  id: number;
  name: string;
  full_name: string;
  private: boolean;
}

interface Workflow {
  id: number;
  name: string;
  content: string;
  repository_id: number;
}

// Component Props
interface ButtonProps {
  onClick: () => void;
  children: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
}
```

### Migration from JavaScript

To migrate a JavaScript component to TypeScript:

1. **Rename file** from `.js` to `.tsx`
2. **Add type annotations** for props and state
3. **Fix type errors** shown by TypeScript
4. **Test thoroughly**

Example migration:

```javascript
// Before (JavaScript)
const Button = ({ onClick, children, variant = 'primary' }) => {
  return (
    <button onClick={onClick} className={`btn btn-${variant}`}>
      {children}
    </button>
  );
};
```

```typescript
// After (TypeScript)
interface ButtonProps {
  onClick: () => void;
  children: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'danger';
}

const Button: React.FC<ButtonProps> = ({ 
  onClick, 
  children, 
  variant = 'primary' 
}) => {
  return (
    <button onClick={onClick} className={`btn btn-${variant}`}>
      {children}
    </button>
  );
};
```

## Styling with Tailwind CSS

### Overview

Tailwind CSS v3 is configured alongside existing CSS variables for gradual migration. Both styling approaches work during the transition period.

### Configuration

**tailwind.config.js** extends the default theme with custom colors matching the design system:

```javascript
module.exports = {
  darkMode: 'class',
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Custom colors from design system
        primary: 'var(--color-primary)',
        secondary: 'var(--color-secondary)',
        success: 'var(--color-success)',
        danger: 'var(--color-danger)',
        warning: 'var(--color-warning)',
        // Background colors
        background: 'var(--color-background)',
        container: 'var(--color-container)',
        // Text colors
        'text-primary': 'var(--color-text-primary)',
        'text-secondary': 'var(--color-text-secondary)',
      },
    },
  },
};
```

### Using Tailwind Classes

**Basic styling:**

```jsx
<div className="p-4 bg-white rounded-lg shadow-md">
  <h1 className="text-2xl font-bold text-gray-800">Title</h1>
  <p className="text-gray-600 mt-2">Description</p>
</div>
```

**Responsive design:**

```jsx
<div className="w-full md:w-1/2 lg:w-1/3">
  <div className="p-4 sm:p-6 md:p-8">
    Content adapts to screen size
  </div>
</div>
```

**Dark mode support:**

```jsx
<div className="bg-white dark:bg-gray-800">
  <p className="text-gray-900 dark:text-gray-100">
    Adapts to theme
  </p>
</div>
```

**Interactive states:**

```jsx
<button className="
  px-4 py-2 
  bg-blue-600 hover:bg-blue-700 
  text-white 
  rounded-md
  focus:outline-none focus:ring-2 focus:ring-blue-500
  disabled:opacity-50 disabled:cursor-not-allowed
">
  Click Me
</button>
```

### Custom Color Classes

Use design system colors:

```jsx
<div className="bg-primary text-white">Primary background</div>
<div className="bg-success text-white">Success background</div>
<div className="bg-danger text-white">Danger background</div>
<div className="text-text-primary">Primary text</div>
<div className="text-text-secondary">Secondary text</div>
```

### Migration from CSS Modules

**Before (CSS Module):**

```css
/* Button.module.css */
.button {
  padding: 0.5rem 1rem;
  background-color: var(--primary-color);
  color: white;
  border-radius: 0.375rem;
}

.button:hover {
  background-color: var(--primary-hover);
}
```

```jsx
import styles from './Button.module.css';

const Button = () => <button className={styles.button}>Click</button>;
```

**After (Tailwind):**

```jsx
const Button = () => (
  <button className="px-4 py-2 bg-primary hover:bg-primary-dark text-white rounded-md">
    Click
  </button>
);
```

## Component Patterns

### Functional Components with Hooks

Use functional components with hooks for all new components:

```jsx
import React, { useState, useEffect } from 'react';

const MyComponent = ({ initialValue }) => {
  const [value, setValue] = useState(initialValue);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Effect logic
    return () => {
      // Cleanup
    };
  }, [dependencies]);

  return <div>{value}</div>;
};
```

### Common Hooks

**useState:**
```jsx
const [count, setCount] = useState(0);
const [user, setUser] = useState(null);
```

**useEffect:**
```jsx
// Run once on mount
useEffect(() => {
  fetchData();
}, []);

// Run when dependencies change
useEffect(() => {
  updateData(userId);
}, [userId]);
```

**useContext:**
```jsx
import { useTheme } from './contexts/ThemeContext';

const MyComponent = () => {
  const { theme, toggleTheme } = useTheme();
  return <button onClick={toggleTheme}>{theme}</button>;
};
```

**useRef:**
```jsx
const inputRef = useRef(null);

const focusInput = () => {
  inputRef.current.focus();
};

return <input ref={inputRef} />;
```

### Conditional Rendering

```jsx
// Short circuit
{isLoggedIn && <UserMenu />}

// Ternary
{isLoading ? <Spinner /> : <Content />}

// Multiple conditions
{isLoggedIn ? (
  isAdmin ? <AdminPanel /> : <UserPanel />
) : (
  <LoginForm />
)}
```

### Lists and Keys

```jsx
const UserList = ({ users }) => (
  <ul>
    {users.map(user => (
      <li key={user.id}>
        {user.name}
      </li>
    ))}
  </ul>
);
```

## State Management

### Local Component State

Use `useState` for component-specific state:

```jsx
const [formData, setFormData] = useState({
  name: '',
  email: '',
});

const handleChange = (e) => {
  setFormData({
    ...formData,
    [e.target.name]: e.target.value,
  });
};
```

### Context API

For shared state across components:

**Creating a Context:**

```jsx
// contexts/UserContext.js
import React, { createContext, useState, useContext } from 'react';

const UserContext = createContext();

export const UserProvider = ({ children }) => {
  const [user, setUser] = useState(null);

  const login = (userData) => setUser(userData);
  const logout = () => setUser(null);

  return (
    <UserContext.Provider value={{ user, login, logout }}>
      {children}
    </UserContext.Provider>
  );
};

export const useUser = () => useContext(UserContext);
```

**Using the Context:**

```jsx
import { useUser } from './contexts/UserContext';

const Header = () => {
  const { user, logout } = useUser();

  return (
    <header>
      {user ? (
        <>
          <span>{user.name}</span>
          <button onClick={logout}>Logout</button>
        </>
      ) : (
        <button>Login</button>
      )}
    </header>
  );
};
```

## API Integration

### Axios Setup

API calls are organized by resource in the `api/` directory:

**Example API module:**

```javascript
// api/projects.js
import axios from 'axios';

const API_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

export const getProjects = async () => {
  const response = await axios.get(`${API_URL}/api/projects`, {
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('token')}`,
    },
  });
  return response.data;
};

export const createProject = async (projectData) => {
  const response = await axios.post(
    `${API_URL}/api/projects`,
    projectData,
    {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
      },
    }
  );
  return response.data;
};
```

### Using API in Components

```jsx
import { useState, useEffect } from 'react';
import { getProjects } from './api/projects';

const ProjectsList = () => {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchProjects = async () => {
      try {
        setLoading(true);
        const data = await getProjects();
        setProjects(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchProjects();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <ul>
      {projects.map(project => (
        <li key={project.id}>{project.name}</li>
      ))}
    </ul>
  );
};
```

## Testing

### Running Unit Tests

```bash
cd frontend
npm test
```

### Running E2E Tests (Playwright)

End-to-end tests live under `frontend/e2e/` and are executed by Playwright.
Phase 1 covers the core authentication, project, workflow-save, and PR
lifecycle flows. The suite mocks every backend and GitHub API call via
`page.route`, so it runs without the FastAPI service or live GitHub access.

```bash
cd frontend

# One-time browser install (downloads Chromium)
npx playwright install chromium

# Run the whole suite (auto-starts the React dev server on port 3000)
npm run test:e2e

# Run a single feature spec
npx playwright test e2e/auth.spec.ts

# Open the HTML report after a run
npx playwright show-report
```

The shared mocks and fixtures live in `frontend/e2e/fixtures/mocks.ts`;
extend that file when adding new tests so all specs share the same default
backend behaviour. Use `data-testid` attributes for any new selectors —
text-only matches are too brittle for the dashboard tables.

### Manual Testing Checklist

- [ ] Component renders correctly
- [ ] Props are handled correctly
- [ ] State updates work as expected
- [ ] API calls succeed/fail gracefully
- [ ] Error messages display correctly
- [ ] Loading states work
- [ ] Both light and dark themes work
- [ ] Responsive design works on mobile/tablet/desktop
- [ ] Accessibility (keyboard navigation, screen readers)

## Migration Guides

### Migrating Components to TypeScript

1. **Rename file** from `.js` to `.tsx`
2. **Define prop types** as interfaces
3. **Add type annotations** for state and variables
4. **Fix TypeScript errors**
5. **Test thoroughly**

See [TypeScript Development](#typescript-development) section for examples.

### Migrating Components to Tailwind

1. **Analyze existing CSS** - identify patterns
2. **Convert to Tailwind classes** - use utility classes
3. **Test in both themes** - light and dark
4. **Verify responsive behavior**
5. **Remove CSS imports** (keep files for reference)
6. **Document changes**

See [Styling with Tailwind CSS](#styling-with-tailwind-css) for examples.

## Best Practices

### Code Organization

- ✅ One component per file
- ✅ Group related components in subdirectories
- ✅ Keep components small and focused
- ✅ Extract reusable logic into hooks
- ✅ Separate API calls from components

### Naming Conventions

- **Components:** PascalCase (`UserAvatar.tsx`)
- **Hooks:** camelCase with `use` prefix (`useAuth.js`)
- **Utilities:** camelCase (`formatDate.js`)
- **Constants:** UPPER_SNAKE_CASE (`API_URL`)

### Props

- ✅ Use destructuring for props
- ✅ Provide default values where appropriate
- ✅ Use TypeScript interfaces for prop types
- ✅ Keep props minimal and focused

### Performance

- ✅ Use `React.memo` for expensive components
- ✅ Use `useMemo` for expensive computations
- ✅ Use `useCallback` for callbacks passed to children
- ✅ Lazy load routes and large components

### Accessibility

- ✅ Use semantic HTML elements
- ✅ Provide alt text for images
- ✅ Ensure keyboard navigation works
- ✅ Use ARIA labels where appropriate
- ✅ Test with screen readers

### Error Handling

- ✅ Use try-catch for async operations
- ✅ Display user-friendly error messages
- ✅ Log errors for debugging
- ✅ Provide fallback UI for errors

## Related Documentation

- **[Development Guide](DEVELOPMENT.md)** - General development setup
- **[Architecture](ARCHITECTURE.md)** - System architecture
- **[Troubleshooting](TROUBLESHOOTING.md)** - Common frontend issues
- **[Contributing](../CONTRIBUTING.md)** - Contribution guidelines

---

**Last Updated:** 2026-02-14  
**Version:** 1.0
