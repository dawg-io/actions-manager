/* eslint-disable no-restricted-syntax -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React, { useRef } from "react";
import { cn } from "../lib/utils";

interface PrefixedInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'prefix'> {
  prefix: string;
  value: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  style?: React.CSSProperties;
  showPrefix?: boolean;
  /** Optional non-editable suffix displayed after the input (e.g. ".yml"). */
  suffix?: string;
}

const PrefixedInput: React.FC<PrefixedInputProps> = ({
  prefix,
  value,
  onChange,
  placeholder = "Enter name",
  className = "input",
  disabled = false,
  style = {},
  showPrefix = true,
  suffix,
  ...props
}) => {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleContainerClick = () => {
    if (inputRef.current && !disabled) {
      inputRef.current.focus();
    }
  };

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (onChange) {
      onChange(event.target.value);
    }
  };

  const handleContainerKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleContainerClick();
    }
  };

  /**
   * Container: mirrors the Shadcn UI Input border / background / radius / shadow
   * so the segmented variant looks identical to the plain Shadcn Input.
   * `focus-within:ring-*` provides the same focus-ring that `focus-visible:ring-*`
   * gives on the plain input, activating as soon as the inner <input> is focused.
   */
  const containerClasses = cn(
    "prefixed-input-container",
    "flex h-9 w-full rounded-md border text-sm shadow-sm transition-colors overflow-hidden",
    "border-input-border bg-input-bg",
    "focus-within:outline-none focus-within:ring-1 focus-within:ring-input-focus",
    "dark:border-input-dark-border dark:bg-input-dark-bg",
    disabled ? "cursor-not-allowed opacity-50" : "cursor-text",
  );

  /** Prefix segment (grayed, left side) — separated from the editable area by a right border. */
  const prefixClasses = cn(
    "prefixed-input-prefix",
    "flex items-center px-3 py-1 text-sm",
    "bg-hover-bg text-text-secondary font-medium whitespace-nowrap select-none",
    "border-r border-input-border",
    "dark:bg-hover-dark-bg dark:text-text-secondary-dark dark:border-input-dark-border",
    disabled && "cursor-not-allowed",
  );

  /** Suffix segment (grayed, right side) — separated from the editable area by a left border. */
  const suffixClasses = cn(
    "prefixed-input-suffix",
    "flex items-center px-3 py-1 text-sm",
    "bg-hover-bg text-text-secondary font-medium whitespace-nowrap select-none",
    "border-l border-input-border",
    "dark:bg-hover-dark-bg dark:text-text-secondary-dark dark:border-input-dark-border",
    disabled && "cursor-not-allowed",
  );

  /** The editable <input> inside any segmented container variant. */
  const innerInputClasses = cn(
    "prefixed-input-field",
    "flex-1 h-full px-3 py-1 text-sm",
    "bg-transparent text-text-primary",
    "placeholder:text-text-muted",
    "outline-none border-0",
    "dark:text-text-primary-dark dark:placeholder:text-text-muted-dark",
    disabled && "cursor-not-allowed",
  );

  // No prefix, with suffix — container with editable area + right suffix segment
  if (!showPrefix && suffix) {
    return (
      <div
        className={cn(containerClasses, className)}
        onClick={handleContainerClick}
        onKeyDown={handleContainerKeyDown}
        role="button"
        tabIndex={0}
        aria-label="Focus input field"
        style={style}
      >
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={handleInputChange}
          placeholder={placeholder}
          className={innerInputClasses}
          disabled={disabled}
          {...props}
        />
        <span className={suffixClasses} data-testid="prefixed-input-suffix">{suffix}</span>
      </div>
    );
  }

  // No prefix, no suffix — plain Shadcn Input clone
  if (!showPrefix) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={handleInputChange}
        placeholder={placeholder}
        className={cn(
          "flex h-9 w-full rounded-md border px-3 py-1 text-sm shadow-sm transition-colors",
          "border-input-border bg-input-bg text-text-primary",
          "placeholder:text-text-muted",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-input-focus",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "dark:border-input-dark-border dark:bg-input-dark-bg dark:text-text-primary-dark dark:placeholder:text-text-muted-dark",
          className,
        )}
        disabled={disabled}
        style={style}
        {...props}
      />
    );
  }

  // Full prefix segment + editable area + optional suffix segment
  return (
    <div
      className={cn(containerClasses, className)}
      onClick={handleContainerClick}
      onKeyDown={handleContainerKeyDown}
      role="button"
      tabIndex={0}
      aria-label="Focus input field"
      style={style}
    >
      {/* Grayed-out prefix */}
      <span className={prefixClasses} data-testid="prefixed-input-prefix">{prefix}</span>

      {/* Editable input */}
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={handleInputChange}
        placeholder={placeholder}
        className={innerInputClasses}
        disabled={disabled}
        {...props}
      />

      {/* Non-editable suffix (e.g. ".yml") */}
      {suffix && <span className={suffixClasses} data-testid="prefixed-input-suffix">{suffix}</span>}
    </div>
  );
};

export default PrefixedInput;

