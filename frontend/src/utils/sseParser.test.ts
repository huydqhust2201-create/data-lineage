import { describe, expect, it } from "vitest";
import { feedSse } from "./sseParser";

describe("feedSse", () => {
  it("keeps fragments, parses multiple frames, and joins data lines", () => {
    const first = feedSse("", 'event: token\ndata: {"text":"lấy');
    expect(first.events).toEqual([]);
    const second = feedSse(first.rest, ' dữ liệu"}\n\nevent: done\ndata: {"a":\ndata: 1}\n\n');
    expect(second.events).toEqual([{ event: "token", data: { text: "lấy dữ liệu" } }, { event: "done", data: { a: 1 } }]);
  });

  it("preserves Vietnamese split in the middle of UTF-8", () => {
    const bytes = new TextEncoder().encode('event: token\ndata: {"text":"lấy dữ liệu từ đâu"}\n\n');
    const decoder = new TextDecoder();
    const text = decoder.decode(bytes.slice(0, 30), { stream: true }) + decoder.decode(bytes.slice(30), { stream: true });
    expect(feedSse("", text).events).toEqual([{ event: "token", data: { text: "lấy dữ liệu từ đâu" } }]);
    expect(text).not.toContain("�");
  });
});
