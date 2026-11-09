"use server";

import { redirect } from "next/navigation";
import { supabaseConfigured } from "@/lib/env";
import { userClient } from "@/lib/supabase/server";

export type SignInState = { error?: string };

export async function signIn(_prev: SignInState, formData: FormData): Promise<SignInState> {
  if (!supabaseConfigured()) return { error: "Sign-in is not configured." };
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");
  if (!email || !password) return { error: "Enter the email and password." };
  const supabase = await userClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) return { error: "Those credentials were not accepted." };
  const { data } = await supabase.auth.getUser();
  const user = data.user;
  if (!user) return { error: "Those credentials were not accepted." };
  const allow = await supabase.from("admin_allowlist").select("user_id").eq("user_id", user.id).maybeSingle();
  if (!allow.data) {
    await supabase.auth.signOut();
    return { error: "This account is not on the admin allowlist." };
  }
  redirect("/mgmt");
}

export async function signOut(): Promise<void> {
  if (supabaseConfigured()) {
    const supabase = await userClient();
    await supabase.auth.signOut();
  }
  redirect("/mgmt/login");
}
