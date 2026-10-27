export interface Workspace {
  id: string;
  name: string;
  description: string;
  tableCount: number;
  columnCount: number;
  edgeCount: number;
  pendingCount: number;
  createdAt: string;
}
