type PreviewPillProps = {
  label?: string;
};

export function PreviewPill({ label = "preview" }: PreviewPillProps) {
  return (
    <span className="preview-pill">
      <span className="preview-pill__dot" aria-hidden="true" />
      {label}
    </span>
  );
}
