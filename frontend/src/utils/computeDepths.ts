export interface DepthEdge {
  source: string;
  target: string;
}

/**
 * Computes each node's longest-path depth from a root node.
 *
 * Invalid edges are ignored. Cycles are bounded at the largest possible DAG
 * depth so layout remains finite even when the backend returns cyclic data.
 */
export function computeDepths(nodeIds: string[], edges: DepthEdge[]): Record<string, number> {
  const depth: Record<string, number> = {};
  for (const id of nodeIds) depth[id] = 0;

  const known = new Set(nodeIds);
  const usable = edges.filter((edge) => known.has(edge.source) && known.has(edge.target));
  const maxDepth = Math.max(0, nodeIds.length - 1);

  for (let iteration = 0; iteration < nodeIds.length; iteration += 1) {
    let changed = false;

    for (const edge of usable) {
      const candidate = Math.min(depth[edge.source] + 1, maxDepth);
      if (candidate > depth[edge.target]) {
        depth[edge.target] = candidate;
        changed = true;
      }
    }

    if (!changed) break;
  }

  return depth;
}
