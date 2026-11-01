import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

const buttonVariants = cva(
  "inline-flex select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-fm-sm border font-medium transition-[background-color,border-color,color,opacity] duration-[var(--fm-motion)] disabled:pointer-events-none disabled:opacity-40 active:translate-y-px",
  {
    variants: {
      variant: {
        primary: "border-fm-text bg-fm-text text-fm-bg hover:opacity-90",
        accent: "border-fm-hold bg-fm-hold text-fm-ink hover:brightness-110 font-semibold",
        secondary: "border-fm-border-strong bg-fm-raised text-fm-text hover:bg-fm-hover",
        ghost: "border-transparent bg-transparent text-fm-muted hover:bg-fm-raised hover:text-fm-text",
        hold: "border-fm-hold-line bg-fm-hold-bg text-fm-hold hover:border-fm-hold",
        verified: "border-fm-verified-line bg-fm-verified-bg text-fm-verified hover:border-fm-verified",
        danger: "border-fm-fraud-line bg-fm-fraud-bg text-fm-fraud hover:border-fm-fraud",
      },
      size: {
        xs: "h-6 px-2 text-[11px]",
        sm: "h-7 px-2.5 text-[12px]",
        md: "h-8 px-3 text-[12.5px]",
        lg: "h-10 px-4 text-[13.5px]",
        icon: "h-8 w-8 p-0",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, type, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp ref={ref} type={asChild ? undefined : type ?? "button"} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
  },
);
Button.displayName = "Button";
export { buttonVariants };
