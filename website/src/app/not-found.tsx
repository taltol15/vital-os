import Link from "next/link";

export default function NotFound() {
  return (
    <main id="content" className="shell page-head">
      <p className="eyebrow">Vital OS</p>
      <h1>That page is not here.</h1>
      <p className="lede">The public pages are home, downloads, docs, and contact.</p>
      <p><Link className="button" href="/">Back home</Link></p>
    </main>
  );
}
