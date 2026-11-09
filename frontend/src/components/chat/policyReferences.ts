import type { RAGCitation } from './types';

interface MarkdownNode {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
}

export function citationReferenceMap(citations: readonly RAGCitation[]) {
  const candidates = new Map<string, string | null>();
  for (const citation of citations) {
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(citation.policy_id)) continue;
    for (const label of [citation.policy_id, citation.criteria_id]) {
      if (!label || !/^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$/.test(label)) continue;
      const previous = candidates.get(label);
      candidates.set(label, previous === undefined || previous === citation.policy_id
        ? citation.policy_id : null);
    }
  }
  return new Map([...candidates].flatMap(([label, policy]) => policy ? [[label, policy] as const] : []));
}

/** Link only explicit, unambiguous source IDs; never infer a policy from prose. */
export function policyReferencePlugin(citations: readonly RAGCitation[]) {
  const references = citationReferenceMap(citations);
  const labels = [...references.keys()].sort((a, b) => b.length - a.length)
    .map(label => label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const pattern = labels.length
    ? new RegExp(`(?<![A-Za-z0-9_-])(?:${labels.join('|')})(?![A-Za-z0-9_-])`, 'g') : null;
  return () => (tree: MarkdownNode) => {
    if (!pattern) return;
    const visit = (node: MarkdownNode) => {
      if (['link', 'linkReference', 'image', 'imageReference', 'code', 'inlineCode', 'html'].includes(node.type) || !node.children) return;
      node.children = node.children.flatMap(child => {
        if (child.type !== 'text' || !child.value) { visit(child); return [child]; }
        const pieces: MarkdownNode[] = [];
        let offset = 0;
        for (const match of child.value.matchAll(pattern)) {
          const index = match.index;
          const policy = references.get(match[0]);
          if (!policy) continue;
          if (index > offset) pieces.push({type: 'text', value: child.value.slice(offset, index)});
          pieces.push({
            type: 'link', url: `#policy/${encodeURIComponent(policy)}`,
            children: [{type: 'text', value: match[0]}],
          });
          offset = index + match[0].length;
        }
        if (!offset) return [child];
        if (offset < child.value.length) pieces.push({type: 'text', value: child.value.slice(offset)});
        return pieces;
      });
    };
    visit(tree);
  };
}
