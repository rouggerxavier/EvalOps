import { RecoveryShell } from "@/components/RecoveryShell";
import { ResetPasswordForm } from "@/components/RecoveryForms";

export const metadata = { title: "Redefinir senha - EvalOps Studio", robots: { index: false, follow: false }, referrer: "no-referrer" };

export default function RecoveryPage() {
  return <RecoveryShell title="Redefinir senha"><ResetPasswordForm /></RecoveryShell>;
}
