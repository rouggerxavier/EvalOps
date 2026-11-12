// Local contract fixture only: no database, mail transport or external services.
import { createServer } from "node:http";

if (process.env.E2E_INVITATIONS !== "1") throw new Error("Set E2E_INVITATIONS=1 for the local invitation fixture");
const port = Number(process.env.E2E_INVITATIONS_API_PORT ?? 18145);
const date = "2026-11-09T12:00:00Z";
const project = { id: "prj_test", organization_id: "org_test", slug: "project", name: "Projeto QA", default_environment: "prod", created_at: date };
const permissions = { owner: ["admin", "destructive", "read", "write"], member: ["read", "write"], viewer: ["read"], legacy: [] };
let members, invitations, calls, failure;
function reset() {
  members = [
    { user_id: "owner", name: "Owner QA", email: "owner@example.invalid", role: "owner", joined_at: date },
    { user_id: "member", name: "Member QA", email: "member@example.invalid", role: "member", joined_at: date },
    { user_id: "viewer", name: "Viewer QA", email: "viewer@example.invalid", role: "viewer", joined_at: date },
    { user_id: "legacy", name: "Legacy QA", email: "legacy@example.invalid", role: "legacy", joined_at: date },
  ];
  invitations = []; calls = []; failure = null;
}
reset();
const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${port}`);
  const path = url.pathname.replace(/^\/v1/, "");
  const send = (status, data) => { res.writeHead(status, { "Content-Type": "application/json" }); res.end(status === 204 ? undefined : JSON.stringify(data)); };
  try {
    let text = ""; for await (const chunk of req) { text += chunk; if (text.length > 16384) return send(413, {}); }
    const body = text ? JSON.parse(text) : {};
    if (path === "/_test/reset") { reset(); return send(200, {}); }
    if (path === "/_test/state") return send(200, { calls, invitations, members });
    if (path === "/_test/failure") { failure = body.detail; return send(200, {}); }
    const userId = req.headers.authorization?.replace("Bearer fixture-", "");
    const member = members.find((m) => m.user_id === userId);
    if (!member) return send(401, { detail: "invalid_session" });
    calls.push({ path, method: req.method, userId });
    if (path === "/auth/session") return send(200, { user: { id: userId, name: member.name, email: member.email }, workspace: { org_id: "org_test", org_slug: "org", org_name: "Organização QA", project_id: project.id, project_slug: "project", project_name: project.name } });
    if (path === "/resolve") return send(200, { org_id: "org_test", org_slug: "org", org_name: "Organização QA", project_id: project.id, project_slug: "project", project_name: project.name, membership: { role: member.role, permissions: permissions[member.role] ?? [] } });
    if (path === "/invitations/accept") {
      if (req.method !== "POST") return send(405, {});
      if (body.token === "x".repeat(43)) return send(400, { detail: "invalid_invitation" });
      if (body.token === "u".repeat(43)) return send(200, { organization_id: "org_restricted", organization_slug: "restrita", role: "legacy", permissions: [], already_member: true });
      if (body.token === "n".repeat(43)) return send(200, { organization_id: "org_empty", organization_slug: "sem-projetos", role: "viewer", permissions: ["read"], already_member: false });
      return send(200, { organization_id: "org_test", organization_slug: "org", role: member.role, permissions: permissions[member.role], already_member: true });
    }
    if (path === "/projects") return send(200, { data: url.searchParams.get("organization_id") === "org_empty" ? [] : [project] });
    if (path.endsWith("/notifications")) return send(200, { data: [{ id: "notice", kind: "info", title: "Avaliação concluída", read_at: null }], next_cursor: null });
    if (path.endsWith("/attention")) return send(200, { count: 0, data: [] });
    if (path === "/organizations/org_test/members" && req.method === "GET") return send(200, { data: members, next_cursor: null });
    if (path.includes("/organizations/") && member.role !== "owner") return send(403, { detail: "forbidden" });
    if (failure && req.method !== "GET") { const error = failure; failure = null; return send(error === "invitations_unavailable" ? 503 : 409, { detail: error }); }
    if (path === "/organizations/org_test/invitations") {
      if (req.method === "GET") return send(200, { data: invitations, next_cursor: null });
      for (const invitation of invitations) if (invitation.email === body.email && ["pending", "sent"].includes(invitation.status)) invitation.status = "revoked";
      const invitation = { id: `inv_${invitations.length}`, organization_id: "org_test", email: body.email, role: body.role, invited_by_user_id: userId, status: "sent", created_at: date, expires_at: "2026-11-10T12:00:00Z", accepted_at: null, revoked_at: null };
      invitations.unshift(invitation); return send(202, invitation);
    }
    if (/\/invitations\/inv_\d+\/revoke$/.test(path)) { const invitation = invitations.find((i) => path.includes(`/${i.id}/`)); if (!invitation) return send(404, {}); invitation.status = "revoked"; return send(204); }
    if (path === "/organizations/org_test/ownership/transfer") { members.find((m) => m.user_id === body.user_id).role = "owner"; member.role = "member"; return send(204); }
    if (path.startsWith("/organizations/org_test/members/")) {
      const target = members.find((m) => m.user_id === path.split("/").at(-1));
      if (!target) return send(404, {});
      if (target.role === "owner" && members.filter((m) => m.role === "owner").length === 1) return send(409, { detail: "last_owner" });
      if (req.method === "DELETE") { members = members.filter((m) => m !== target); return send(204); }
      target.role = body.role; return send(200, target);
    }
    if (path.endsWith("/usage")) return send(200, { traces_ingested: 0, spans_ingested: 0, evaluations_run: 0, exports_created: 0 });
    if (path.endsWith("/subscription")) return send(200, { plan: { monthly_trace_limit: 100, monthly_span_limit: 100, monthly_eval_limit: 100, monthly_export_limit: 100, monthly_judge_budget_usd: 1 } });
    if (path.endsWith("/rubrics") || path.endsWith("/jobs") || path.endsWith("/prompts")) return send(200, { data: [], next_cursor: null });
    return send(404, { detail: "not_found" });
  } catch { return send(500, { detail: "fixture_error" }); }
});
server.listen(port, "127.0.0.1", () => process.stdout.write(`Invitation contract fixture on ${port}\n`));
