export type EndpointDescriptor = {
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  path: string;
  desc?: string;
};

type EndpointSnippetProps = {
  endpoint: EndpointDescriptor;
};

export function EndpointSnippet({ endpoint }: EndpointSnippetProps) {
  return (
    <div className="endpoint-snippet">
      <span className={`endpoint-snippet__method method-${endpoint.method}`}>{endpoint.method}</span>
      <span>{endpoint.path}</span>
      {endpoint.desc ? <div className="faint" style={{ marginTop: 8 }}>{endpoint.desc}</div> : null}
    </div>
  );
}
