type QuickstartCardProps = {
  title: string;
  description: string;
  steps: string[];
  snippet?: string;
};

export function QuickstartCard({ title, description, steps, snippet }: QuickstartCardProps) {
  return (
    <div className="quickstart">
      <h3>{title}</h3>
      <p>{description}</p>
      <ol>
        {steps.map((step, idx) => (
          <li key={`${idx}-${step}`}>{step}</li>
        ))}
      </ol>
      {snippet ? (
        <pre>
          <code>{snippet}</code>
        </pre>
      ) : null}
    </div>
  );
}
