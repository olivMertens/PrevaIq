type MessageValue =
  | string
  | number
  | boolean
  | null
  | MessageValue[]
  | { [key: string]: MessageValue };

export function sameLanguage(left: string, right: string): boolean {
  return left.toLowerCase().split('-')[0] === right.toLowerCase().split('-')[0];
}

/** Swiss UI messages inherit German without changing message keys or source documents. */
export function swissGermanMessages<T extends MessageValue>(value: T): T;
export function swissGermanMessages(value: MessageValue): MessageValue {
  if (typeof value === 'string') return value.replace(/ß/g, 'ss').replace(/ẞ/g, 'SS');
  if (Array.isArray(value)) return value.map(swissGermanMessages);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [key, swissGermanMessages(child)])
    );
  }
  return value;
}
