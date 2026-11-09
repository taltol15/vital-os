"use client";

import { useActionState } from "react";
import { signIn, type SignInState } from "@/app/mgmt/actions";

export function LoginForm() {
  const [state, action, pending] = useActionState(signIn, {} as SignInState);
  return (
    <form className="form" action={action} style={{ paddingTop: "2rem" }}>
      <p className="eyebrow">Vital OS</p>
      <h1>Admin</h1>
      <p className="lede">Email sign-in. An account that is not on the allowlist is signed out and cannot manage anything.</p>
      {state.error ? <p className="banner banner-warn" role="alert">{state.error}</p> : null}
      <label className="field">
        <span>Email</span>
        <input name="email" type="email" autoComplete="username" required />
      </label>
      <label className="field">
        <span>Password</span>
        <input name="password" type="password" autoComplete="current-password" required />
      </label>
      <button className="button" type="submit" disabled={pending}>{pending ? "Signing in" : "Sign in"}</button>
    </form>
  );
}
