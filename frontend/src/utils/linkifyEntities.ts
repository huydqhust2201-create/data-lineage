export type Entity = { name: string; nodeId: string };
export type Chunk = string | { label: string; nodeId: string };

const identifierBoundary = "A-Za-z0-9_.";

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function linkifyEntities(text: string, entities: Entity[]): Chunk[] {
  if (!text) return [];

  const uniqueEntities = Array.from(
    new Map(
      entities
        .filter((entity) => entity.name)
        .sort((left, right) => right.name.length - left.name.length)
        .map((entity) => [entity.name.toLowerCase(), entity]),
    ).values(),
  );
  if (uniqueEntities.length === 0) return [text];

  const lookup = new Map(uniqueEntities.map((entity) => [entity.name.toLowerCase(), entity]));
  const pattern = uniqueEntities.map((entity) => escapeRegex(entity.name)).join("|");
  const matcher = new RegExp(`(?<![${identifierBoundary}])(${pattern})(?![${identifierBoundary}])`, "gi");
  const chunks: Chunk[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = matcher.exec(text)) !== null) {
    if (match.index > cursor) chunks.push(text.slice(cursor, match.index));
    const entity = lookup.get(match[0].toLowerCase());
    if (entity) chunks.push({ label: match[0], nodeId: entity.nodeId });
    cursor = matcher.lastIndex;
  }

  if (cursor === 0) return [text];
  if (cursor < text.length) chunks.push(text.slice(cursor));
  return chunks;
}
