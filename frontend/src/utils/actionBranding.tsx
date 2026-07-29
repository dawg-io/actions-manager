import React from 'react';
import { Package } from 'lucide-react';
import { DynamicIcon, iconNames, type IconName } from 'lucide-react/dynamic';

const ICON_NAME_SET = new Set<string>(iconNames);

// GitHub's fixed action.yml branding.color enum, mapped to Tailwind text-color
// utility classes (literal strings so Tailwind's JIT scanner picks them up).
// Same "identity accent, not status" spirit as projectColors.ts's color map.
const BRANDING_COLOR_CLASSES: Record<string, string> = {
  white: 'text-slate-200 dark:text-slate-100',
  yellow: 'text-yellow-500 dark:text-yellow-400',
  blue: 'text-blue-500 dark:text-blue-400',
  green: 'text-emerald-500 dark:text-emerald-400',
  orange: 'text-orange-500 dark:text-orange-400',
  red: 'text-red-500 dark:text-red-400',
  purple: 'text-purple-500 dark:text-purple-400',
  'gray-dark': 'text-slate-600 dark:text-slate-300',
};

interface ActionBrandingIconProps {
  icon?: string | null;
  color?: string | null;
  size?: number;
  className?: string;
}

/**
 * Renders an action's marketplace-style branding icon (parsed from its
 * action.yml `branding: {icon, color}` block), falling back to a generic
 * icon when there's no branding or the icon name isn't a recognized Feather
 * icon. `icon` is user-repo-controlled data, so membership in lucide-react's
 * own name set is checked before it's used as a component prop.
 */
export const ActionBrandingIcon: React.FC<ActionBrandingIconProps> = ({
  icon,
  color,
  size = 16,
  className,
}) => {
  const colorClass = (color && BRANDING_COLOR_CLASSES[color]) || '';
  const combinedClassName = [className, colorClass].filter(Boolean).join(' ');

  if (icon && ICON_NAME_SET.has(icon)) {
    return (
      <DynamicIcon
        name={icon as IconName}
        size={size}
        className={combinedClassName}
        aria-hidden="true"
        fallback={Package}
      />
    );
  }

  return <Package size={size} className={combinedClassName} aria-hidden="true" />;
};
