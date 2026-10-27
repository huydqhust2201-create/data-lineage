import { LineageNodeData, LineageEdgeData, ImpactAnalysisResult } from '../types/lineage';
import type { ImpactQueryResult } from '../types/backend';

/**
 * Calculates Upstream (Sources) and Downstream (Blast Radius) dependencies for any node.
 */
export function computeImpactAnalysis(
  targetNodeId: string,
  operation: ImpactAnalysisResult['operation'] = 'modify_schema',
  impactedColumn: string | undefined,
  nodes: LineageNodeData[],
  edges: LineageEdgeData[]
): ImpactAnalysisResult {
  const nodeMap = new Map<string, LineageNodeData>(nodes.map(n => [n.id, n]));
  const targetNode = nodeMap.get(targetNodeId);
  const targetNodeName = targetNode ? targetNode.name : targetNodeId;

  // Active edges only for dependency flow
  const activeEdges = edges.filter(e => e.status === 'active');

  // Adjacency maps
  const downstreamMap = new Map<string, string[]>();
  const upstreamMap = new Map<string, string[]>();

  activeEdges.forEach(edge => {
    if (!downstreamMap.has(edge.source)) downstreamMap.set(edge.source, []);
    downstreamMap.get(edge.source)!.push(edge.target);

    if (!upstreamMap.has(edge.target)) upstreamMap.set(edge.target, []);
    upstreamMap.get(edge.target)!.push(edge.source);
  });

  // 1. Upstream Traversal (BFS)
  const upstreamNodes: ImpactAnalysisResult['upstreamNodes'] = [];
  const visitedUpstream = new Set<string>([targetNodeId]);
  const queueUpstream: { id: string; depth: number; path: string[] }[] = [{ id: targetNodeId, depth: 0, path: [targetNodeName] }];

  while (queueUpstream.length > 0) {
    const current = queueUpstream.shift()!;
    const parents = upstreamMap.get(current.id) || [];

    for (const parentId of parents) {
      if (!visitedUpstream.has(parentId)) {
        visitedUpstream.add(parentId);
        const parentNode = nodeMap.get(parentId);
        if (parentNode) {
          const newPath = [parentNode.name, ...current.path];
          upstreamNodes.push({
            node: parentNode,
            depth: current.depth + 1,
            path: newPath
          });
          queueUpstream.push({ id: parentId, depth: current.depth + 1, path: newPath });
        }
      }
    }
  }

  // 2. Downstream Traversal (BFS)
  const downstreamNodes: ImpactAnalysisResult['downstreamNodes'] = [];
  const visitedDownstream = new Set<string>([targetNodeId]);
  const queueDownstream: { id: string; depth: number; path: string[] }[] = [{ id: targetNodeId, depth: 0, path: [targetNodeName] }];

  const criticalDashboards: string[] = [];
  const mlFeaturesAffected: string[] = [];

  while (queueDownstream.length > 0) {
    const current = queueDownstream.shift()!;
    const children = downstreamMap.get(current.id) || [];

    for (const childId of children) {
      if (!visitedDownstream.has(childId)) {
        visitedDownstream.add(childId);
        const childNode = nodeMap.get(childId);
        if (childNode) {
          const newPath = [...current.path, childNode.name];

          // Determine risk level based on layer and depth
          let riskLevel: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' = 'MEDIUM';
          let impactReason = `Downstream dependency at depth ${current.depth + 1}.`;

          if (childNode.layer === 'bi_dashboard') {
            riskLevel = 'CRITICAL';
            impactReason = 'Critical BI Dashboard directly broken for executive stakeholders and daily KPI reporting.';
            criticalDashboards.push(childNode.name);
          } else if (childNode.layer === 'feature_store') {
            riskLevel = 'CRITICAL';
            impactReason = 'Production Machine Learning inference features will receive nulls or schema mismatch error.';
            mlFeaturesAffected.push(childNode.name);
          } else if (childNode.layer === 'reverse_etl') {
            riskLevel = 'HIGH';
            impactReason = 'Reverse ETL sync to CRM/Customer tooling will fail.';
          } else if (childNode.layer === 'marts') {
            riskLevel = current.depth <= 1 ? 'HIGH' : 'MEDIUM';
            impactReason = 'Gold analytic fact/dimension table requires full refresh and testing.';
          } else {
            riskLevel = 'LOW';
          }

          // Check if column mapping matches
          let affectedColumns: string[] = [];
          if (impactedColumn) {
            affectedColumns = childNode.columns.filter(c => 
              c.name.toLowerCase().includes(impactedColumn.toLowerCase()) || 
              impactedColumn.toLowerCase().includes(c.name.toLowerCase())
            ).map(c => c.name);
            if (affectedColumns.length > 0) {
              impactReason += ` Matched downstream column(s): [${affectedColumns.join(', ')}].`;
            }
          }

          downstreamNodes.push({
            node: childNode,
            depth: current.depth + 1,
            path: newPath,
            riskLevel,
            impactReason,
            affectedColumns: affectedColumns.length > 0 ? affectedColumns : undefined
          });

          queueDownstream.push({ id: childId, depth: current.depth + 1, path: newPath });
        }
      }
    }
  }

  // Calculate composite risk score
  let riskScore = 0;
  if (downstreamNodes.length === 0) {
    riskScore = 5;
  } else {
    const criticalCount = downstreamNodes.filter(n => n.riskLevel === 'CRITICAL').length;
    const highCount = downstreamNodes.filter(n => n.riskLevel === 'HIGH').length;
    const medCount = downstreamNodes.filter(n => n.riskLevel === 'MEDIUM').length;
    
    riskScore = Math.min(100, Math.round(
      criticalCount * 30 +
      highCount * 18 +
      medCount * 8 +
      downstreamNodes.length * 4
    ));
  }

  // Mitigation advice — lời khuyên chung theo operation, không gắn theo
  // criticalDashboards/mlFeaturesAffected (luôn rỗng với dữ liệu thật vì
  // inferLayer() không bao giờ suy ra layer bi_dashboard/feature_store từ
  // tên bảng dbt thật, xem adapters/backendToLineage.ts).
  const mitigationAdvice: string[] = [];
  if (operation === 'drop_column' || operation === 'rename_column') {
    mitigationAdvice.push(`🔄 Use dbt deprecation period: Keep '${impactedColumn || 'column'}' as a generated/aliased column in staging before dropping in next sprint.`);
  }
  if (operation === 'add_column') {
    mitigationAdvice.push(`👀 Check downstream models for \`SELECT *\` on '${targetNodeName}' — a strict-schema consumer (BI tool, materialized view) may break silently when the new column arrives.`);
  }
  if (operation === 'change_constraint') {
    mitigationAdvice.push(`🔍 Backfill or clean up existing rows before adding NOT NULL — a constraint change fails immediately if current data already violates it.`);
  }
  mitigationAdvice.push(`🧪 Run \`dbt build --select +${targetNodeName}+\` in a staging pull-request schema to simulate dry-run validation.`);

  return {
    targetNodeId,
    targetNodeName,
    operation,
    impactedColumn,
    upstreamNodes,
    downstreamNodes,
    totalImpactedCount: downstreamNodes.length,
    criticalDashboards,
    mlFeaturesAffected,
    riskScore,
    mitigationAdvice
  };
}

/**
 * Export helpers
 */
export function exportLineageToCSV(nodes: LineageNodeData[], edges: LineageEdgeData[]) {
  const rows = [
    ['Edge ID', 'Source Table', 'Source Layer', 'Target Table', 'Target Layer', 'Confidence Score', 'Inferred By', 'Status', 'Reasoning']
  ];

  const nodeMap = new Map(nodes.map(n => [n.id, n]));

  edges.forEach(e => {
    const src = nodeMap.get(e.source);
    const tgt = nodeMap.get(e.target);
    rows.push([
      e.id,
      src ? `${src.schema}.${src.name}` : e.source,
      src?.layer || 'unknown',
      tgt ? `${tgt.schema}.${tgt.name}` : e.target,
      tgt?.layer || 'unknown',
      e.confidence.toFixed(2),
      e.inferredBy,
      e.status,
      `"${(e.reasoning || '').replace(/"/g, '""')}"`
    ]);
  });

  const csvContent = 'data:text/csv;charset=utf-8,' + rows.map(r => r.join(',')).join('\n');
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `lineage_ai_graph_${Date.now()}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export function exportLineageToJSON(nodes: LineageNodeData[], edges: LineageEdgeData[], hitlQueue: any[]) {
  const payload = {
    exportedAt: new Date().toISOString(),
    project: 'DATA-04 Lineage AI (Baby Sharks - P-116)',
    summary: {
      totalNodes: nodes.length,
      totalEdges: edges.length,
      activeEdges: edges.filter(e => e.status === 'active').length,
      hitlPending: hitlQueue.filter(h => h.status === 'pending').length
    },
    nodes,
    edges,
    hitlQueue
  };

  const jsonStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(payload, null, 2));
  const link = document.createElement('a');
  link.setAttribute('href', jsonStr);
  link.setAttribute('download', `lineage_ai_export_${Date.now()}.json`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export function exportCatalogToCSV(nodes: LineageNodeData[]) {
  const rows = [
    ['Schema', 'Table Name', 'Layer', 'Column Name', 'Data Type', 'Primary Key', 'Quality Score', 'Freshness', 'Owner', 'Description']
  ];

  nodes.forEach(node => {
    if (node.columns.length === 0) {
      rows.push([
        node.schema,
        node.name,
        node.layer,
        'N/A',
        'N/A',
        'No',
        `${node.qualityScore || 99}%`,
        node.freshness || 'Daily',
        node.owner,
        `"${(node.description || '').replace(/"/g, '""')}"`
      ]);
    } else {
      node.columns.forEach(col => {
        rows.push([
          node.schema,
          node.name,
          node.layer,
          col.name,
          col.type,
          col.isPrimaryKey ? 'YES' : 'NO',
          `${node.qualityScore || 99}%`,
          node.freshness || 'Daily',
          node.owner,
          `"${(col.description || node.description || '').replace(/"/g, '""')}"`
        ]);
      });
    }
  });

  const csvContent = 'data:text/csv;charset=utf-8,' + rows.map(r => r.join(',')).join('\n');
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `data_catalog_dictionary_${Date.now()}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export function generateTableDDL(node: LineageNodeData): string {
  const columnDefs = node.columns.map(c => {
    let def = `  ${c.name.padEnd(28)} ${c.type}`;
    if (c.isPrimaryKey) {
      def += ' PRIMARY KEY';
    }
    if (c.description) {
      def += ` COMMENT '${c.description.replace(/'/g, "''")}'`;
    }
    return def;
  });

  return `-- Table: ${node.schema}.${node.name} (${node.layer})\n-- Owner: ${node.owner} | Quality: ${node.qualityScore || 99}%\n-- Description: ${node.description || 'N/A'}\nCREATE TABLE IF NOT EXISTS ${node.schema}.${node.name} (\n${columnDefs.join(',\n')}\n);\n`;
}

export function exportDatabaseToSQL(nodes: LineageNodeData[], targetNode?: LineageNodeData) {
  const targetNodes = targetNode ? [targetNode] : nodes;
  const header = `-- ========================================================\n-- DATA-04 LINEAGE AI - DATABASE DDL EXPORT SCRIPT\n-- Exported At: ${new Date().toISOString()}\n-- Total Tables: ${targetNodes.length}\n-- ========================================================\n\n`;
  
  const ddlStatements = targetNodes.map(node => generateTableDDL(node)).join('\n');
  const fullSql = header + ddlStatements;

  const encodedUri = 'data:text/sql;charset=utf-8,' + encodeURIComponent(fullSql);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  const filename = targetNode ? `ddl_${targetNode.name}_${Date.now()}.sql` : `database_full_schema_${Date.now()}.sql`;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// Xuất CSV từ dữ liệu THẬT trả về bởi GET /impact/{table} (ImpactQueryResult) —
// không còn Risk Level/Impact Reason/Dependency Path bịa, chỉ các cột phản ánh
// đúng những gì backend biết: hop, hitl_status, source_type, confidence, risk
// text (rule-based, chỉ có khi meta.operation map được change_kind), evidence.
export function exportImpactReportToCSV(
  impact: ImpactQueryResult,
  meta: { targetNodeName: string; operation: string; impactedColumn?: string },
) {
  const all = [
    ...impact.confirmed.map(e => ({ ...e, hitl_status: e.hitl_status ?? ('confirmed' as const) })),
    ...impact.inferred_pending.map(e => ({ ...e, hitl_status: e.hitl_status ?? ('pending' as const) })),
  ];

  const rows = [
    ['Impact Analysis Report - DATA-04 Lineage AI'],
    ['Target Node', meta.targetNodeName],
    ['Operation', meta.operation],
    ['Impacted Column', meta.impactedColumn || 'N/A'],
    ['Confirmed Edges', `${impact.confirmed.length}`],
    ['Pending (chờ duyệt) Edges', `${impact.inferred_pending.length}`],
    [],
    ['--- Downstream Impacted Edges (thật, GET /impact) ---'],
    ['Target Table', 'Target Column', 'Hop', 'HITL Status', 'Source Type', 'Confidence', 'Risk Note', 'Evidence File']
  ];

  all.forEach(e => {
    rows.push([
      e.target.table,
      e.target.column || 'N/A',
      `${e.hops ?? 1}`,
      e.hitl_status,
      e.source_type,
      e.confidence.toFixed(2),
      `"${(e.risk || 'N/A').replace(/"/g, '""')}"`,
      `"${(e.evidence?.file_path || 'N/A').replace(/"/g, '""')}"`
    ]);
  });

  const csvContent = 'data:text/csv;charset=utf-8,' + rows.map(r => r.join(',')).join('\n');
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `impact_report_${meta.targetNodeName}_${Date.now()}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
