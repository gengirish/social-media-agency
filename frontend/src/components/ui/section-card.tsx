import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Eyebrow } from "@/components/ui/panel";

/*
 * Cadence's SectionCard: a glass panel headed by an eyebrow, with an optional
 * display-face heading, description and actions. `delay` staggers the fade-up
 * entrance when several cards render together.
 */
export function SectionCard({
  eyebrow,
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
  delay = 0,
  as: Tag = "section",
}: {
  eyebrow?: ReactNode;
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
  delay?: number;
  as?: "section" | "div" | "form";
}) {
  const hasHead = eyebrow || title || description || actions;
  return (
    <Tag
      className={cn(
        "rounded-xl border border-line bg-panel/70 p-5 shadow-soft backdrop-blur-xl motion-safe:animate-screen-in sm:p-6",
        className
      )}
      style={delay ? { animationDelay: `${delay}s` } : undefined}
    >
      {hasHead && (
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1.5">
            {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
            {title && <h2 className="font-display text-lg font-semibold tracking-tight text-ink">{title}</h2>}
            {description && <p className="max-w-2xl text-sm text-muted">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children && <div className={cn(hasHead && "mt-5", bodyClassName)}>{children}</div>}
    </Tag>
  );
}
