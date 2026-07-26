/**
 * Shared UI primitives.
 *
 * Kept deliberately small and unstyled-by-prop: the look lives in
 * `styles/global.css`, so a change to the design system is one file, not a
 * sweep through every component.
 */

import { type ReactNode, useId, useState } from "react";

/* ------------------------------------------------------------------ layout */

export function Card({
  title,
  eyebrow,
  note,
  children,
}: {
  title?: string;
  eyebrow?: string;
  note?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      {(title || eyebrow) && (
        <header className="card-head">
          {title && <h3>{title}</h3>}
          {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        </header>
      )}
      {note && <p className="card-note">{note}</p>}
      {children}
    </section>
  );
}

export function SectionHead({ title, eyebrow }: { title: string; eyebrow?: string }) {
  return (
    <div className="section-head">
      <h2>{title}</h2>
      {eyebrow && <span className="eyebrow">{eyebrow}</span>}
    </div>
  );
}

/* -------------------------------------------------------------------- tabs */

export interface TabDef {
  id: string;
  label: string;
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          // Styling keys off the class, not off `aria-selected`. The attribute
          // is still set for assistive tech, but some engines don't reliably
          // re-evaluate an attribute selector when React mutates the attribute
          // in place — the tab would keep the previous tab's highlight. A class
          // change always invalidates.
          className={`tab${active === tab.id ? " is-active" : ""}`}
          aria-selected={active === tab.id}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------- accordion */

export function Group({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <div className="group">
      <button
        className={`group-head${open ? " is-open" : ""}`}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
      >
        {title}
        <svg className="chev" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
          <path d="M3 1l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.4" />
        </svg>
      </button>
      {open && (
        <div className="group-body" id={id}>
          {children}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ fields */

/**
 * A slider that draws its own market band on the track.
 *
 * The guardrail becomes visible *before* you trip it rather than only as a
 * complaint afterwards — you can see that you are dragging out of the market
 * as you do it, which is the whole point of a calibration layer.
 */
export function SliderField({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
  band,
  note,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  format: (value: number) => string;
  band?: [number, number];
  note?: ReactNode;
}) {
  const pct = (v: number) => ((v - min) / (max - min)) * 100;
  const outOfBand = band ? value < band[0] || value > band[1] : false;
  const bandLeft = band ? Math.max(0, pct(band[0])) : 0;
  const bandRight = band ? Math.min(100, pct(band[1])) : 0;

  return (
    <label className="field">
      <span className="field-top">
        <span className="field-label">{label}</span>
        <span className={`field-value${outOfBand ? " out" : ""}`}>{format(value)}</span>
      </span>
      <span className="slider-wrap">
        {band && (
          <span
            className="band-marker"
            style={{ left: `${bandLeft}%`, width: `${Math.max(0, bandRight - bandLeft)}%` }}
            title={`Typical market range: ${format(band[0])} – ${format(band[1])}`}
          />
        )}
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </span>
      {note && <span className="field-note">{note}</span>}
    </label>
  );
}

export function NumberField({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  suffix,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
  suffix?: string;
}) {
  return (
    <label className="field">
      <span className="field-top">
        <span className="field-label">{label}</span>
        {suffix && <span className="field-value">{suffix}</span>}
      </span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isFinite(next)) onChange(next);
        }}
      />
    </label>
  );
}

export function ToggleField({
  label,
  checked,
  onChange,
  note,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  note?: ReactNode;
}) {
  return (
    <div className="field">
      <label className="toggle">
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>{label}</span>
      </label>
      {note && <span className="field-note">{note}</span>}
    </div>
  );
}

/* ------------------------------------------------------------------- state */

export function Skeleton({ height = 260 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} />;
}

export function StructureFailedNotice({ message }: { message: string }) {
  return (
    <div className="callout">
      <strong>This structure does not finance.</strong> {message}
    </div>
  );
}
