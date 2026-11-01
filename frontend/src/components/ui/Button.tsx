import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

const buttonVariants = cva(
  "inline-flex h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded-fm-sm border px-3 text-[12px] font-medium transition-colors duration-[var(--fm-motion)] disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        primary: "border-fm-text bg-fm-text text-fm-bg hover:opacity-85",
        secondary: "border-fm-border-strong bg-fm-raised hover:bg-fm-panel",
        ghost: "border-transparent bg-transparent hover:bg-fm-raised",
        hold: "border-fm-hold/50 bg-fm-hold-bg text-fm-hold hover:brightness-110",
        danger: "border-fm-fraud/50 bg-fm-fraud-bg text-fm-fraud hover:brightness-110",
      },
      size: { sm: "h-7 px-2 text-[11px]", md: "h-8 px-3", lg: "h-9 px-4 text-[13px]" },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
  },
);
Button.displayName = "Button";
export { buttonVariants };
