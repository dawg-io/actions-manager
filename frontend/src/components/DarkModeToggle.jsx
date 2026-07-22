import { useTheme } from './ThemeContext';

const DarkModeToggle = ({ className = 'fixed' }) => {
  const { isDarkMode, toggleTheme } = useTheme();

  // Tailwind classes for the toggle button
  const baseClasses = "bg-container border border-border rounded-lg px-3 py-2 cursor-pointer text-lg transition-all duration-200 shadow-md flex items-center justify-center w-12 h-12 hover:shadow-lg hover:scale-105 active:scale-95";
  const fixedClasses = "fixed top-6 right-6 z-[1000]";
  const inlineClasses = "static bg-white/20 border-white/30 backdrop-blur-md hover:bg-white/30";
  
  const positionClasses = className === 'fixed' ? fixedClasses : inlineClasses;

  return (
    <button 
      className={`${baseClasses} ${positionClasses}`}
      onClick={toggleTheme}
      title={`Switch to ${isDarkMode ? 'light' : 'dark'} mode`}
      aria-label={`Switch to ${isDarkMode ? 'light' : 'dark'} mode`}
    >
      {isDarkMode ? '☀️' : '🌙'}
    </button>
  );
};

export default DarkModeToggle;