export type SseEvent = { event: string; data: unknown };

export function feedSse(buffer: string, text: string): { events: SseEvent[]; rest: string } {
  let remaining = buffer + text;
  const events: SseEvent[] = [];
  let boundary: RegExpMatchArray | null;
  while ((boundary = remaining.match(/\r?\n\r?\n/)) !== null) {
    const frame = remaining.slice(0, boundary.index);
    remaining = remaining.slice((boundary.index ?? 0) + boundary[0].length);
    const data = frame.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart());
    if (data.length === 0) continue;
    const event = frame.split(/\r?\n/).find((line) => line.startsWith("event:"))?.slice(6).trim() ?? "message";
    try { events.push({ event, data: JSON.parse(data.join("\n")) }); } catch { /* ignore malformed frames */ }
  }
  return { events, rest: remaining };
}
