export type MoneyValue = string | number | bigint | null | undefined;

export function moneyToCents(value: MoneyValue): bigint | null {
  if (value == null || value === "") return null;
  const text = String(value).trim().replace(/,/g, "");
  const match = /^([+-]?)(\d+)(?:\.(\d{1,2}))?$/.exec(text);
  if (!match) return null;
  const fraction = (match[3] || "").padEnd(2, "0");
  const cents = BigInt(match[2]) * BigInt(100) + BigInt(fraction || "0");
  return match[1] === "-" ? -cents : cents;
}

export function centsToDecimal(cents: bigint): string {
  const negative = cents < BigInt(0);
  const absolute = negative ? -cents : cents;
  return `${negative ? "-" : ""}${absolute / BigInt(100)}.${String(absolute % BigInt(100)).padStart(2, "0")}`;
}

export function sumMoney(values: MoneyValue[]): string {
  return centsToDecimal(values.reduce<bigint>((total, value) => total + (moneyToCents(value) || BigInt(0)), BigInt(0)));
}

export function formatCny(value: MoneyValue): string {
  const parsed = moneyToCents(value);
  if (parsed == null) return value == null || value === "" ? "金额待确认" : String(value);
  const absolute = parsed < BigInt(0) ? -parsed : parsed;
  const integer = (absolute / BigInt(100)).toLocaleString("zh-CN");
  return `¥${integer}.${String(absolute % BigInt(100)).padStart(2, "0")}`;
}

export function moneyRatioPercent(value: MoneyValue, maximum: MoneyValue): number {
  const amount = moneyToCents(value) || BigInt(0);
  const max = moneyToCents(maximum) || BigInt(0);
  if (max <= BigInt(0) || amount <= BigInt(0)) return 0;
  return Number((amount * BigInt(10_000)) / max) / 100;
}
