import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";

import { AuthSidePanel } from "@/components/AuthSidePanel";
import { registerAction } from "@/lib/auth-actions";
import { getSession } from "@/lib/auth";

export const metadata = {
  title: "Create your workspace · EvalOps Studio",
};

type Search = Promise<{ error?: string; email?: string; name?: string }>;

export default async function RegisterPage({ searchParams }: { searchParams: Search }) {
  const sp = await searchParams;
  const session = await getSession();
  if (session) {
    redirect("/app");
  }

  return (
    <div className="auth-shell">
      <div className="auth-grid">
        <section className="auth-pane">
          <Link className="auth-back" href="/">
            <ArrowLeft size={14} /> Back home
          </Link>
          <div className="auth-pane__form">
            <Link className="auth-brand" href="/">
              <img src="/brand/mark-evalops.svg" alt="" />
              <span>
                EvalOps<span className="sub">Studio</span>
              </span>
            </Link>
            <h1>Create your workspace</h1>
            <p className="auth-sub">
              Trace your first agent in under five minutes. Free during beta &mdash; no card required.
            </p>

            {sp?.error ? <p className="auth-error">{sp.error}</p> : null}

            <form action={registerAction}>
              <div className="auth-field">
                <label htmlFor="name">Full name</label>
                <input
                  id="name"
                  name="name"
                  type="text"
                  placeholder="Ada Lovelace"
                  autoComplete="name"
                  defaultValue={sp?.name ?? ""}
                  required
                />
              </div>
              <div className="auth-field">
                <label htmlFor="email">Work email</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="you@company.com"
                  autoComplete="email"
                  defaultValue={sp?.email ?? ""}
                  required
                />
              </div>
              <div className="auth-field">
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  placeholder="At least 8 characters"
                  autoComplete="new-password"
                  required
                  minLength={8}
                />
              </div>
              <div className="auth-field">
                <label htmlFor="org_name">Workspace name (optional)</label>
                <input
                  id="org_name"
                  name="org_name"
                  type="text"
                  placeholder="Rogue Labs"
                  autoComplete="organization"
                />
              </div>
              <label className="auth-checkbox">
                <input type="checkbox" name="terms" required defaultChecked /> I agree to the{" "}
                <a href="#" style={{ color: "var(--primary-300)", marginLeft: 4 }}>Terms</a>
                &nbsp;and&nbsp;
                <a href="#" style={{ color: "var(--primary-300)" }}>Privacy Policy</a>
              </label>
              <button type="submit" className="mk-btn mk-btn--primary mk-btn--block mk-btn--lg">
                Create workspace <ArrowRight />
              </button>
            </form>

            <p className="auth-foot">
              Already have a workspace? <Link href="/login">Sign in</Link>
            </p>
            <p className="auth-legal">
              By creating a workspace you&apos;ll receive setup tips and product updates. You can opt out at
              any time. We never train on your prompts or responses.
            </p>
          </div>
        </section>

        <AuthSidePanel variant="register" />
      </div>
    </div>
  );
}
