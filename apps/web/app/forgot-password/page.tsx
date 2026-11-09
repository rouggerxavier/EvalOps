import { RecoveryShell } from "@/components/RecoveryShell";
import { ForgotPasswordForm } from "@/components/RecoveryForms";

export const metadata = { title: "Recuperar senha - EvalOps Studio", robots: { index: false, follow: false }, referrer: "no-referrer" };

export default function RecoveryPage() {
  return <RecoveryShell title="Recuperar senha"><ForgotPasswordForm /></RecoveryShell>;
}
