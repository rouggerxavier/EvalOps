import Link from "next/link";
import { GitBranch, HelpCircle, Plus } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createPromptAction, createPromptVersionAction } from "@/lib/actions";
import { getPromptUsage, getPromptVersions, getPrompts, hasAuthToken, resolveProject } from "@/lib/api";
import { safeErrorMessage } from "@/lib/safe-error";
import type { Prompt, PromptUsage, PromptVersion } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ prompt?: string; created?: string; versioned?: string; error?: string }>;
};

function relTime(iso: string): string {
  const diff = Date.now() - Date.parse(iso);
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "agora";
  if (mins < 60) return `há ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `há ${hrs} h`;
  return `há ${Math.floor(hrs / 24)} dias`;
}

function DiffView({ current, previous }: { current: PromptVersion; previous: PromptVersion | null }) {
  const currentLines = current.template.split("\n");

  if (!previous) {
    return (
      <div className="ops-diff">
        {currentLines.map((line, index) => (
          <div className="ops-diff__line ops-diff__line--add" key={index}>
            <span aria-hidden="true">+</span><code>{line || " "}</code>
          </div>
        ))}
      </div>
    );
  }

  const previousLines = previous.template.split("\n");
  const maxLength = Math.max(currentLines.length, previousLines.length);
  const lines: Array<{ text: string; kind: "add" | "del" | "same" }> = [];

  for (let index = 0; index < maxLength; index++) {
    const currentLine = currentLines[index];
    const previousLine = previousLines[index];
    if (currentLine === previousLine) {
      if (currentLine !== undefined) lines.push({ text: currentLine, kind: "same" });
    } else {
      if (previousLine !== undefined) lines.push({ text: previousLine, kind: "del" });
      if (currentLine !== undefined) lines.push({ text: currentLine, kind: "add" });
    }
  }

  return (
    <div className="ops-diff">
      {lines.map((line, index) => (
        <div className={`ops-diff__line ops-diff__line--${line.kind}`} key={index}>
          <span aria-hidden="true">{line.kind === "add" ? "+" : line.kind === "del" ? "−" : " "}</span>
          <code>{line.text || " "}</code>
        </div>
      ))}
    </div>
  );
}

function modelFor(version: PromptVersion | null): string {
  const value = version?.metadata?.model_default;
  return typeof value === "string" ? value : "Sem dados";
}

export default async function PromptsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);
  const canWrite = resolved.membership?.permissions.includes("write") ?? false;
  const prompts = (await getPrompts(resolved.project_id)).data;
  const versionsByPrompt = new Map(
    await Promise.all(
      prompts.map(async (prompt) => [prompt.id, (await getPromptVersions(prompt.id)).data] as const),
    ),
  );
  const usageByPrompt = new Map<string, PromptUsage | null>(
    await Promise.all(
      prompts.map(async (prompt) => {
        try {
          return [prompt.id, await getPromptUsage(prompt.id, 3)] as const;
        } catch {
          return [prompt.id, null] as const;
        }
      }),
    ),
  );

  const selectedId = qp.prompt ?? prompts[0]?.id;
  const selected = prompts.find((prompt) => prompt.id === selectedId) ?? prompts[0] ?? null;
  const selectedVersions = selected ? versionsByPrompt.get(selected.id) ?? [] : [];
  const latest = selectedVersions[selectedVersions.length - 1] ?? null;
  const previous = selectedVersions[selectedVersions.length - 2] ?? null;
  const usage = selected ? usageByPrompt.get(selected.id) ?? null : null;
  const baseUrl = `/o/${org}/p/${project}/prompts`;
  const errorMessage = qp.error ? safeErrorMessage(qp.error, "Falha ao salvar prompt.") : null;
  const successMessage = qp.created ? "Prompt criado." : qp.versioned ? "Nova versão publicada." : null;

  return (
    <div className="page ops-page">
      <header className="ops-page-header">
        <div className="ops-page-header__copy">
          <h1 className="ops-page-header__title">Prompts</h1>
          <p className="ops-page-header__subtitle">
            As instruções que a IA recebe, com o histórico de cada versão.
          </p>
        </div>
        {canWrite ? <details className="ops-create" open={prompts.length === 0}>
          <summary className="btn btn--sm btn--primary"><Plus size={12} /> Novo prompt</summary>
          <form action={createPromptAction} className="ops-form">
            <input type="hidden" name="org" value={org} />
            <input type="hidden" name="project" value={project} />
            <input type="hidden" name="project_id" value={resolved.project_id} />
            <div className="ops-form__grid">
              <label className="ops-form__field">
                <span>Identificador</span>
                <input name="slug" placeholder="Identificador curto" required />
              </label>
              <label className="ops-form__field">
                <span>Descrição</span>
                <input name="description" placeholder="Para que este prompt serve" />
              </label>
            </div>
            <label className="ops-form__field">
              <span>Template</span>
              <textarea name="template" rows={5} required />
            </label>
            <label className="ops-form__field">
              <span>Variáveis JSON</span>
              <textarea name="variables_json" rows={2} defaultValue="{}" />
            </label>
            <label className="ops-form__field">
              <span>Metadata JSON</span>
              <textarea name="metadata_json" rows={2} defaultValue="{}" />
            </label>
            <button type="submit" className="btn btn--sm btn--primary">Criar prompt</button>
          </form>
        </details> : null}
      </header>

      {errorMessage && <div className="ops-flash ops-flash--error" role="alert">{errorMessage}</div>}
      {successMessage && <div className="ops-flash ops-flash--success" role="status">{successMessage}</div>}

      {selected ? (
        <div className="ops-prompts-layout">
          <nav className="ops-prompts-list ops-panel" aria-label="Lista de prompts">
            <header className="ops-panel__header"><h2>{prompts.length} prompts</h2></header>
            {prompts.map((prompt: Prompt) => {
              const active = prompt.id === selected.id;
              const promptVersions = versionsByPrompt.get(prompt.id) ?? [];
              const promptUsage = usageByPrompt.get(prompt.id);
              const currentVersion = promptVersions[promptVersions.length - 1];
              return (
                <Link
                  key={prompt.id}
                  href={`${baseUrl}?prompt=${encodeURIComponent(prompt.id)}`}
                  className={`ops-prompts-list__item${active ? " is-active" : ""}`}
                  aria-current={active ? "page" : undefined}
                >
                  <strong className="ops-mono">{prompt.slug}</strong>
                  <span className="ops-prompts-list__meta">
                    {prompt.current_version} {prompt.current_version === 1 ? "versão" : "versões"}
                    {" · "}{promptUsage ? `${promptUsage.usage_count.toLocaleString("pt-BR")} traces` : "Sem dados de uso"}
                    {" · "}{currentVersion ? relTime(currentVersion.created_at) : "Sem dados de versão"}
                  </span>
                </Link>
              );
            })}
          </nav>

          <div className="ops-prompt-detail">
            <section className="ops-panel">
              <header className="ops-prompt-detail__header">
                <div>
                  <h2 className="ops-mono">{selected.slug}</h2>
                  <p>{selected.description ?? "Sem descrição disponível."}</p>
                </div>
                {selectedVersions.length > 0 && (
                  canWrite ? <details className="ops-create ops-create--version" id="prompt-version">
                    <summary className="btn btn--sm"><GitBranch size={12} /> Nova versão</summary>
                    <form action={createPromptVersionAction} className="ops-form">
                      <input type="hidden" name="org" value={org} />
                      <input type="hidden" name="project" value={project} />
                      <input type="hidden" name="prompt_id" value={selected.id} />
                      <label className="ops-form__field">
                        <span>Template</span>
                        <textarea name="template" rows={6} required defaultValue={latest?.template ?? ""} />
                      </label>
                      <label className="ops-form__field">
                        <span>Variáveis JSON</span>
                        <textarea name="variables_json" rows={3} defaultValue={JSON.stringify(latest?.variables ?? {}, null, 2)} />
                      </label>
                      <label className="ops-form__field">
                        <span>Metadata JSON</span>
                        <textarea name="metadata_json" rows={3} defaultValue={JSON.stringify(latest?.metadata ?? {}, null, 2)} />
                      </label>
                      <button type="submit" className="btn btn--sm btn--primary">Publicar versão</button>
                    </form>
                  </details> : null
                )}
              </header>
              <div className="ops-prompt-status" role="status">
                <span className="ops-status ops-status--unknown"><HelpCircle size={14} aria-hidden="true" /> Sem dados</span>
                <span>Sem dados de avaliação por versão. A API não associa scores à versão do prompt.</span>
              </div>
            </section>

            <section className="ops-panel">
              <header className="ops-panel__header">
                <h3>Versão atual: v{latest?.version ?? selected.current_version}</h3>
                <span className="ops-mono">{modelFor(latest)}</span>
              </header>
              {latest ? (
                <pre className="ops-code">{latest.template}</pre>
              ) : (
                <p className="ops-panel__empty">Sem dados de template para esta versão.</p>
              )}
            </section>

            <div className="ops-prompt-bottom">
              <section className="ops-panel">
                <header className="ops-panel__header">
                  <h3>Versões</h3><span className="ops-panel__muted">Score médio</span>
                </header>
                {selectedVersions.length ? (
                  selectedVersions.slice(-3).reverse().map((version) => (
                    <div className="ops-prompt-row" key={version.id}>
                      <strong>v{version.version}</strong>
                      <span className="ops-panel__muted">{relTime(version.created_at)}</span>
                      <span className="ops-prompt-row__score">Sem dados</span>
                    </div>
                  ))
                ) : (
                  <p className="ops-panel__empty">Sem dados de versões.</p>
                )}
                {previous && latest && (
                  <details className="ops-prompt-diff">
                    <summary>Ver diferenças com v{previous.version}</summary>
                    <DiffView current={latest} previous={previous} />
                  </details>
                )}
              </section>

              <section className="ops-panel">
                <header className="ops-panel__header">
                  <h3>Usado por</h3>
                  <span className="ops-panel__muted">
                    {usage ? `${usage.usage_count.toLocaleString("pt-BR")} traces` : "Sem dados"}
                  </span>
                </header>
                {usage?.traces.length ? (
                  usage.traces.map((trace) => (
                    <div className="ops-prompt-row ops-prompt-row--trace" key={trace.trace_id}>
                      <span className="ops-mono">{trace.name || trace.trace_id}</span>
                      <span className="ops-panel__muted">{trace.environment} · {trace.status}</span>
                    </div>
                  ))
                ) : (
                  <p className="ops-panel__empty">
                    {usage ? "Nenhum trace associado a este prompt." : "Sem dados de uso."}
                  </p>
                )}
                {usage && usage.traces.length < usage.usage_count && (
                  <p className="ops-panel__note">Mostrando os 3 traces mais recentes de {usage.usage_count.toLocaleString("pt-BR")}.</p>
                )}
              </section>
            </div>
          </div>
        </div>
      ) : (
        <section className="ops-panel ops-empty">
          <h2 className="ops-empty__title">Nenhum prompt</h2>
          <p className="ops-empty__description">Crie um prompt versionado para começar.</p>
        </section>
      )}
    </div>
  );
}
