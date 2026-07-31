import React, { createContext, useContext, useState, useEffect } from 'react';

// Define the shape of the theme context value
interface ThemeContextValue {
  isDarkMode: boolean;
  toggleTheme: () => void;
}

// Define the props for ThemeProvider
interface ThemeProviderProps {
  children: React.ReactNode;
}

// Create context with proper typing
const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

export const useTheme = (): ThemeContextValue => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  const [isDarkMode, setIsDarkMode] = useState<boolean>(() => {
    // Check localStorage for saved theme preference
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
      return savedTheme === 'dark';
    }
    // No saved preference: dark mode is the application default for all new users.
    // This intentionally ignores the OS/system colour-scheme preference so that
    // the React state always agrees with the index.html bootstrap script, which
    // also unconditionally defaults to dark when no preference is saved.
    return true;
  });

  useEffect(() => {
    const theme = isDarkMode ? 'dark-theme' : 'light-theme';
    const dataTheme = isDarkMode ? 'dark' : 'light';

    // <html> is the single source of truth that the index.html bootstrap script
    // also writes to, so both always agree and the opposite class is removed first.
    const root = document.documentElement;
    root.classList.remove('dark-theme', 'light-theme');
    root.classList.add(theme);
    root.dataset.theme = dataTheme;

    // Mirror the class on <body> so that CSS variable declarations scoped to
    // `.dark-theme { --color-background: ... }` resolve on the element that
    // `body { background-color: var(--color-background) }` inherits from directly.
    // Without this, the :root light-mode defaults can win over the html-level
    // dark override inside Tailwind's @layer base cascade.
    document.body.classList.remove('dark-theme', 'light-theme');
    document.body.classList.add(theme);
    document.body.dataset.theme = dataTheme;

    // Save theme preference to localStorage
    localStorage.setItem('theme', dataTheme);
  }, [isDarkMode]);

  const toggleTheme = (): void => {
    setIsDarkMode(prev => !prev);
  };

  return (
    <ThemeContext.Provider value={{ isDarkMode, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};
