import { z } from "zod";

const control = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/;

export const contactFields = z.object({
  name: z.string().trim().min(1, "Enter a name.").max(80, "Name is too long."),
  email: z.string().trim().email("Enter a valid email.").max(120, "Email is too long."),
  subject: z.string().trim().min(1, "Enter a subject.").max(120, "Subject is too long."),
  message: z.string().trim().min(1, "Enter a message.").max(5000, "Message is too long."),
});

export type ContactInput = z.infer<typeof contactFields>;

export type ContactResult =
  | { ok: true; honeypot: true }
  | { ok: true; honeypot: false; value: ContactInput; locale: "en" | "he" }
  | { ok: false; status: 400; errors: Record<string, string> };

export function validateContact(input: {
  name?: unknown;
  email?: unknown;
  subject?: unknown;
  message?: unknown;
  fax_number?: unknown;
  locale?: unknown;
}): ContactResult {
  const fax = typeof input.fax_number === "string" ? input.fax_number.trim() : "";
  if (fax) return { ok: true, honeypot: true };
  const parsed = contactFields.safeParse({
    name: input.name ?? "",
    email: input.email ?? "",
    subject: input.subject ?? "",
    message: input.message ?? "",
  });
  if (!parsed.success) {
    const errors: Record<string, string> = {};
    for (const issue of parsed.error.issues) {
      const key = String(issue.path[0] ?? "form");
      if (!errors[key]) errors[key] = issue.message;
    }
    return { ok: false, status: 400, errors };
  }
  if (control.test(parsed.data.name) || parsed.data.name.includes("\n")) {
    return { ok: false, status: 400, errors: { name: "Name has characters that are not allowed." } };
  }
  if (control.test(parsed.data.subject) || parsed.data.subject.includes("\n")) {
    return { ok: false, status: 400, errors: { subject: "Subject has characters that are not allowed." } };
  }
  if (control.test(parsed.data.message) || control.test(parsed.data.email)) {
    return { ok: false, status: 400, errors: { message: "Message has characters that are not allowed." } };
  }
  const locale = input.locale === "he" ? "he" : "en";
  return { ok: true, honeypot: false, value: parsed.data, locale };
}
