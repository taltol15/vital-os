import fs from "node:fs";
import path from "node:path";

export type DocPage = {
  slug: string;
  title: string;
  description: string;
  order: number;
  body: string;
  fallback: boolean;
};

function splitFrontmatter(raw: string): { data: Record<string, string>; body: string } {
  if (!raw.startsWith("---\n")) return { data: {}, body: raw };
  const end = raw.indexOf("\n---\n", 4);
  if (end === -1) return { data: {}, body: raw };
  const data: Record<string, string> = {};
  for (const line of raw.slice(4, end).split("\n")) {
    const index = line.indexOf(":");
    if (index === -1) continue;
    data[line.slice(0, index).trim()] = line.slice(index + 1).trim();
  }
  return { data, body: raw.slice(end + 5) };
}

function docPath(locale: string, slug: string): string {
  return path.join(process.cwd(), "content", "docs", locale, `${slug}.mdx`);
}

export function readDoc(locale: string, slug: string): DocPage | null {
  const folder = locale !== "en" && fs.existsSync(docPath(locale, slug)) ? locale : "en";
  const file = docPath(folder, slug);
  if (!fs.existsSync(file)) return null;
  const { data, body } = splitFrontmatter(fs.readFileSync(docPath(folder, slug), "utf8"));
  return {
    slug,
    title: data.title || slug,
    description: data.description || "",
    order: Number(data.order || 0),
    body,
    fallback: folder === "en" && locale !== "en",
  };
}

export function listDocs(locale: string): DocPage[] {
  const dir = path.join(process.cwd(), "content", "docs", "en");
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((name) => name.endsWith(".mdx"))
    .map((name) => readDoc(locale, name.replace(/\.mdx$/, "")))
    .filter((doc): doc is DocPage => doc !== null)
    .sort((a, b) => a.order - b.order);
}
