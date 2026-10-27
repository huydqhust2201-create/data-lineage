import { describe, expect, it } from "vitest";

import type { LineageNodeData } from "../types/lineage";

import { buildEntities } from "./chatEntities";

const node = (id: string, columns: string[]): LineageNodeData => ({
  id,
  name: id,
  schema: "public",
  layer: "staging",
  type: "table",
  description: "",
  columns: columns.map((name) => ({ name, type: "unknown" })),
  owner: "—",
  tags: [],
});

describe("buildEntities", () => {
  it("returns no entities before the graph loads", () => {
    expect(buildEntities([])).toEqual([]);
  });

  it("keeps every table and only columns unique across the graph", () => {
    expect(buildEntities([node("orders", ["id", "total"]), node("payments", ["id", "amount"])])).toEqual([
      { name: "orders", nodeId: "orders" },
      { name: "payments", nodeId: "payments" },
      { name: "total", nodeId: "orders" },
      { name: "amount", nodeId: "payments" },
    ]);
  });
});
