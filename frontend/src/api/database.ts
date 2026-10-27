import { request } from "./http";

export interface Database {
  id: number;
  owner_id: number;
  name: string;
  created_at: string;
  role: "engineer" | "viewer";
}

export function listDatabases(): Promise<Database[]> {
  return request<Database[]>("/databases");
}

export function createDatabase(name: string): Promise<Database> {
  return request<Database>("/databases", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}
