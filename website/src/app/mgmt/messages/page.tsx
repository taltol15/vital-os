import { redirect } from "next/navigation";
import { AdminFrame } from "@/components/admin-frame";
import { currentAdmin, loadMessages } from "@/lib/admin-read";
import { formatDate } from "@/lib/format";
import { previewEnabled } from "@/lib/preview";

export const dynamic = "force-dynamic";

export default async function MessagesPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const preview = previewEnabled();
  const admin = await currentAdmin();
  if (!admin && !preview) redirect("/mgmt/login");
  const query = await searchParams;
  const messages = await loadMessages();
  return (
    <AdminFrame current="messages" email={admin?.email} preview={preview}>
      <header className="page-head">
        <p className="eyebrow">Contact</p>
        <h1>Messages</h1>
      </header>
      {query.error ? <p className="banner banner-warn">{query.error}</p> : null}
      <div className="stack">
        {messages.length === 0 ? <p>No messages.</p> : null}
        {messages.map((message) => (
          <article className="card" key={message.id}>
            <header className="release header">
              <h2>{message.subject}</h2>
              <span className="badge badge-quiet">{message.read_at ? "Read" : "New"}</span>
            </header>
            <p className="facts">
              <span>{message.name}</span>
              <span className="mono">{message.email}</span>
              <span>{formatDate(message.created_at, "en")}</span>
            </p>
            <p>{message.message}</p>
            {message.read_at ? null : (
              <form action="/api/mgmt/messages" method="post">
                <input type="hidden" name="id" value={message.id} />
                <button className="button button-small button-ghost" type="submit">Mark read</button>
              </form>
            )}
          </article>
        ))}
      </div>
    </AdminFrame>
  );
}
