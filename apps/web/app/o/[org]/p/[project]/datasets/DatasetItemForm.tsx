type Props = {
  org: string;
  project: string;
  datasetId: string;
  action: (formData: FormData) => Promise<void>;
};

export function DatasetItemForm({ org, project, datasetId, action }: Props) {
  return (
    <form className="ops-form ops-form__grid" action={action}>
      <input type="hidden" name="org" value={org} />
      <input type="hidden" name="project" value={project} />
      <input type="hidden" name="dataset_id" value={datasetId} />
      <label className="ops-form__field">
        <span>Pergunta</span>
        <input name="question" placeholder="Como cancelo meu pedido?" minLength={1} required />
      </label>
      <label className="ops-form__field">
        <span>Resposta esperada</span>
        <input name="expected_answer" placeholder="Em Meus pedidos, antes do envio." />
      </label>
      <button type="submit" className="btn btn--primary">Adicionar</button>
    </form>
  );
}
