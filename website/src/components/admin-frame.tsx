import Image from "next/image";
import Link from "next/link";
import { signOut } from "@/app/mgmt/actions";

const links = [
  { href: "/mgmt", id: "overview", label: "Overview" },
  { href: "/mgmt/catalog", id: "catalog", label: "Catalog" },
  { href: "/mgmt/releases", id: "releases", label: "Releases" },
  { href: "/mgmt/messages", id: "messages", label: "Messages" },
];

export function AdminFrame({
  current,
  email,
  preview,
  children,
}: {
  current: string;
  email?: string | null;
  preview?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="shell admin">
      <nav className="admin-nav" aria-label="Administration">
        <Link className="brand" href="/mgmt">
          <Image src="/brand/vital-symbol.svg" alt="" width={22} height={22} />
        </Link>
        {preview ? <span className="preview-pill">Preview data</span> : null}
        {links.map((link) => (
          <Link key={link.id} href={link.href} aria-current={current === link.id ? "page" : undefined}>{link.label}</Link>
        ))}
        {email ? (
          <form action={signOut}>
            <button type="submit">Sign out</button>
            <p className="meta-line">{email}</p>
          </form>
        ) : (
          <Link href="/mgmt/login">Sign in</Link>
        )}
      </nav>
      <div>{children}</div>
    </div>
  );
}
