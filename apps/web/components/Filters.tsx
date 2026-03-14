"use client";

type FiltersProps = {
  filterLabels: Set<string>;
  setFilterLabels: (s: Set<string>) => void;
  colorBy: "label" | "community";
  setColorBy: (c: "label" | "community") => void;
  nodeLabels: string[];
};

export function Filters({
  filterLabels,
  setFilterLabels,
  colorBy,
  setColorBy,
  nodeLabels,
}: FiltersProps) {
  const toggleLabel = (label: string) => {
    const next = new Set(filterLabels);
    if (next.has(label)) next.delete(label);
    else next.add(label);
    setFilterLabels(next);
  };

  return (
    <section style={{ marginBottom: "1rem" }}>
      <h2 style={{ fontSize: "0.875rem", fontWeight: 600, margin: "0 0 0.5rem 0", color: "#a0a0a0" }}>
        Filters
      </h2>
      <p style={{ fontSize: "0.75rem", color: "#888", marginBottom: "0.5rem" }}>
        Node type (hide)
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
        {nodeLabels.length === 0 ? (
          <span style={{ fontSize: "0.75rem", color: "#666" }}>Load a graph first</span>
        ) : (
          nodeLabels.map((label) => (
            <label key={label} style={{ display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.8rem" }}>
              <input
                type="checkbox"
                checked={filterLabels.has(label)}
                onChange={() => toggleLabel(label)}
              />
              {label}
            </label>
          ))
        )}
      </div>
      <p style={{ fontSize: "0.75rem", color: "#888", margin: "0.5rem 0 0.25rem 0" }}>
        Color by
      </p>
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <label style={{ display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.8rem" }}>
          <input
            type="radio"
            name="colorBy"
            checked={colorBy === "label"}
            onChange={() => setColorBy("label")}
          />
          Label
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.8rem" }}>
          <input
            type="radio"
            name="colorBy"
            checked={colorBy === "community"}
            onChange={() => setColorBy("community")}
          />
          Community
        </label>
      </div>
    </section>
  );
}
