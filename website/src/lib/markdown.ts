function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inline(value: string): string {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" rel="noreferrer">$1</a>');
}

/** Small markdown subset for admin-authored release notes. HTML is escaped first. */
export function renderSimpleMarkdown(source: string): string {
  const blocks = source.replace(/\r\n/g, "\n").trim().split(/\n{2,}/);
  if (!blocks.length || (blocks.length === 1 && !blocks[0])) return "";
  return blocks
    .map((block) => {
      const lines = block.split("\n");
      if (lines.every((line) => line.startsWith("- "))) {
        const items = lines.map((line) => `<li>${inline(line.slice(2))}</li>`).join("");
        return `<ul>${items}</ul>`;
      }
      return `<p>${lines.map((line) => inline(line)).join("<br />")}</p>`;
    })
    .join("");
}
