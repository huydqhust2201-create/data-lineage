import { describe, expect, it } from "vitest";

import { linkifyEntities } from "./linkifyEntities";

const entities = [
  { name: "revenue_alerts", nodeId: "short" },
  { name: "revenue_alerts_final", nodeId: "long" },
  { name: "amount_paid", nodeId: "invoice" },
];

describe("linkifyEntities", () => {
  it("matches full identifiers, longest names first, including backticks", () => {
    expect(linkifyEntities("`revenue_alerts_final` uses amount_paid", entities)).toEqual([
      "`",
      { label: "revenue_alerts_final", nodeId: "long" },
      "` uses ",
      { label: "amount_paid", nodeId: "invoice" },
    ]);
  });

  it("does not match inside a longer identifier", () => {
    expect(linkifyEntities("revenue_alerts_finalized", entities)).toEqual(["revenue_alerts_finalized"]);
  });

  it("keeps ordinary text and handles empty text", () => {
    expect(linkifyEntities("nothing to link", entities)).toEqual(["nothing to link"]);
    expect(linkifyEntities("", entities)).toEqual([]);
  });
});
