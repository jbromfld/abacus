import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type Source = { id: string; url: string };
type Node = { type: string; value?: string; url?: string; children?: Node[] };

// A few local models emit TeX despite requesting ordinary Markdown. Normalize
// common prose notation only; never interpret it as HTML or execute math/code.
export function readableProse(content: string) {
  return content
    .split(/(`{3,}[\s\S]*?`{3,}|`[^`\n]*`)/g)
    .map((part, index) => {
      if (index % 2) return part;
      return part
        .replace(/\u00a0|\u202f/g, ' ')
        .replace(/\\\$/g, '$')
        .replace(/\$?\\(?:text|mathrm|mathbf)\{([^{}]*)\}/g, '$1')
        .replace(/\\approx/g, '≈')
        .replace(/\\(?:times|cdot)/g, '×')
        .replace(/\\(?:left|right)(?=[()[\]])/g, '')
        .replace(/\\[([]([\s\S]*?)\\[)\]]/g, '$1')
        .replace(/(\d)\$(?=\s|[),.;]|$)/g, '$1');
    })
    .join('');
}

export default function AdvisorMarkdown({
  content,
  sources = [],
}: {
  content: string;
  sources?: Source[];
}) {
  // Resolve source markers without parsing HTML or changing code/link contents.
  const byId = new Map(sources.map((source) => [source.id, source]));
  function citations() {
    return (tree: Node) => {
      function visit(node: Node) {
        if (
          ['link', 'linkReference', 'code', 'inlineCode'].includes(node.type) ||
          !node.children
        )
          return;
        node.children = node.children.flatMap((child) => {
          if (child.type !== 'text' || !child.value) {
            visit(child);
            return [child];
          }
          child.value = readableProse(child.value);
          const parts: Node[] = [];
          let start = 0;
          for (const match of child.value.matchAll(/\[(S\d+)\]/g)) {
            if (!byId.has(match[1])) continue;
            if (match.index > start)
              parts.push({
                type: 'text',
                value: child.value.slice(start, match.index),
              });
            parts.push({
              type: 'link',
              url: '#abacus-source-' + match[1],
              children: [{ type: 'text', value: match[0] }],
            });
            start = match.index + match[0].length;
          }
          if (!start) return [child];
          if (start < child.value.length)
            parts.push({ type: 'text', value: child.value.slice(start) });
          return parts;
        });
      }
      visit(tree);
    };
  }
  return (
    <div className="advisor-markdown">
      <Markdown
        remarkPlugins={[remarkGfm, citations]}
        skipHtml
        components={{
          // Images and unverified links could leak financial text via URL requests.
          img: () => null,
          a: ({ href, children }) => {
            const source = href?.startsWith('#abacus-source-')
              ? byId.get(href.slice('#abacus-source-'.length))
              : sources.find((source) => source.url === href);
            const url = source?.url;
            return url && /^https?:\/\//i.test(url) ? (
              <a href={url} target="_blank" rel="noreferrer noopener">
                {children}
              </a>
            ) : (
              <span>{children}</span>
            );
          },
          table: ({ children }) => (
            <div
              className="table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Advisor response table"
            >
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}
