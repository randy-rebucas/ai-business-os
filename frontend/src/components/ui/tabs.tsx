"use client";

import { useId, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export type TabItem = { key: string; label: string; content: React.ReactNode; badge?: React.ReactNode };

/** WAI-ARIA tabs: one tab stop, arrow keys / Home / End move between tabs, panels are labelled by their tab. */
export function Tabs({ items, label, initial }: { items: TabItem[]; label: string; initial?: string }) {
  const id = useId();
  const [active, setActive] = useState(initial && items.some((i) => i.key === initial) ? initial : items[0]?.key);
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const move = (to: number) => {
    const next = items[(to + items.length) % items.length];
    setActive(next.key);
    refs.current[next.key]?.focus();
  };
  const onKey = (e: React.KeyboardEvent, index: number) => {
    const keys: Record<string, number> = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: items.length - 1 };
    if (e.key in keys) {
      e.preventDefault();
      move(keys[e.key]);
    }
  };

  return (
    <div>
      <div role="tablist" aria-label={label} className="mb-5 flex gap-1 overflow-x-auto border-b border-border">
        {items.map((item, i) => {
          const selected = item.key === active;
          return (
            <button
              key={item.key}
              ref={(el) => { refs.current[item.key] = el; }}
              type="button"
              role="tab"
              id={`${id}-tab-${item.key}`}
              aria-selected={selected}
              aria-controls={`${id}-panel-${item.key}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(item.key)}
              onKeyDown={(e) => onKey(e, i)}
              className={cn(
                "-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors",
                selected ? "border-accent font-medium text-fg" : "border-transparent text-muted hover:text-fg",
              )}
            >
              {item.label}
              {item.badge}
            </button>
          );
        })}
      </div>
      {items.map((item) => (
        <div
          key={item.key}
          role="tabpanel"
          id={`${id}-panel-${item.key}`}
          aria-labelledby={`${id}-tab-${item.key}`}
          hidden={item.key !== active}
          tabIndex={0}
          className="focus-visible:outline-none"
        >
          {item.key === active && item.content}
        </div>
      ))}
    </div>
  );
}
