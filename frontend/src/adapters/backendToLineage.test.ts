import { describe, expect, it } from "vitest";

import type { GraphResponse, LineageEdge } from "../types/backend";
import { graphResponseToLineageData } from "./backendToLineage";

function baseNode(id: string, over: Partial<GraphResponse["nodes"][number]> = {}) {
  return {
    id,
    label: id,
    description: null,
    description_label: null,
    description_source: null,
    description_is_stale: false,
    columns: [],
    ...over,
  };
}

describe("graphResponseToLineageData — column_schemas", () => {
  it("maps declared type + PK/FK/nullable onto ColumnDef, replacing the 'unknown' default", () => {
    const graph: GraphResponse = {
      nodes: [
        baseNode("raw_patients", {
          column_schemas: [
            {
              name: "patient_id",
              data_type: "INTEGER",
              is_nullable: false,
              is_primary_key: true,
              is_foreign_key: false,
              references_table: null,
              references_column: null,
              origin: "declared",
            },
            {
              name: "primary_doctor_id",
              data_type: "INTEGER",
              is_nullable: true,
              is_primary_key: false,
              is_foreign_key: true,
              references_table: "raw_doctors",
              references_column: "doctor_id",
              origin: "declared",
            },
          ],
        }),
      ],
      edges: [
        { edge_id: "e1", source_table: "raw_patients", source_column: "patient_id", target_table: "stg_patients", target_column: "patient_id", transform_type: "direct", confidence: 1, source_type: "parser", dependency_kind: "output", evidence: null },
      ],
    } as unknown as GraphResponse;

    const { nodes } = graphResponseToLineageData(graph);
    const raw = nodes.find((n) => n.id === "raw_patients")!;
    const pid = raw.columns.find((c) => c.name === "patient_id")!;
    expect(pid.type).toBe("INTEGER");
    expect(pid.isPrimaryKey).toBe(true);
    expect(pid.isNullable).toBe(false);
    expect(pid.schemaOrigin).toBe("declared");

    const fk = raw.columns.find((c) => c.name === "primary_doctor_id")!;
    expect(fk.isForeignKey).toBe(true);
    expect(fk.referencesTable).toBe("raw_doctors");
  });

  it("keeps 'unknown' when a column has neither edge info nor schema, and flags propagated origin", () => {
    const graph: GraphResponse = {
      nodes: [
        baseNode("stg_x", {
          column_schemas: [
            { name: "a", data_type: "TEXT", is_nullable: true, is_primary_key: false, is_foreign_key: false, references_table: null, references_column: null, origin: "propagated" },
          ],
        }),
      ],
      edges: [
        { edge_id: "e1", source_table: "raw_x", source_column: "a", target_table: "stg_x", target_column: "a", transform_type: "direct", confidence: 1, source_type: "parser", dependency_kind: "output", evidence: null },
        { edge_id: "e2", source_table: "stg_x", source_column: "b", target_table: "mart_x", target_column: "b", transform_type: "aggregation", confidence: 1, source_type: "parser", dependency_kind: "output", evidence: null },
      ],
    } as unknown as GraphResponse;

    const { nodes } = graphResponseToLineageData(graph);
    const stg = nodes.find((n) => n.id === "stg_x")!;
    expect(stg.columns.find((c) => c.name === "a")!.type).toBe("TEXT");
    expect(stg.columns.find((c) => c.name === "a")!.schemaOrigin).toBe("propagated");
    // column "b" only appears via an outgoing edge — no schema → stays "unknown"
    expect(stg.columns.find((c) => c.name === "b")!.type).toBe("unknown");
  });

  it("does not throw when column_schemas is absent (older backend)", () => {
    const graph = { nodes: [baseNode("t")], edges: [] } as unknown as GraphResponse;
    expect(() => graphResponseToLineageData(graph)).not.toThrow();
  });
});

const edge = (source_table: string, target_table: string): LineageEdge => ({
  edge_id: `${source_table}-${target_table}`,
  source_table,
  source_column: null,
  target_table,
  target_column: null,
  dependency_kind: "output",
  transform_type: "direct",
  confidence: 1,
  source_type: "parser",
  evidence: null,
});

const layerGraph = (ids: string[], edges: LineageEdge[]): GraphResponse => ({
  nodes: ids.map((id) => ({
    id, label: id, description: null, description_label: null, description_source: null,
    description_is_stale: false, columns: [],
  })),
  edges,
});

const layers = (input: GraphResponse) => Object.fromEntries(
  graphResponseToLineageData(input).nodes.map((node) => [node.id, node.layer]),
);

describe("graphResponseToLineageData layer inference", () => {
  it("classifies a four-layer chain from topology", () => {
    expect(layers(layerGraph(
      ["raw_orders", "stg_orders", "int_join", "mart_revenue"],
      [edge("raw_orders", "stg_orders"), edge("stg_orders", "int_join"), edge("int_join", "mart_revenue")],
    ))).toMatchObject({ raw_orders: "source", stg_orders: "staging", int_join: "intermediate", mart_revenue: "marts" });
  });

  it("labels isolated nodes unknown regardless of their names", () => {
    expect(layers(layerGraph(["raw_lonely", "stg_lonely"], []))).toMatchObject({ raw_lonely: "unknown", stg_lonely: "unknown" });
  });

  it("does not treat raw_ as source when topology says otherwise", () => {
    expect(layers(layerGraph(["source", "raw_x", "consumer"], [edge("source", "raw_x"), edge("raw_x", "consumer")]))["raw_x"]).toBe("staging");
  });

  it("classifies an unprefixed topology intermediate correctly", () => {
    expect(layers(layerGraph(
      ["raw_a", "stg_a", "doctor_workload", "mart_x"],
      [edge("raw_a", "stg_a"), edge("stg_a", "doctor_workload"), edge("doctor_workload", "mart_x")],
    ))["doctor_workload"]).toBe("intermediate");
  });

  it("has no staging default and uses stg_ only for a source-fed leaf", () => {
    expect(layers(layerGraph(["raw_a", "intermediate_a", "leaf"], [edge("raw_a", "intermediate_a"), edge("intermediate_a", "leaf")]))["leaf"]).toBe("marts");
    expect(layers(layerGraph(["raw_a", "stg_leaf"], [edge("raw_a", "stg_leaf")]))["stg_leaf"]).toBe("staging");
    expect(layers(layerGraph(["raw_a", "stg.leaf"], [edge("raw_a", "stg.leaf")]))["stg.leaf"]).toBe("staging");
    expect(layers(layerGraph(["raw_a", "leaf"], [edge("raw_a", "leaf")]))["leaf"]).toBe("marts");
  });
});
