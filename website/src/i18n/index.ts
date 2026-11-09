import { en, type Dictionary } from "@/i18n/en";
import { he } from "@/i18n/he";

export type Locale = "en" | "he";

export function isLocale(value: string): value is Locale {
  return value === "en" || value === "he";
}

export function dictionary(locale: string): Dictionary {
  return locale === "he" ? he : en;
}

export function direction(locale: string): "rtl" | "ltr" {
  return locale === "he" ? "rtl" : "ltr";
}
