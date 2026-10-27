import type { LineageNodeData } from "../types/lineage";

import type { Entity } from "./linkifyEntities";

export function buildEntities(realNodes: LineageNodeData[]): Entity[] {
  const columnCounts = new Map<string, number>();
  for (const node of realNodes) {
    for (const column of node.columns) {
      columnCounts.set(column.name, (columnCounts.get(column.name) ?? 0) + 1);
    }
  }

  const entities: Entity[] = realNodes.map((node) => ({ name: node.id, nodeId: node.id }));
  for (const node of realNodes) {
    for (const column of node.columns) {
      if (columnCounts.get(column.name) === 1) {
        entities.push({ name: column.name, nodeId: node.id });
      }
    }
  }
  return entities;
}
