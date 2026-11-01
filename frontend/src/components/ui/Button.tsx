import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

const buttonVariants = cva(
  "inline-flex select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-full font-medium tracking-[-0.01em] transition-[background-color,color,opacity,transform] duration-200 ease-[var(--fm-ease)] disabled:pointer-events-none disabled:opacity-40 active:scale-[0.98] motion-reduce:active:scale-100",
  {
    variants: {
      variant: {
        /** Blue pill: the one call to action on a surface. */
        accent: "bg-fm-accent text-white hover:bg-fm-accent-hover",
        /** Ink pill: strong, but not the accent. */
        primary: "bg-fm-text text-fm-canvas hover:opacity-85",
        secondary: "bg-fm-raised text-fm-text hover:bg-fm-hover",
        ghost: "bg-transparent text-fm-muted hover:bg-fm-raised hover:text-fm-text",
        link: "h-auto bg-transparent !px-0 text-fm-accent-text hover:underline underline-offset-4",
        hold: "bg-fm-hold-bg text-fm-hold hover:brightness-[0.97]",
        verified: "bg-fm-verified-bg text-fm-verified hover:brightness-[0.97]",
        danger: "bg-fm-fraud-bg text-fm-fraud hover:brightness-[0.97]",
      },
      size: {
        xs: "h-7 px-3 text-[12px]",
        sm: "h-8 px-3.5 text-[13px]",
        md: "h-9 px-4 text-[14px]",
        lg: "h-11 px-5 text-[15px]",
        xl: "h-12 px-6 text-[17px]",
        icon: "h-9 w-9 p-0",
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
