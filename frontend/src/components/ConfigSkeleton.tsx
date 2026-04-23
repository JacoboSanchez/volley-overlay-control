export default function ConfigSkeleton() {
  return (
    <div className="config-skeleton" aria-busy="true" aria-live="polite">
      <div className="config-skeleton-line config-skeleton-line-title" />
      <div className="config-skeleton-line" />
      <div className="config-skeleton-line" />
      <div className="config-skeleton-line config-skeleton-line-short" />
    </div>
  );
}
