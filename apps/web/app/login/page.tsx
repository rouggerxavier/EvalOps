import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";

import { AuthSidePanel } from "@/components/AuthSidePanel";
import { loginAction } from "@/lib/auth-actions";
import { getSession } from "@/lib/auth";

export const metadata = {
  title: "Sign in · EvalOps Studio",
};

type Search = Promise<{ error?: string; email?: string; redirected?: string }>;

export default async function LoginPage({ searchParams }: { searchParams: Search }) {
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
            <h1>Welcome back</h1>
            <p className="auth-sub">
              Sign in to your workspace to keep tracing, evaluating and shipping.
            </p>

            {sp?.error ? <p className="auth-error">{sp.error}</p> : null}

            <form action={loginAction}>
              <div className="auth-field">
                <label htmlFor="email">Email</label>
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
                <div className="auth-field__row">
                  <label htmlFor="password">Password</label>
                </div>
                <input
                  id="password"
                  name="password"
                  type="password"
                  placeholder="••••••••"
                  autoComplete="current-password"
                  required
                />
              </div>
              <label className="auth-checkbox">
                <input type="checkbox" name="remember" defaultChecked /> Keep me signed in for 30 days
              </label>
              <button type="submit" className="mk-btn mk-btn--primary mk-btn--block mk-btn--lg">
                Sign in <ArrowRight />
              </button>
            </form>

            <p className="auth-foot">
              Don&apos;t have a workspace? <Link href="/register">Create one</Link>
            </p>
            <p className="auth-legal">
              By signing in you agree to our <a href="#">Terms</a> and <a href="#">Privacy Policy</a>.
              Single sign-on (SSO) is available on the Team plan.
            </p>
          </div>
        </section>

        <AuthSidePanel variant="login" />
      </div>
    </div>
  );
}
