import { describe, expect, it } from "vitest";

import { computeDepths } from "./computeDepths";

describe("computeDepths", () => {
  it("assigns depths along a straight chain", () => {
    expect(computeDepths(["A", "B", "C"], [{ source: "A", target: "B" }, { source: "B", target: "C" }])).toEqual({
      A: 0,
      B: 1,
      C: 2,
    });
  });

  it("places multiple roots before their shared target", () => {
    expect(
      computeDepths(
        ["employee", "customer", "track", "invoice_line", "sales_by_album_agent"],
        [
          { source: "employee", target: "sales_by_album_agent" },
          { source: "customer", target: "sales_by_album_agent" },
          { source: "track", target: "sales_by_album_agent" },
          { source: "invoice_line", target: "sales_by_album_agent" },
        ],
      ),
    ).toEqual({
      employee: 0,
      customer: 0,
      track: 0,
      invoice_line: 0,
      sales_by_album_agent: 1,
    });
  });

  it("uses the longest path when a shortcut exists", () => {
    const depths = computeDepths(
      ["A", "B", "C"],
      [
        { source: "A", target: "B" },
        { source: "A", target: "C" },
        { source: "B", target: "C" },
      ],
    );

    expect(depths.C).toBe(2);
  });

  it("keeps isolated nodes at depth zero", () => {
    expect(computeDepths(["isolated"], [])).toEqual({ isolated: 0 });
  });

  it("ignores edges whose endpoint is not a known node", () => {
    expect(computeDepths(["A", "B"], [{ source: "A", target: "B" }, { source: "X", target: "Y" }])).toEqual({
      A: 0,
      B: 1,
    });
  });

  it("bounds depths when the graph contains a cycle", () => {
    const nodeIds = ["A", "B"];
    const depths = computeDepths(nodeIds, [
      { source: "A", target: "B" },
      { source: "B", target: "A" },
    ]);

    expect(depths.A).toBeLessThanOrEqual(nodeIds.length - 1);
    expect(depths.B).toBeLessThanOrEqual(nodeIds.length - 1);
  });

  it("models the measured jaffle-shop longest path", () => {
    const depths = computeDepths(
      ["ecom.raw_orders", "stg_orders", "orders", "customers", "ecom.raw_customers", "stg_customers"],
      [
        { source: "ecom.raw_orders", target: "stg_orders" },
        { source: "stg_orders", target: "orders" },
        { source: "orders", target: "customers" },
        { source: "ecom.raw_customers", target: "stg_customers" },
        { source: "stg_customers", target: "customers" },
      ],
    );

    expect(depths).toMatchObject({
      "ecom.raw_orders": 0,
      stg_orders: 1,
      orders: 2,
      customers: 3,
      "ecom.raw_customers": 0,
      stg_customers: 1,
    });
  });
});
