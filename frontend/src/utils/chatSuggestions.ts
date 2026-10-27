export function buildSuggestions(realTables: string[]): string[] {
  const sorted = [...realTables].sort((left, right) => left.localeCompare(right));
  const nonRaw = sorted.filter((table) => !table.startsWith("raw_"));
  const tables = nonRaw.length > 0 ? nonRaw : sorted;

  return tables.slice(0, 3).map((table, index) => {
    if (index === 0) return `${table} lấy dữ liệu từ đâu?`;
    if (index === 1) return `Nếu sửa ${table} thì vỡ gì?`;
    return `${table} bị lỗi, tại sao?`;
  });
}
