"use client";

import { useState } from "react";

import { deleteApiKeyAction, revokeApiKeyAction } from "@/lib/actions";

type Props = {
  org: string;
  project: string;
  projectId: string;
  keyId: string;
  revoked: boolean;
};

export function ApiKeyActions({ org, project, projectId, keyId, revoked }: Props) {
  const [confirming, setConfirming] = useState(false);
  const action = revoked ? deleteApiKeyAction : revokeApiKeyAction;

  if (!confirming) {
    return (
      <button type="button" className="btn btn--sm" onClick={() => setConfirming(true)}>
        {revoked ? "Excluir" : "Revogar"}
      </button>
    );
  }

  return (
    <div className="ops-confirm" role="group" aria-label={revoked ? "Confirmar exclusão" : "Confirmar revogação"}>
      <span>{revoked ? "Excluir chave?" : "Revogar chave?"}</span>
      <form action={action}>
        <input type="hidden" name="org" value={org} />
        <input type="hidden" name="project" value={project} />
        <input type="hidden" name="project_id" value={projectId} />
        <input type="hidden" name="key_id" value={keyId} />
        <button type="submit" className="btn btn--danger btn--sm">Confirmar</button>
      </form>
      <button type="button" className="btn btn--sm" onClick={() => setConfirming(false)}>Cancelar</button>
    </div>
  );
}
