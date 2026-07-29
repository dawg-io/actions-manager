import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "../../lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-white shadow hover:bg-primary-hover dark:bg-primary-dark dark:hover:bg-primary-dark-hover",
        destructive:
          "bg-danger text-white shadow-sm hover:bg-danger/90 dark:bg-danger dark:hover:bg-danger/90",
        merge:
          "bg-merge text-white shadow hover:bg-merge-hover focus-visible:ring-merge-ring dark:bg-merge dark:hover:bg-merge-hover",
        outline:
          "border border-input-border bg-background text-text-primary shadow-sm hover:bg-hover-bg hover:text-text-primary dark:border-border-dark dark:bg-container-dark dark:text-text-primary-dark dark:hover:bg-hover-dark-bg dark:hover:text-text-primary-dark",
        secondary:
          "bg-secondary text-white shadow-sm hover:bg-secondary-hover dark:bg-secondary dark:hover:bg-secondary-dark-hover",
        ghost: "hover:bg-hover-bg hover:text-text-primary dark:hover:bg-hover-dark-bg dark:hover:text-text-primary-dark",
        link: "text-primary underline-offset-4 hover:underline dark:text-primary-dark",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-8",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
