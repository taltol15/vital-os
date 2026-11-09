"use client";

import { useState } from "react";
import type { Dictionary } from "@/i18n/en";

export function ContactForm({ locale, dict, initial }: { locale: "en" | "he"; dict: Dictionary["contact"]; initial?: string }) {
  const [status, setStatus] = useState(initial ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  const banner =
    status === "sent" || status === "1" ? dict.sent : status === "rate" ? dict.rate : status === "unavailable" ? dict.unavailable : status === "error" ? dict.invalid : "";

  return (
    <form
      className="form"
      action="/api/contact"
      method="post"
      onSubmit={async (event) => {
        event.preventDefault();
        setPending(true);
        setErrors({});
        const data = new FormData(event.currentTarget);
        const response = await fetch("/api/contact", {
          method: "POST",
          body: data,
          headers: { Accept: "application/json" },
        });
        setPending(false);
        if (response.status === 200) {
          setStatus("sent");
          event.currentTarget.reset();
          return;
        }
        if (response.status === 429) {
          setStatus("rate");
          return;
        }
        if (response.status === 503) {
          setStatus("unavailable");
          return;
        }
        const body = (await response.json().catch(() => ({}))) as { errors?: Record<string, string> };
        setErrors(body.errors ?? {});
        setStatus("error");
      }}
    >
      {banner ? <p className={status === "sent" || status === "1" ? "banner" : "banner banner-warn"} role="status">{banner}</p> : null}
      <input type="hidden" name="locale" value={locale} />
      <label className="field">
        <span>{dict.name}</span>
        <input name="name" autoComplete="name" required maxLength={80} aria-invalid={Boolean(errors.name)} />
        {errors.name ? <span className="error">{errors.name}</span> : null}
      </label>
      <label className="field">
        <span>{dict.email}</span>
        <input name="email" type="email" autoComplete="email" required maxLength={120} aria-invalid={Boolean(errors.email)} />
        {errors.email ? <span className="error">{errors.email}</span> : null}
      </label>
      <label className="field">
        <span>{dict.subject}</span>
        <input name="subject" required maxLength={120} aria-invalid={Boolean(errors.subject)} />
        {errors.subject ? <span className="error">{errors.subject}</span> : null}
      </label>
      <label className="field">
        <span>{dict.message}</span>
        <textarea name="message" required maxLength={5000} aria-invalid={Boolean(errors.message)} />
        {errors.message ? <span className="error">{errors.message}</span> : null}
      </label>
      <label className="honeypot">
        {dict.fax}
        <input name="fax_number" tabIndex={-1} autoComplete="off" />
      </label>
      <button className="button" type="submit" disabled={pending}>{pending ? dict.sending : dict.send}</button>
    </form>
  );
}
