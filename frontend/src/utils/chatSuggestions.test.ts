import { describe, expect, it } from "vitest";

import { buildSuggestions } from "./chatSuggestions";

describe("buildSuggestions", () => {
  it("returns no sendable suggestions until lineage is available", () => {
    expect(buildSuggestions([])).toEqual([]);
  });

  it("sorts tables and excludes raw_ tables when alternatives exist", () => {
    expect(buildSuggestions(["raw_orders", "mart_revenue", "stg_orders", "dim_customer"])).toEqual([
      "dim_customer lấy dữ liệu từ đâu?",
      "Nếu sửa mart_revenue thì vỡ gì?",
      "stg_orders bị lỗi, tại sao?",
    ]);
  });

  it("uses raw_ tables only when they are the only tables", () => {
    expect(buildSuggestions(["raw_z", "raw_a"])).toEqual([
      "raw_a lấy dữ liệu từ đâu?",
      "Nếu sửa raw_z thì vỡ gì?",
    ]);
  });

  it("returns one suggestion for one table independent of input order", () => {
    expect(buildSuggestions(["stg_orders"])).toEqual(["stg_orders lấy dữ liệu từ đâu?"]);
    expect(buildSuggestions(["stg_orders", "mart_revenue"])).toEqual(
      buildSuggestions(["mart_revenue", "stg_orders"]),
    );
  });
});
