type JsonBlockProps = {
  value: unknown;
  language?: "json" | "yaml" | "text";
};

export function JsonBlock({ value, language = "json" }: JsonBlockProps) {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? "-", null, 2);
  return (
    <pre className="code" data-language={language}>
      <code>{text}</code>
    </pre>
  );
}
