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

function fileFor(locale: string, slug: string): { file: string; fallback: boolean } | null {
  const localized = path.join(process.cwd(), "content/docs", locale, `${slug}.mdx`);
  const english = path.join(process.cwd(), "content/docs/en", `${slug}.mdx`);
  if (fs.existsSync(localized)) return { file: localized, fallback: false };
  if (fs.existsSync(english)) return { file: english, fallback: locale !== "en" };
  return null;
}

export function readDoc(locale: string, slug: string): DocPage | null {
  const found = fileFor(locale, slug);
  if (!found) return null;
  const { data, body } = splitFrontmatter(fs.readFileSync(found.file, "utf8"));
  return {
    slug,
    title: data.title || slug,
    description: data.description || "",
    order: Number(data.order || 0),
    body,
    fallback: found.fallback,
  };
}

export function listDocs(locale: string): DocPage[] {
  const dir = path.join(process.cwd(), "content/docs/en");
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((name) => name.endsWith(".mdx"))
    .map((name) => readDoc(locale, name.replace(/\.mdx$/, "")))
    .filter((doc): doc is DocPage => doc !== null)
    .sort((a, b) => a.order - b.order);
}
