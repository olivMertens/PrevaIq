// Agent output shown in the chat: JSON objects become readable Markdown and the review
// flag, shown as a status badge instead, is removed from the text.
// Pure module (no imports) so tests can load it without the Next.js toolchain.

type Translate = (key: string) => string;

const DECISION_LABELS: Record<string, string> = {
  documented_recommendation: 'recommendation',
  recommendation: 'recommendation',
  decision: 'decision',
  rationale: 'rationale',
  reasoning: 'rationale',
  conditions_or_franchise: 'conditionsOrDeductible',
  conditions: 'conditions',
  next_steps: 'nextSteps',
  actions: 'actions',
  missing_items: 'missingItems',
  missing_documents: 'missingDocuments',
  requires_human_review: 'humanReview',
  confidence: 'confidence',
  risk_level: 'riskLevel',
  citations: 'citations',
  sources: 'sources',
};

function tryParseAgentJson(text: string): Record<string, unknown> | null {
  if (!text) return null;
  const trimmed = text.trim();
  const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)```\s*$/i);
  const candidate = fenced ? fenced[1].trim() : trimmed;
  if (!(candidate.startsWith('{') && candidate.endsWith('}'))) return null;
  try {
    const parsed = JSON.parse(candidate);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function humanizeKey(key: string, t: Translate): string {
  return DECISION_LABELS[key]
    ? t(`decisionFields.${DECISION_LABELS[key]}`)
    : key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function renderAgentValue(value: unknown, t: Translate, indent = 0): string {
  if (value === null || value === undefined) return '_—_';
  if (typeof value === 'boolean') return value ? `✅ ${t('yes')}` : `❌ ${t('no')}`;
  if (typeof value === 'number') return String(value);
  if (typeof value === 'string') return value.trim();
  if (Array.isArray(value)) {
    if (value.length === 0) return `_(${t('none')})_`;
    return value
      .map((item) => {
        if (typeof item === 'string') return `${'  '.repeat(indent)}- ${item.trim()}`;
        if (item && typeof item === 'object') {
          const inner = Object.entries(item as Record<string, unknown>)
            .map(([k, val]) => `**${humanizeKey(k, t)}** : ${renderAgentValue(val, t, indent + 1)}`)
            .join(' · ');
          return `${'  '.repeat(indent)}- ${inner}`;
        }
        return `${'  '.repeat(indent)}- ${String(item)}`;
      })
      .join('\n');
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `- **${humanizeKey(k, t)}** : ${renderAgentValue(v, t, indent + 1)}`)
      .join('\n');
  }
  return String(value);
}

function formatAgentObject(obj: Record<string, unknown>, t: Translate): string | null {
  const keys = Object.keys(obj);
  const known = ['documented_recommendation', 'recommendation', 'decision', 'rationale', 'next_steps', 'missing_items', 'conditions_or_franchise'];
  if (!keys.some((k) => known.includes(k))) return null;

  const parts: string[] = [];
  const reco = (obj.documented_recommendation || obj.recommendation || obj.decision) as string | undefined;
  if (typeof reco === 'string' && reco) {
    const lower = reco.toLowerCase();
    const badge = lower.includes('approve') || lower.includes('accept') || lower === 'approuve' ? '🟢'
      : lower.includes('deny') || lower.includes('reject') || lower === 'refuse' ? '🔴'
      : lower.includes('review') ? '🟡'
      : '🔵';
    parts.push(`**${badge} ${humanizeKey('documented_recommendation', t)} :** \`${reco}\``);
  }

  const order = [
    'rationale', 'reasoning',
    'conditions_or_franchise', 'conditions',
    'missing_items', 'missing_documents',
    'next_steps', 'actions',
    'risk_level', 'confidence',
    'citations', 'sources',
  ];
  const skip = new Set(['documented_recommendation', 'recommendation', 'decision']);
  const remaining = [...order.filter((k) => k in obj), ...keys.filter((k) => !order.includes(k) && !skip.has(k))];

  for (const key of remaining) {
    if (skip.has(key)) continue;
    const val = obj[key];
    if (val === undefined) continue;
    if (Array.isArray(val) && val.length === 0) continue;
    parts.push(`\n**${humanizeKey(key, t)}**`);
    parts.push(renderAgentValue(val, t));
  }

  return parts.join('\n');
}

// The review flag on a line of its own ("requires_human_review: true", "- **…**: true").
const FLAG_LINE_RE = /^[ \t>*_`'"-]*requires_human_review[`'"*_]*[ \t]*:[ \t]*[`'"*_]*[ \t]*(?:true|false)\b[`'"*_ \t.]*$\n?/gim;
// "…: timed out — `requires_human_review: true`."
const FLAG_SUFFIX_RE = /[ \t]*[—–-][ \t]*[`'"*_]*requires_human_review[`'"*_]*[ \t]*:[ \t]*[`'"*_]*[ \t]*(?:true|false)\b[`'"*_]*(?=[ \t]*[.!?]?[ \t]*$)/gim;
// "`requires_human_review: true` — retry or …"
const FLAG_PREFIX_RE = /[`'"*_]*requires_human_review[`'"*_]*[ \t]*:[ \t]*[`'"*_]*[ \t]*(?:true|false)\b[`'"*_]*[ \t]*[—–-][ \t]*/gi;

/** Remove the machine-readable review flag from agent prose. */
export function stripReviewMarker(text: string): string {
  return text
    .replace(FLAG_LINE_RE, '')
    .replace(FLAG_SUFFIX_RE, '')
    .replace(FLAG_PREFIX_RE, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/** Markdown to display for an agent output (prose as is, JSON objects as fields). */
export function agentDisplayText(text: string, t: Translate): string {
  const parsed = tryParseAgentJson(text);
  if (!parsed) return stripReviewMarker(text || '');
  const fields = { ...parsed };
  delete fields.requires_human_review;
  return formatAgentObject(fields, t) ?? renderAgentValue(fields, t);
}
