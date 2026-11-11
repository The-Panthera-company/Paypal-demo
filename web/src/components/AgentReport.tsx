// Shows the Giving Agent's report text nicely: the model writes light markdown
// (**bold**, "- " items in one long line, amounts as "$3.00 (300 cents)").
// Plain text in, React out: nothing is rendered as HTML.

function inline(text: string) {
  const clean = text.replace(/\s*\(\d[\d,]*\s*cents?\)/gi, "");
  return clean.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    /^\*\*[^*]+\*\*$/.test(part) ? (
      <strong key={i} className="font-bold text-ink">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    ),
  );
}

export function AgentReport({ text, compact = false }: { text: string; compact?: boolean }) {
  // Split "intro - item - item. Closing" into intro, items and closing
  const pieces = text.trim().split(/\s+-\s+(?=\*\*|\$)/);
  let intro = pieces[0];
  const items = pieces.slice(1);
  let closing = "";
  if (items.length) {
    const last = items[items.length - 1];
    const cut = last.search(/(?<=\.)\s+(?=[A-Z])/);
    if (cut > 0) {
      items[items.length - 1] = last.slice(0, cut);
      closing = last.slice(cut).trim();
    }
  }
  // A leading "**Title**" becomes a heading
  let title = "";
  const t = intro.match(/^\*\*([^*]+)\*\*\s*/);
  if (t) {
    title = t[1];
    intro = intro.slice(t[0].length);
  }
  return (
    <div className="space-y-3 text-ink">
      {title && <p className="font-display text-xl">{title}</p>}
      {intro && <p className="leading-7">{inline(intro)}</p>}
      {items.length > 0 && (
        <ul className="space-y-2">
          {items.map((it, i) => {
            const [head, why] = it.split(/\s+[—–-]\s+/, 2);
            return (
              <li key={i} className="border-l-2 border-cobalt-green bg-surface-alt px-3 py-2 leading-6">
                <span>{inline(head)}</span>
                {why && !compact && <span className="block text-sm text-text">{inline(why)}</span>}
              </li>
            );
          })}
        </ul>
      )}
      {closing && <p className="text-sm leading-6 text-text">{inline(closing)}</p>}
    </div>
  );
}
