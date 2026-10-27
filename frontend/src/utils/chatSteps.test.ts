import { describe, expect, it } from "vitest";
import { stepLabel } from "./chatSteps";

describe("stepLabel", () => {
  it("labels traversal and errors", () => {
    expect(stepLabel({ tool: "traverse", args: { table: "orders", direction: "upstream", column: "id" }, summary: "", resolved: null, error: null })).toContain("orders.id");
    expect(stepLabel({ tool: "traverse", args: { table: "orders", direction: "upstream" }, summary: "", resolved: null, error: null })).toContain("orders");
    expect(stepLabel({ tool: "other", args: {}, summary: "", resolved: null, error: null })).toContain("Chạy other");
    expect(stepLabel({ tool: "other", args: {}, summary: "", resolved: null, error: "failed" })).toContain("failed");
  });

  it("includes deterministic results from the tool summary", () => {
    expect(stepLabel({ tool: "breaking_changes", args: { table: "orders" }, summary: "0 confirmed, 0 pending", resolved: null, error: null })).toContain("không có cảnh báo nào");
    expect(stepLabel({ tool: "traverse", args: { table: "orders", direction: "upstream" }, summary: "3 confirmed, 0 pending", resolved: null, error: null })).toContain("3 quan hệ đã xác nhận");
    expect(stepLabel({ tool: "traverse", args: { table: "orders", direction: "upstream" }, summary: "2 confirmed, 1 pending", resolved: null, error: null })).toContain("1 chưa duyệt");
  });
});
