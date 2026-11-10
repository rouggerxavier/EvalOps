"use client";
import Link from "next/link";
import { useState } from "react";
export function CaptureLink({ org, project, trace, datasets }: { org: string; project: string; trace: string; datasets: { id: string; slug: string }[] }) {
  const [dataset, setDataset] = useState("");
  return <div><label>Dataset para curadoria<select value={dataset} onChange={event => setDataset(event.target.value)}><option value="">Selecione</option>{datasets.map(row => <option key={row.id} value={row.id}>{row.slug}</option>)}</select></label>{dataset && <Link href={`/o/${org}/p/${project}/datasets/${dataset}/cases?trace=${encodeURIComponent(trace)}`}>Criar caso a partir da evidência</Link>}</div>;
}
