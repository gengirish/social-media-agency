import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/*
 * Cadence's GlowButton: amber gradient with dark text and a lift-and-glow on
 * hover for primary; a quiet outlined button for everything else.
 */
const buttonVariants = cva(
  "press-scale inline-flex items-center justify-center gap-1.5 rounded-md font-mono font-medium transition-[transform,box-shadow,background-color,border-color,color] duration-200 disabled:cursor-not-allowed",
  {
    variants: {
      variant: {
        primary:
          "bg-gradient-to-br from-[#F6D07E] via-accent to-[#E4A72E] text-on-accent shadow-[0_2px_8px_rgb(var(--c-accent)/0.18),inset_0_1px_0_rgb(255_255_255/0.2)] hover:-translate-y-0.5 hover:shadow-glow disabled:translate-y-0 disabled:bg-none disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none",
        secondary: "border border-line text-muted hover:border-slate-300 hover:bg-slate-500/10 hover:text-ink disabled:opacity-50",
        ghost: "text-muted hover:bg-slate-500/10 hover:text-ink disabled:opacity-50",
        danger: "border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-50",
      },
      size: {
        sm: "px-3 py-1.5 text-xs",
        md: "px-4 py-2 text-sm",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  }
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, type = "button", ...props },
  ref
) {
  return <button ref={ref} type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
});

export { buttonVariants };
