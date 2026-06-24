import { cn } from "../../lib/utils";

interface BadgeProps {
  variant: "processing" | "completed" | "failed";
  children: React.ReactNode;
  className?: string;
}

const variantStyles: Record<"processing" | "completed" | "failed", string> = {
  processing: "text-amber-400",
  completed: "text-emerald-400",
  failed: "text-red-400",
};

export function Badge({ variant, children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center text-xs font-medium capitalize",
        variantStyles[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
