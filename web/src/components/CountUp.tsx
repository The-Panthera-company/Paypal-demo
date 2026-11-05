import { RollingNumber } from "./RollingNumber";

// Home stats: the formatted number rolls into place, odometer-style, when scrolled into view.
export function CountUp({ value, format = "number", currency = "USD" }: { value: number; format?: "number" | "money"; currency?: string; duration?: number }) {
  const text =
    format === "money"
      ? new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(value / 100)
      : value.toLocaleString();
  return <RollingNumber value={text} />;
}
