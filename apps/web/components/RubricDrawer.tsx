import { FileCode2, GitBranch, X } from "lucide-react";
import Link from "next/link";

import type { Rubric, RubricVersion } from "@/lib/types";

type RubricDrawerProps = {
  closeHref: string;
  rubric: Rubric;
  versions: RubricVersion[];
};

function latestVersion(versions: RubricVersion[], currentVersion: number): RubricVersion | null {
  return (
    versions.find((version) => version.version === currentVersion) ??
    versions.reduce<RubricVersion | null>((latest, version) => {
      if (!latest || version.version > latest.version) return version;
      return latest;
    }, null)
  );
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function YamlPreview({ code }: { code: string }) {
  const lines = code.split("\n");

  return (
    <div className="evo-rubric-drawer__yaml">
      <pre className="evo-code__body evo-rubric-drawer__code">
        {lines.map((line, index) => (
          <span className="evo-rubric-drawer__line" key={index}>
            <span className="evo-rubric-drawer__line-no">{index + 1}</span>
            <span className="evo-rubric-drawer__line-text">{line || " "}</span>
          </span>
        ))}
      </pre>
    </div>
  );
}

export function RubricDrawer({ closeHref, rubric, versions }: RubricDrawerProps) {
  const version = latestVersion(versions, rubric.current_version);
  const yamlSource = version?.yaml_source ?? "";
  const evaluatorCount = version?.parsed_spec?.evaluators?.length ?? 0;
  const lineCount = yamlSource ? yamlSource.split("\n").length : 0;

  return (
    <aside className="evo-card evo-rubric-drawer" aria-labelledby="rubric-drawer-title">
      <div className="evo-card__header evo-rubric-drawer__header">
        <div>
          <p className="evo-page-header__eyebrow">Rubrica selecionada</p>
          <h3 className="evo-card__title" id="rubric-drawer-title">
            {rubric.slug}
          </h3>
          <p className="evo-card__subtitle">YAML read-only da versao ativa.</p>
        </div>
        <Link className="evo-btn evo-btn--ghost evo-btn--sm evo-btn--icon" href={closeHref} aria-label="Fechar YAML">
          <X size={14} />
        </Link>
      </div>

      <div className="evo-card__body evo-rubric-drawer__body">
        <div className="evo-rubric-drawer__facts">
          <span className="evo-badge evo-badge--eval">
            <FileCode2 size={11} /> YAML
          </span>
          <span className="evo-badge">
            <GitBranch size={11} /> v{version?.version ?? rubric.current_version}
          </span>
          <span className="evo-tag">{evaluatorCount} avaliador{evaluatorCount !== 1 ? "es" : ""}</span>
          {lineCount > 0 && <span className="evo-tag">{lineCount} linhas</span>}
        </div>

        <div className="evo-code" data-mode="read-only">
          <div className="evo-code__header">
            <span>{version ? `rubric_${rubric.slug}_v${version.version}.yaml` : "rubric.yaml"}</span>
            <span>somente leitura</span>
          </div>
          {version ? (
            <YamlPreview code={yamlSource} />
          ) : (
            <div className="evo-empty-row">Nenhuma versao retornada pelo backend.</div>
          )}
        </div>

        {versions.length > 0 && (
          <div className="evo-rubric-drawer__versions" aria-label="Versoes da rubrica">
            {[...versions]
              .sort((a, b) => b.version - a.version)
              .slice(0, 4)
              .map((item) => (
                <div className="evo-rubric-drawer__version" key={item.id}>
                  <span className="evo-mono">v{item.version}</span>
                  <span>{formatDate(item.created_at)}</span>
                  {item.version === rubric.current_version && <strong>ativa</strong>}
                </div>
              ))}
          </div>
        )}
      </div>
    </aside>
  );
}
