import React from 'react';

/**
 * BrandLogo renders the ActionsManager shield icon plus the wordmark using
 * real text (not a rasterized image) so it stays crisp at any size and
 * adapts to light/dark theme via the app's own color tokens.
 *
 * - variant="full": shield icon + "ActionsManager" text. Use in the main
 *   app header / login screen / dashboards where there is enough
 *   horizontal space.
 * - variant="icon": shield-only icon. Use in compact / mobile / collapsed
 *   layouts (sidebar collapsed state, small headers).
 * - variant="mono": single-color shield (kept for completeness; not used
 *   by default).
 */
export type BrandLogoVariant = 'full' | 'icon' | 'mono';
export type BrandLogoSize = 'sm' | 'md' | 'lg';

interface BrandLogoProps {
  variant?: BrandLogoVariant;
  size?: BrandLogoSize;
  className?: string;
  /** Override the accessible name. Defaults to "ActionsManager". */
  alt?: string;
}

const ICON_HEIGHT_CLASS: Record<BrandLogoSize, string> = {
  sm: 'h-9',   // 36px – compact headers
  md: 'h-11',  // 44px – sidebar, top app header, paired with text
  lg: 'h-12',  // 48px – dashboard / login hero, paired with text
};

const ICON_ONLY_HEIGHT_CLASS: Record<BrandLogoSize, string> = {
  sm: 'h-10',  // 40px – compact headers
  md: 'h-14',  // 56px – sidebar collapsed, standard icon placements
  lg: 'h-16',  // 64px – large hero icons
};

const TEXT_SIZE_CLASS: Record<BrandLogoSize, string> = {
  sm: 'text-xl',
  md: 'text-2xl',
  lg: 'text-3xl',
};

const BrandLogo: React.FC<BrandLogoProps> = ({
  variant = 'full',
  size = 'md',
  className = '',
  alt = 'ActionsManager',
}) => {
  if (variant === 'icon') {
    return (
      <img
        src="/branding/svg/shield-icon-transparent.svg"
        alt={alt}
        className={`${ICON_ONLY_HEIGHT_CLASS[size]} w-auto select-none ${className}`.trim()}
        draggable={false}
      />
    );
  }

  if (variant === 'mono') {
    return (
      <img
        src="/branding/svg/shield-monochrome-transparent.svg"
        alt={alt}
        className={`${ICON_ONLY_HEIGHT_CLASS[size]} w-auto select-none ${className}`.trim()}
        draggable={false}
      />
    );
  }

  // variant === 'full': icon + real text, not a rasterized wordmark image.
  return (
    <span className={`inline-flex items-center gap-2 select-none ${className}`.trim()}>
      <img
        src="/branding/svg/shield-icon-transparent.svg"
        alt=""
        aria-hidden="true"
        className={`${ICON_HEIGHT_CLASS[size]} w-auto`}
        draggable={false}
      />
      <span
        className={`${TEXT_SIZE_CLASS[size]} font-sans font-bold tracking-tight leading-none`}
        aria-label={alt}
      >
        <span className="text-text-primary dark:text-text-primary-dark">Actions</span>
        <span className="text-primary dark:text-primary-dark">Manager</span>
      </span>
    </span>
  );
};

export default BrandLogo;
