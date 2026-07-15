interface DashboardColumnProps {
  title: string;
  children: React.ReactNode;
}

export function DashboardColumn({ title, children }: DashboardColumnProps) {
  return (
    <section className="flex flex-col rounded-md border border-terminal-border bg-terminal-panel/60 p-3 backdrop-blur-sm">
      <h2 className="mb-3 border-b border-terminal-border pb-2 text-sm font-bold uppercase tracking-widest text-terminal-in text-glow-in">
        {title}
      </h2>
      <div className="flex-1">{children}</div>
    </section>
  );
}
