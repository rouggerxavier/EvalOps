import Link from "next/link";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { getTraces, hasAuthToken, resolveProject } from "@/lib/api";
import { QuickstartCard } from "@/components/QuickstartCard";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ status?: string; environment?: string; name?: string }>;
};

export default async function TracesListPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="container" />;
  }

  const resolved = await resolveProject(org, project);
  const traces = await getTraces({
    projectId: resolved.project_id,
    status: qp.status,
    environment: qp.environment,
    name: qp.name,
    limit: 50,
  });

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1 style={{ margin: 0 }}>Traces</h1>
        <Link href={`/o/${org}/p/${project}`}>Voltar ao overview</Link>
      </div>

      <form className="panel row" style={{ marginTop: 12 }} method="get">
        <input name="name" defaultValue={qp.name} placeholder="buscar por nome" />
        <select name="status" defaultValue={qp.status ?? ""}>
          <option value="">status: todos</option>
          <option value="ok">ok</option>
          <option value="partial">partial</option>
          <option value="error">error</option>
        </select>
        <select name="environment" defaultValue={qp.environment ?? ""}>
          <option value="">env: todos</option>
          <option value="dev">dev</option>
          <option value="staging">staging</option>
          <option value="prod">prod</option>
        </select>
        <button type="submit">Filtrar</button>
      </form>

      <section className="panel" style={{ marginTop: 12 }}>
        {traces.data.length === 0 ? (
          <QuickstartCard
            title="Nenhum trace ainda"
            description="Conecte o SDK para comeÃ§ar a visualizar traces, spans e custos neste projeto."
            steps={[
              "Crie uma API key em API Keys com escopo ingest.",
              "Configure EVALOPS_API_KEY no seu serviÃ§o.",
              "Envie alguns requests instrumentados e atualize esta tela.",
            ]}
            snippet={`import evalops\n\nevalops.init(api_key="evk_prod_...", project="demo", environment="prod")\n\n@evalops.trace("chat.answer")\ndef answer(msg: str):\n    with evalops.span("llm_call", type="llm_call"):\n        return "ok"`}
          />
        ) : (
          <table>
            <thead>
              <tr>
                <th>Nome</th>
                <th>Status</th>
                <th>Ambiente</th>
                <th>DuraÃ§Ã£o</th>
                <th>Tokens</th>
                <th>Custo USD</th>
                <th>Criado em</th>
              </tr>
            </thead>
            <tbody>
              {traces.data.map((trace) => (
                <tr key={trace.id}>
                  <td>
                    <Link href={`/o/${org}/p/${project}/traces/${trace.id}`}>{trace.name}</Link>
                  </td>
                  <td className={`status-${trace.status}`}>{trace.status}</td>
                  <td>{trace.environment}</td>
                  <td>{trace.duration_ms}ms</td>
                  <td>
                    {trace.total_tokens_in}/{trace.total_tokens_out}
                  </td>
                  <td>{trace.total_cost_usd.toFixed(6)}</td>
                  <td>{new Date(trace.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}



