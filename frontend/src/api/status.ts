import { request } from "./http";
import type { StatusResponse } from "../types/backend";

/** GET /api/v1/status — chỉ render đúng field BE trả về, không tự bịa thêm thành phần. */
export function getStatus(): Promise<StatusResponse> {
  return request<StatusResponse>("/status");
}
