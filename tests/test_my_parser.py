import os
from pathlib import Path

from src.services.parser_service import SQLParserService

# Khởi tạo Service
parser = SQLParserService(default_dialect="postgres")

sql_dir = Path("tests/ground_truth/sql")
parsed_edges = []
unparsed_files = []

# Duyệt từng file để phân loại chính xác PASS / FAIL
for file_name in sorted(os.listdir(sql_dir)):
    if file_name.endswith(".sql"):
        file_path = sql_dir / file_name
        edges = parser.parse_file(str(file_path))

        if len(edges) > 0:
            parsed_edges.extend(edges)
        else:
            # File trả về [] chính là file Parser FAIL (cần chuyển tiếp cho LLM)
            unparsed_files.append(file_name)

print("=== CÁC CẠNH PARSE THÀNH CÔNG ===")
for e in parsed_edges:
    print(e)

print(f"\nTotal Edges: {len(parsed_edges)}")

print("\n=== DANH SÁCH FILE PARSER FAIL (SẼ CHUYỂN SANG LLM) ===")
for f in unparsed_files:
    print(" ⚠️ ", f)
