import { render } from '@testing-library/react';
import { ActionBrandingIcon, createPackageFallback } from './actionBranding';

/**
 * This file had no tests, which is why a regression in the DynamicIcon
 * fallback shipped twice: once when `fallback={Package}` was passed (a
 * zero-arg slot handed a props-taking component), and again when hoisting it
 * to module scope to satisfy SonarQube's S6478 silently dropped size and
 * className. Both were invisible because nothing rendered this component.
 */

const svg = (container: HTMLElement) => container.querySelector('svg');

describe('createPackageFallback', () => {
  it('renders at the requested size rather than lucide default of 24', () => {
    const Fallback = createPackageFallback(16, '');
    const { container } = render(<Fallback />);

    expect(svg(container)).toHaveAttribute('width', '16');
    expect(svg(container)).toHaveAttribute('height', '16');
  });

  it('carries the branding class through to the fallback', () => {
    const Fallback = createPackageFallback(16, 'text-blue-500 dark:text-blue-400');
    const { container } = render(<Fallback />);

    expect(svg(container)).toHaveClass('text-blue-500', 'dark:text-blue-400');
  });

  it('is decorative, so it stays hidden from assistive tech', () => {
    const Fallback = createPackageFallback(16, '');
    const { container } = render(<Fallback />);

    expect(svg(container)).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('ActionBrandingIcon', () => {
  it('falls back to the generic icon when there is no branding', () => {
    const { container } = render(<ActionBrandingIcon />);

    expect(svg(container)).toHaveAttribute('width', '16');
    expect(svg(container)).toHaveAttribute('aria-hidden', 'true');
  });

  it('ignores an icon name lucide does not know', () => {
    // `icon` is user-repo-controlled, so an unrecognised name must not be
    // forwarded as a component prop.
    const { container } = render(<ActionBrandingIcon icon="definitely-not-a-lucide-icon" />);

    expect(svg(container)).toBeInTheDocument();
  });

  it('applies the mapped branding colour class', () => {
    const { container } = render(<ActionBrandingIcon color="blue" />);

    expect(svg(container)).toHaveClass('text-blue-500');
  });

  it('ignores a colour outside GitHub branding enum', () => {
    const { container } = render(<ActionBrandingIcon color="chartreuse" className="shrink-0" />);

    expect(svg(container)).toHaveClass('shrink-0');
    expect(svg(container)?.getAttribute('class')).not.toContain('chartreuse');
  });

  it('honours an explicit size', () => {
    const { container } = render(<ActionBrandingIcon size={32} />);

    expect(svg(container)).toHaveAttribute('width', '32');
  });

  it('renders the fallback path and the branded path at the same size', () => {
    // The regression this file exists to catch: the two paths disagreeing.
    const { container: fallbackPath } = render(<ActionBrandingIcon size={20} />);
    const Fallback = createPackageFallback(20, '');
    const { container: dynamicFallback } = render(<Fallback />);

    expect(svg(fallbackPath)?.getAttribute('width')).toBe(
      svg(dynamicFallback)?.getAttribute('width'),
    );
  });
});
