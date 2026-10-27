import logging
import os
import re
from pathlib import Path

from sqlglot import exp
from sqlglot import parse as sqlglot_parse
from sqlglot.errors import SqlglotError

from src.models.schemas import ColumnSchema, GraphEvent, LineageEdge, LineageEvidence
from src.services.naming import qualified_table_name, should_drop_edge

logger = logging.getLogger(__name__)

# Giải thích ngắn theo transform_type — ghép cùng file_path/line_range để mọi
# cạnh parser cũng có "vì sao" hiển thị được, không chỉ cạnh LLM (trước đây
# reasoning=None cho toàn bộ cạnh parser).
_TRANSFORM_EXPLANATIONS: dict[str, str] = {
    "direct": "Ánh xạ cột trực tiếp, không qua hàm biến đổi",
    "conditional": "Giá trị phụ thuộc điều kiện (CASE WHEN / COALESCE / NULLIF), không truyền nguyên trạng",
    "aggregation": "Qua hàm tổng hợp hoặc window function",
    "join": "Kết hợp dữ liệu từ JOIN nhiều bảng",
    "unknown": "Không xác định rõ kiểu biến đổi",
}

# Bản dài hơn cho evidence.reasoning_detail — hiển thị khi user bấm "Chi tiết"
# trên drawer cạnh. Diễn giải CƠ CHẾ biến đổi theo từng transform_type, KHÔNG
# lặp lại SQL nguyên văn (drawer đã có mục "Raw SQL" riêng bên dưới rồi).
# Giải thích cho cạnh control lineage (dependency_kind != "output") — thay cho
# _TRANSFORM_EXPLANATIONS/_TRANSFORM_DETAIL (vốn nói về biến đổi cột output).
_DEPENDENCY_EXPLANATIONS: dict[str, str] = {
    "filter": "Cột dùng trong điều kiện lọc (WHERE/HAVING) — quyết định hàng nào của bảng đích xuất hiện",
    "join_key": "Cột dùng làm khoá JOIN (ON/USING) — quyết định hàng nào khớp giữa các bảng",
    "group_key": "Cột dùng trong GROUP BY — quyết định cách gom nhóm hàng",
    "window_partition": "Cột dùng trong PARTITION BY của window function — chia khung tính toán",
    "window_order": "Cột dùng trong ORDER BY của window function — quyết định thứ tự trong khung",
}
_DEPENDENCY_DETAIL: dict[str, str] = {
    "filter": (
        "Cột này KHÔNG chảy vào giá trị của cột output nào ở bảng đích, nhưng nằm trong mệnh đề "
        "WHERE/HAVING nên nó quyết định TẬP HÀNG của bảng đích. Xoá cột này làm model lỗi biên dịch; "
        "đổi kiểu/giá trị làm số hàng của bảng đích thay đổi mà không cột output nào báo động."
    ),
    "join_key": (
        "Cột này là khoá JOIN — không nhất thiết vào output, nhưng quyết định hàng nào của các bảng "
        "được ghép với nhau. Xoá/đổi tên làm phép JOIN vỡ; đổi kiểu làm join không còn khớp, mất/thừa hàng."
    ),
    "group_key": (
        "Cột này nằm trong GROUP BY — quyết định độ mịn của việc gom nhóm ở bảng đích. Xoá/đổi làm "
        "thay đổi số nhóm, tức thay đổi toàn bộ số liệu tổng hợp downstream."
    ),
    "window_partition": (
        "Cột này nằm trong PARTITION BY của window function — chia dữ liệu thành các khung tính toán. "
        "Đổi cột này làm kết quả window (ROW_NUMBER/RANK/SUM OVER...) tính lại theo khung khác."
    ),
    "window_order": (
        "Cột này nằm trong ORDER BY của window function — quyết định thứ tự các hàng trong mỗi khung. "
        "Đổi kiểu/giá trị làm đảo thứ tự → lệch kết quả ROW_NUMBER/LAG/LEAD và các bộ lọc downstream dựa vào đó."
    ),
}

_TRANSFORM_DETAIL: dict[str, str] = {
    "direct": (
        "Cột đích nhận dữ liệu truyền nguyên trạng từ cột nguồn — không đi qua hàm tổng hợp, "
        "phép JOIN hay biểu thức biến đổi nào. Đây là quan hệ phụ thuộc rõ ràng nhất: nếu cột "
        "nguồn đổi kiểu, đổi tên hoặc bị xoá thì cột đích ảnh hưởng trực tiếp."
    ),
    "conditional": (
        "Giá trị cột đích được suy ra từ một biểu thức điều kiện (CASE WHEN / COALESCE / NULLIF / IF) "
        "trên cột nguồn — KHÔNG phải truyền nguyên trạng. Nguy hiểm hơn 'direct' ở chỗ: đổi TẬP GIÁ "
        "TRỊ của cột nguồn (vd thêm 1 giá trị enum mới) có thể làm nhánh CASE rơi sai, kết quả cột "
        "đích sai lệch mà không có cột nào ở downstream báo động."
    ),
    "aggregation": (
        "Cột đích là kết quả của một hàm tổng hợp hoặc window function (SUM/COUNT/AVG/ROW_NUMBER…) "
        "tính trên cột nguồn. Giá trị đã bị biến đổi so với nguồn, nên thay đổi ở cột nguồn làm "
        "sai lệch số liệu tính ra chứ không chỉ đổi định dạng."
    ),
    "join": (
        "Cạnh này sinh ra từ một phép JOIN nhiều bảng — cột nguồn thường tham gia điều kiện join "
        "hoặc được chọn ra từ một trong các bảng được join. Thay đổi ở cột nguồn có thể làm phép "
        "join không còn khớp và mất/thừa hàng ở bảng đích."
    ),
    "unknown": (
        "sqlglot xác định được quan hệ phụ thuộc giữa hai cột nhưng không phân loại chắc chắn kiểu "
        "biến đổi. Nên xem lại câu SQL gốc bên dưới để rõ cơ chế."
    ),
}

_DBT_JINJA = re.compile(r"\{\{.*?\}\}", re.DOTALL)
_MACRO_BLOCK = re.compile(r"\{%-?\s*macro\b.*?endmacro\s*-?%\}", re.DOTALL | re.IGNORECASE)


def preprocess_dbt_jinja(sql_content: str) -> str:
    """Tiền xử lý các đoạn dbt Jinja cơ bản thành SQL thuần hợp lệ để sqlglot
    parse được. Hàm cấp module (không phụ thuộc self) — dùng chung cho cả
    SQLParserService lẫn sql_document_service (RAG trên nội dung SQL), 2 nơi
    khác nhau đều cần sqlglot parse được cùng 1 file dbt model."""
    # 1. Loại bỏ Jinja Comment: {# ... #}
    sql_clean = re.sub(r"\{#.*?#\}", "", sql_content, flags=re.DOTALL)

    # 2. Loại bỏ block dbt config: {{ config(...) }}
    sql_clean = re.sub(r"\{\{\s*config\s*\(.*?\)\s*\}\}", "", sql_clean, flags=re.DOTALL)

    # 3. Thay thế ref('model_name') -> model_name
    # Khớp cả dấu nháy đơn ' và nháy kép "
    sql_clean = re.sub(
        r'\{\{\s*ref\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)\s*\}\}', lambda match: f'"{match.group(1)}"', sql_clean
    )

    # 4. Thay thế source('schema', 'table') -> schema.table
    sql_clean = re.sub(
        r'\{\{\s*source\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)\s*\}\}',
        lambda match: f'"{match.group(1)}"."{match.group(2)}"',
        sql_clean,
    )

    # 5. Thay thế {{ this }} -> target_table (nếu có)
    sql_clean = re.sub(r"\{\{\s*this\s*\}\}", "this_table", sql_clean)

    # 6. Loại bỏ Jinja block dbt snapshot: {% snapshot NAME %} ... {% endsnapshot %}
    # Giữ nguyên SQL bên trong (select xác định cột theo dõi) — tên snapshot
    # theo quy ước dbt luôn trùng tên file, nên vẫn dùng target_table_fallback
    # (path.stem) bình thường như model .sql khác, không cần trích riêng NAME.
    sql_clean = re.sub(r"\{%-?\s*snapshot\s+\w+\s*-?%\}", "", sql_clean)
    sql_clean = re.sub(r"\{%-?\s*endsnapshot\s*-?%\}", "", sql_clean)

    return sql_clean


class SQLParserService:
    """
    SQL Parser Service sử dụng `sqlglot` để trích xuất Column-Level Data Lineage.
    """

    def __init__(self, default_dialect: str = "postgres"):
        """
        Khởi tạo parser service với dialect mặc định.
        :param default_dialect: SQL dialect (postgres, snowflake, bigquery, duckdb, v.v.)
        """
        self.default_dialect = default_dialect
        self._cache = {}

    def _preprocess_dbt_jinja(self, sql_content: str) -> str:
        return preprocess_dbt_jinja(sql_content)

    def _is_macro_only(self, sql_content: str) -> bool:
        """True nếu file chỉ chứa định nghĩa macro dbt (macros/*.sql) — không
        có model/query thật nào để trích lineage. Macro không phải bảng,
        không có nguồn/đích, nên tốn 1 lần gọi LLM fallback (và rủi ro LLM bịa
        ra 1 cạnh không tồn tại) chỉ để rồi rút ra kết luận không có gì cả.
        """
        if not _MACRO_BLOCK.search(sql_content):
            return False
        remainder = _MACRO_BLOCK.sub("", sql_content)
        remainder = re.sub(r"\{#.*?#\}", "", remainder, flags=re.DOTALL)
        return not remainder.strip()

    def parse_file(self, file_path: str, dialect: str | None = None) -> list[LineageEdge]:
        """
        Đọc và parse một file .sql để trích xuất Data Lineage.

        :param file_path: Đường dẫn tới file .sql
        :param dialect: Ghi đè SQL dialect nếu cần
        :return: Danh sách các LineageEdge
        """
        edges, _ = self.parse_file_with_diagnostics(file_path, dialect=dialect)
        return edges

    def parse_file_with_diagnostics(
        self, file_path: str, dialect: str | None = None
    ) -> tuple[list[LineageEdge], str | None]:
        """
        Giống parse_file(), nhưng trả kèm lý do fail (dùng làm fallback_reason
        khi đưa file này qua LLM fallback) và gắn evidence (file_path/raw_sql/
        line_range) vào từng cạnh — evidence chỉ gắn được ở đây vì cần path.

        :return: (danh sách LineageEdge có evidence, lý do fail hoặc None nếu ok)
        """
        events, reason = self.parse_file_events(file_path, dialect=dialect)
        edges = [edge for event in events if event.kind == "edges" for edge in event.edges]
        return self._deduplicate_edges(edges), reason

    def parse_file_events(self, file_path: str, dialect: str | None = None) -> tuple[list[GraphEvent], str | None]:
        """Return ordered graph effects for one SQL file and an optional parse reason."""
        path = Path(file_path)
        if not path.exists():
            return [], f"File không tồn tại: {file_path}"

        try:
            sql_content = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error("Lỗi khi đọc file %s: %s", file_path, exc)
            return [], f"Lỗi đọc file: {exc}"

        import hashlib

        active_dialect = dialect or self.default_dialect
        normalized_file_path = str(path.resolve())
        hash_key = hashlib.sha256(f"{active_dialect}\x00{normalized_file_path}\x00{sql_content}".encode()).hexdigest()

        if hash_key in self._cache:
            cached_events_data, cached_reason = self._cache[hash_key]
            return self._recreate_cached_events(cached_events_data, file_path), cached_reason

        events, reason = self._parse_core_events(
            sql_content,
            file_path=file_path,
            target_table_fallback=path.stem,
            dialect=dialect,
        )
        events = self._attach_event_evidence(events, file_path=file_path, sql_content=sql_content)
        self._cache[hash_key] = ([event.model_dump() for event in events], reason)
        return events, reason

    def parse_sql_text(
        self, sql_content: str, target_table_fallback: str = "unknown_target", dialect: str | None = None
    ) -> list[LineageEdge]:
        """
        Parse nội dung chuỗi SQL và trích xuất các mối quan hệ lineage ở cấp độ cột.

        :param sql_content: Chuỗi câu lệnh SQL
        :param target_table_fallback: Tên bảng đích dự phòng nếu không tìm thấy trong AST
        :param dialect: Dialect của SQL
        :return: Danh sách các LineageEdge
        """
        edges, _ = self._parse_core(sql_content, target_table_fallback=target_table_fallback, dialect=dialect)
        return edges

    def parse_text_events(
        self, sql_content: str, dialect: str | None = None
    ) -> tuple[list[GraphEvent], str | None]:
        """Public seam for parsing inline SQL into ordered graph events."""
        return self._parse_core_events(
            sql_content,
            file_path="<inline>",
            target_table_fallback="unknown_target",
            dialect=dialect,
        )

    def _parse_core(
        self, sql_content: str, target_table_fallback: str = "unknown_target", dialect: str | None = None
    ) -> tuple[list[LineageEdge], str | None]:
        """Legacy edge-only adapter over the ordered event parser."""
        events, reason = self._parse_core_events(
            sql_content,
            file_path="<inline>",
            target_table_fallback=target_table_fallback,
            dialect=dialect,
        )
        edges = [edge for event in events if event.kind == "edges" for edge in event.edges]
        return self._deduplicate_edges(edges), reason

    def _parse_core_events(
        self,
        sql_content: str,
        *,
        file_path: str,
        target_table_fallback: str,
        dialect: str | None,
    ) -> tuple[list[GraphEvent], str | None]:
        """Parse SQL into graph effects, preserving statement order."""
        active_dialect = dialect or self.default_dialect

        if self._is_macro_only(sql_content):
            return [], None

        is_dbt_model = bool(_DBT_JINJA.search(sql_content))
        sql_content = self._preprocess_dbt_jinja(sql_content)

        # 1. Kiểm tra an toàn: Nếu câu lệnh chứa Dynamic SQL / Stored Procedure không thể parse tĩnh
        sql_clean = sql_content.strip()
        if "EXECUTE IMMEDIATE" in sql_clean.upper() or "CREATE OR REPLACE PROCEDURE" in sql_clean.upper():
            reason = "Phát hiện Dynamic SQL / Stored Procedure — không parse tĩnh được"
            logger.warning(f"[Parser Fail] {reason} -> Trả về [] để LLM Agent xử lý.")
            return [], reason

        try:
            # Tách file thành từng câu lệnh riêng biệt (theo dấu ";") — dùng
            # sqlglot.parse() thay vì parse_one(), vì parse_one() chỉ trả về
            # ĐÚNG 1 Expression cho cả chuỗi input. Với file nhiều câu lệnh
            # (nhiều CREATE TABLE/VIEW như file DDL export thực tế), parse_one()
            # âm thầm chỉ giữ lại 1 câu rồi bỏ hết phần còn lại — không lỗi,
            # không cảnh báo, khiến kết quả trông "linh tinh"/không liên quan.
            statements = [s for s in sqlglot_parse(sql_content, read=active_dialect) if s is not None]
        except (SqlglotError, Exception) as e:
            reason = f"sqlglot parse error: {e}"
            logger.warning(f"[Parser Failure] Không thể parse SQL: {e}")
            return [], reason

        if not statements:
            return [], "sqlglot không tách được câu lệnh nào hợp lệ"

        events: list[GraphEvent] = []
        for order, statement in enumerate(statements):
            try:
                ddl_event = self._extract_ddl_event(statement, file_path, order, active_dialect)
                if ddl_event is not None:
                    events.append(ddl_event)
                    continue

                # 2. Thu thập danh sách Alias/CTE để giải quyết nguồn gốc bảng gốc (Source Table Resolver)
                cte_map = self._build_cte_and_source_map(statement, active_dialect)

                # 3. Xác định Target Table chính (cần cte_map để biết bảng trong
                # FROM có thực sự là 1 CTE hay chỉ là bảng nguồn thô)
                target_table = self._extract_target_table(
                    statement,
                    fallback=target_table_fallback,
                    cte_names=set(cte_map),
                    dialect=active_dialect,
                    is_dbt_model=is_dbt_model,
                )

                # 4. Trích xuất Lineage cấp cột từ các câu SELECT
                statement_edges = self._extract_column_lineage(
                    statement, target_table=target_table, cte_map=cte_map, dialect=active_dialect
                )
                retained_edges = self._drop_invalid_edges(statement_edges)
                if retained_edges:
                    events.append(
                        GraphEvent(
                            file_path=file_path,
                            order=order,
                            kind="edges",
                            edges=self._deduplicate_edges(retained_edges),
                        )
                    )
                elif isinstance(statement, exp.Create):
                    target = self._extract_target_table(
                        statement,
                        fallback=target_table_fallback,
                        cte_names=set(cte_map),
                        dialect=active_dialect,
                        is_dbt_model=is_dbt_model,
                    )
                    events.append(
                        GraphEvent(
                            file_path=file_path,
                            order=order,
                            kind="declare",
                            table=target,
                            columns=self._extract_column_schema(statement),
                        )
                    )
                elif is_dbt_model:
                    cte_aliases = {cte.alias for cte in statement.find_all(exp.CTE)}
                    source_tables = set()
                    for table in statement.find_all(exp.Table):
                        table_name = table.name
                        if table_name in cte_aliases and table_name not in cte_map:
                            continue
                        source_tables.add(cte_map.get(table_name, qualified_table_name(table, active_dialect)))

                    table_edges = []
                    for source_table in sorted(source_tables):
                        if should_drop_edge(source_table, target_table) is None:
                            table_edges.append(
                                LineageEdge(
                                    source_table=source_table,
                                    source_column=None,
                                    target_table=target_table,
                                    target_column=None,
                                    transform_type="unknown",
                                    confidence=1.0,
                                    source_type="parser",
                                )
                            )
                    if table_edges:
                        events.append(GraphEvent(file_path=file_path, order=order, kind="edges", edges=table_edges))
            except Exception as e:
                # 1 câu lệnh lỗi (vd cú pháp dialect-specific lạ) không nên
                # làm mất lineage của các câu lệnh khác trong cùng file.
                logger.warning(f"[Parser Failure] Bỏ qua 1 statement không parse được: {e}")
                continue

        if not events:
            return [], "Parser không trích được cạnh nào (có thể SQL không có SELECT/JOIN rõ ràng)"
        return events, None

    def _extract_ddl_event(self, statement: exp.Expr, file_path: str, order: int, dialect: str) -> GraphEvent | None:
        if isinstance(statement, exp.Alter):
            old_table = statement.this
            for action in statement.args.get("actions") or []:
                if (
                    isinstance(action, exp.AlterRename)
                    and isinstance(old_table, exp.Table)
                    and isinstance(action.this, exp.Table)
                ):
                    return GraphEvent(
                        file_path=file_path,
                        order=order,
                        kind="rename",
                        table=qualified_table_name(old_table, dialect),
                        new_name=qualified_table_name(action.this, dialect),
                    )

        if isinstance(statement, exp.Drop) and statement.args.get("kind") == "TABLE":
            if isinstance(statement.this, exp.Table):
                return GraphEvent(
                    file_path=file_path,
                    order=order,
                    kind="drop",
                    table=qualified_table_name(statement.this, dialect),
                )
        return None

    @staticmethod
    def _parse_reference(ref: exp.Expression | None) -> tuple[str | None, str | None]:
        """(bảng, cột) được tham chiếu trong REFERENCES / FOREIGN KEY ... REFERENCES.

        sqlglot bọc đích tham chiếu trong `exp.Reference.this` = `exp.Schema`
        (Schema.this = Table, Schema.expressions = danh sách cột). Lấy cột đầu
        tiên — FK nhiều cột hiếm ở dữ liệu nguồn phân tích và impact chỉ cần
        biết "trỏ tới bảng nào".
        """
        if not isinstance(ref, exp.Reference):
            return None, None
        target = ref.this
        if isinstance(target, exp.Schema):
            tbl = target.this
            tbl_name = tbl.name if isinstance(tbl, exp.Table) else (tbl.sql() if tbl is not None else None)
            cols = [c.name for c in target.expressions if getattr(c, "name", None)]
            return tbl_name or None, (cols[0] if cols else None)
        if isinstance(target, exp.Table):
            return target.name or None, None
        return None, None

    def _extract_column_schema(self, statement: exp.Expression) -> list[ColumnSchema]:
        """Kiểu + constraint mỗi cột từ `CREATE TABLE x (col TYPE ...)` tường minh.

        Chỉ chạy khi statement có `exp.Schema` với `exp.ColumnDef` — tức DDL bảng
        nguồn thật. `CREATE TABLE x AS SELECT` không có danh sách cột nên trả `[]`,
        đường đi cũ (declare rỗng) giữ nguyên.
        """
        schema = statement.this
        if not isinstance(schema, exp.Schema):
            return []
        col_defs = [e for e in schema.expressions if isinstance(e, exp.ColumnDef)]
        if not col_defs:
            return []

        # Constraint mức bảng: PRIMARY KEY (a, b) / FOREIGN KEY (c) REFERENCES ...
        pk_cols: set[str] = set()
        fk_map: dict[str, tuple[str | None, str | None]] = {}
        for e in schema.expressions:
            if isinstance(e, exp.PrimaryKey):
                pk_cols.update(c.name for c in e.expressions if getattr(c, "name", None))
            elif isinstance(e, exp.ForeignKey):
                ref_tbl, ref_col = self._parse_reference(e.args.get("reference"))
                for c in e.expressions:
                    if getattr(c, "name", None):
                        fk_map[c.name] = (ref_tbl, ref_col)

        result: list[ColumnSchema] = []
        for cd in col_defs:
            kind = cd.args.get("kind")
            data_type = kind.sql() if kind is not None else None
            is_nullable = True
            is_pk = cd.name in pk_cols
            ref_tbl, ref_col = fk_map.get(cd.name, (None, None))
            is_fk = cd.name in fk_map
            for con in cd.constraints:
                k = getattr(con, "kind", None)
                if isinstance(k, exp.NotNullColumnConstraint):
                    # `NULL` tường minh => allow_null=True; chỉ `NOT NULL` mới chặn.
                    if not k.args.get("allow_null"):
                        is_nullable = False
                elif isinstance(k, exp.PrimaryKeyColumnConstraint):
                    is_pk = True
                elif isinstance(k, exp.UniqueColumnConstraint):
                    pass  # UNIQUE không đổi 4 field ta lưu; giữ để không rơi vào nhánh khác
                elif isinstance(k, exp.Reference):
                    is_fk = True
                    rt, rc = self._parse_reference(k)
                    ref_tbl, ref_col = rt or ref_tbl, rc or ref_col
            if is_pk:
                is_nullable = False
            result.append(
                ColumnSchema(
                    name=cd.name,
                    data_type=data_type,
                    is_nullable=is_nullable,
                    is_primary_key=is_pk,
                    is_foreign_key=is_fk,
                    references_table=ref_tbl,
                    references_column=ref_col,
                    origin="declared",
                )
            )
        return result

    def _drop_invalid_edges(self, edges: list[LineageEdge]) -> list[LineageEdge]:
        retained_edges = []
        for edge in edges:
            drop_reason = should_drop_edge(edge.source_table, edge.target_table)
            if drop_reason is not None:
                logger.debug(
                    "Dropping parser edge (%s): %s -> %s",
                    drop_reason,
                    edge.source_table,
                    edge.target_table,
                )
                continue
            retained_edges.append(edge)

        return retained_edges

    def _attach_evidence(self, edges: list[LineageEdge], file_path: str, sql_content: str) -> list[LineageEdge]:
        """Gắn file_path/raw_sql/line_range/reasoning cho từng cạnh — nguyên văn
        nội dung file, line_range là xấp xỉ (tìm dòng chứa tên cột/bảng), không
        phải vị trí AST chính xác vì sqlglot không track vị trí nguồn theo mặc
        định. reasoning là câu template dựa trên transform_type + line_range,
        không gọi LLM — parser đã biết chắc chắn 100%, chỉ cần diễn giải lại
        cho người đọc, không cần suy luận thêm."""
        total_lines = len(sql_content.splitlines()) or 1
        result = []
        for edge in edges:
            line_range = self._find_line_range(sql_content, edge.source_column, edge.source_table)
            evidence = (edge.evidence or LineageEvidence()).model_copy(
                update={
                    "file_path": file_path,
                    "raw_sql": sql_content,
                    "line_range": line_range,
                    "reasoning": self._explain_parser_edge(
                        edge.transform_type, line_range, total_lines, edge.dependency_kind
                    ),
                    "reasoning_detail": self._explain_parser_edge_detail(
                        edge.transform_type, line_range, total_lines, edge.dependency_kind
                    ),
                }
            )
            result.append(
                edge.model_copy(
                    update={
                        "evidence": evidence
                    }
                )
            )
        return result

    def _explain_parser_edge(
        self, transform_type: str, line_range: list[int], total_lines: int, dependency_kind: str = "output"
    ) -> str:
        if dependency_kind != "output":
            kind = _DEPENDENCY_EXPLANATIONS.get(dependency_kind, "Cột dùng trong một điều kiện của truy vấn")
        else:
            kind = _TRANSFORM_EXPLANATIONS.get(transform_type, _TRANSFORM_EXPLANATIONS["unknown"])
        # _find_line_range trả về [1, total_lines] khi không tìm thấy needle nào
        # trong file — đây là fallback "cả file", không phải vị trí chính xác,
        # nên phải nói rõ thay vì giả vờ đã xác định được dòng cụ thể.
        if line_range == [1, total_lines] and total_lines > 1:
            return f"{kind} (vị trí chính xác không xác định được, xem toàn bộ file)"
        if line_range[0] == line_range[1]:
            return f"{kind}, phát hiện tại dòng {line_range[0]}"
        return f"{kind}, phát hiện trong khoảng dòng {line_range[0]}-{line_range[1]}"

    def _explain_parser_edge_detail(
        self, transform_type: str, line_range: list[int], total_lines: int, dependency_kind: str = "output"
    ) -> str:
        """Bản dài cho evidence.reasoning_detail — diễn giải cơ chế biến đổi +
        vì sao cạnh parser chắc chắn 100% và không cần HITL. Không trích SQL
        nguyên văn (drawer đã có mục Raw SQL riêng)."""
        if dependency_kind != "output":
            body = _DEPENDENCY_DETAIL.get(
                dependency_kind, "Cột này nằm trong một điều kiện của truy vấn, không phải cột dữ liệu output."
            )
        else:
            body = _TRANSFORM_DETAIL.get(transform_type, _TRANSFORM_DETAIL["unknown"])
        if line_range == [1, total_lines] and total_lines > 1:
            loc = "Không xác định được dòng cụ thể trong file nguồn — xem toàn bộ SQL gốc bên dưới."
        elif line_range[0] == line_range[1]:
            loc = f"Phát hiện tại dòng {line_range[0]} của file nguồn (xem SQL gốc bên dưới)."
        else:
            loc = (
                f"Phát hiện trong khoảng dòng {line_range[0]}–{line_range[1]} của file nguồn "
                "(xem SQL gốc bên dưới)."
            )
        return (
            "Cạnh do parser tĩnh sqlglot phân giải trực tiếp từ cây cú pháp (AST) của câu lệnh SQL, "
            "không qua suy luận của mô hình ngôn ngữ — vì vậy độ tin cậy là 100% và cạnh không cần "
            f"đi qua bước duyệt thủ công (HITL). {body} {loc}"
        )

    def _attach_event_evidence(self, events: list[GraphEvent], file_path: str, sql_content: str) -> list[GraphEvent]:
        return [
            event.model_copy(update={"edges": self._attach_evidence(event.edges, file_path, sql_content)})
            if event.kind == "edges"
            else event
            for event in events
        ]

    def _recreate_cached_events(self, cached_events_data: list[dict], file_path: str) -> list[GraphEvent]:
        from uuid import uuid4

        recreated_events = []
        for event_data in cached_events_data:
            copied_data = event_data.copy()
            copied_data["file_path"] = file_path
            recreated_edges = []
            for edge_data in copied_data.get("edges", []):
                copied_edge = edge_data.copy()
                copied_edge["edge_id"] = str(uuid4())
                if copied_edge.get("evidence") is not None:
                    copied_evidence = copied_edge["evidence"].copy()
                    copied_evidence["file_path"] = file_path
                    copied_edge["evidence"] = copied_evidence
                recreated_edges.append(copied_edge)
            copied_data["edges"] = recreated_edges
            recreated_events.append(GraphEvent.model_validate(copied_data))
        return recreated_events

    def _find_line_range(self, sql_content: str, *needles: str | None) -> list[int]:
        """Xấp xỉ dòng chứa 1 trong các needle (ưu tiên needle đầu). Không tìm
        thấy cái nào thì trả về toàn bộ file — line_range không bao giờ rỗng."""
        lines = sql_content.splitlines() or [sql_content]
        for needle in needles:
            if not needle:
                continue
            needle_lower = needle.lower()
            for i, line in enumerate(lines, start=1):
                if needle_lower in line.lower():
                    return [i, i]
        return [1, len(lines)]

    def parse_directory(self, dir_path: str, dialect: str | None = None) -> list[LineageEdge]:
        """
        Quét và parse toàn bộ các file .sql trong một thư mục.
        """
        all_edges: list[LineageEdge] = []
        path = Path(dir_path)

        if not path.is_dir():
            raise NotADirectoryError(f"Thư mục không tồn tại: {dir_path}")

        for root, _, files in os.walk(path):
            for file in sorted(files):
                if file.endswith(".sql"):
                    file_full_path = os.path.join(root, file)
                    edges = self.parse_file(file_full_path, dialect=dialect)
                    all_edges.extend(edges)

        return self._deduplicate_edges(all_edges)

    # =========================================================================
    # Các hàm bổ trợ Helper nội bộ (Internal Resolver Helpers)
    # =========================================================================

    def _extract_target_table(
        self,
        parsed: exp.Expression,
        fallback: str,
        cte_names: set[str] | None = None,
        dialect: str = "postgres",
        is_dbt_model: bool = False,
    ) -> str:
        """Trích xuất tên bảng đích từ CREATE TABLE / INSERT INTO / CTE cuối.

        Chỉ coi bảng trong FROM là "target" nếu nó thực sự là 1 CTE đã định
        nghĩa (vd `WITH renamed AS (...) SELECT * FROM renamed`) — nếu FROM
        trỏ thẳng vào 1 bảng nguồn thô (không có CTE nào cả), đó là bảng
        NGUỒN chứ không phải đích, phải dùng fallback (tên file).
        """
        if isinstance(parsed, exp.Create):
            if parsed.this and isinstance(parsed.this, exp.Schema):
                return qualified_table_name(parsed.this.this, dialect)
            elif isinstance(parsed.this, exp.Table):
                return qualified_table_name(parsed.this, dialect)
        elif isinstance(parsed, exp.Insert):
            if isinstance(parsed.this, exp.Table):
                return qualified_table_name(parsed.this, dialect)

        if is_dbt_model:
            return fallback

        # Nếu có CTE cuối cùng được SELECT
        # Lưu ý: key nội bộ đổi "from" -> "from_" giữa các bản sqlglot (đang
        # cài 30.x, code gốc viết cho <30 dùng "from") — thử cả 2 key để không
        # âm thầm gãy lần nữa nếu version đổi tiếp.
        select_expr = parsed.find(exp.Select)
        from_clause = (select_expr.args.get("from_") or select_expr.args.get("from")) if select_expr else None
        if from_clause:
            if isinstance(from_clause.this, exp.Table):
                potential_target = from_clause.this.name
                if potential_target and cte_names and potential_target in cte_names:
                    return potential_target

        return fallback

    def _build_cte_and_source_map(self, parsed: exp.Expression, dialect: str) -> dict:
        """
        Xây dựng bản đồ ánh xạ từ CTE / Alias về Bảng Nguồn Gốc (Raw Source Table)
        bằng thuật toán Transitive Resolution (phân giải bắc cầu/đệ quy).
        """
        cte_map = {}
        for cte in parsed.find_all(exp.CTE):
            alias_name = cte.alias
            # Tìm bảng nguồn bên trong CTE
            tables = [
                (t.name, qualified_table_name(t, dialect)) for t in cte.find_all(exp.Table) if t.name != alias_name
            ]
            if tables:
                cte_map[alias_name] = tables[0][1]

        # Thực hiện phân giải đệ quy (Transitive Resolution) để tìm bảng gốc thực sự
        resolved_map = {}
        for alias, table in cte_map.items():
            visited = set()
            curr = table
            while curr in cte_map and curr not in visited:
                visited.add(curr)
                curr = cte_map[curr]
            resolved_map[alias] = curr

        return resolved_map

    def _resolve_explicit_select_columns(
        self, select_node: exp.Select, cte_map: dict, dialect: str
    ) -> list[tuple[str, str, list[tuple[str, str]]]]:
        """Resolve 1 câu SELECT có cột tường minh (không phải `SELECT *`) thành
        danh sách (target_col, transform_type, [(source_table, source_col), ...])
        theo đúng thứ tự cột output — dùng chung cho main_select lẫn từng nhánh
        UNION (xem `_resolve_union_branch_columns`), tách ra để không lặp logic.
        """
        tables_in_query: dict[str, str] = {}
        for table in select_node.find_all(exp.Table):
            tbl_name = table.name
            tbl_alias = table.alias or tbl_name
            resolved_table = cte_map.get(tbl_name, qualified_table_name(table, dialect))
            tables_in_query[tbl_alias] = resolved_table
            tables_in_query[tbl_name] = resolved_table

        default_source_table = list(tables_in_query.values())[0] if tables_in_query else "unknown_source"

        resolved: list[tuple[str, str, list[tuple[str, str]]]] = []
        for expression in select_node.expressions:
            if isinstance(expression, exp.Star):
                continue

            target_col = expression.alias_or_name
            transform_type = self._determine_transform_type(expression)
            source_columns = list(expression.find_all(exp.Column))
            sources: list[tuple[str, str]] = []
            for src_col in source_columns:
                raw_table = src_col.table or default_source_table
                actual_source_table = tables_in_query.get(raw_table, raw_table)
                actual_source_table = cte_map.get(actual_source_table, actual_source_table)
                sources.append((actual_source_table, src_col.name))
            resolved.append((target_col, transform_type, sources))

        return resolved

    def _resolve_union_branch_columns(
        self,
        select_node: exp.Select,
        cte_defs: dict[str, exp.Expression],
        cte_map: dict,
        dialect: str,
        depth: int = 0,
    ) -> list[tuple[str, str, list[tuple[str, str]]]] | None:
        """Resolve cột output của 1 nhánh UNION. Nếu nhánh có cột tường minh,
        dùng thẳng. Nếu nhánh chỉ là `SELECT * FROM <cte>` (khuôn dbt phổ biến
        — xem `stg_orders.sql`: CTE cuối cùng luôn `select * from renamed`),
        lần ngược 1 cấp vào CTE đó để lấy cột tường minh của nó. Giới hạn
        depth=3 để tránh đệ quy vô hạn nếu SQL có cấu trúc lạ/cycle.
        """
        has_explicit = any(not isinstance(e, exp.Star) for e in select_node.expressions)
        if has_explicit:
            return self._resolve_explicit_select_columns(select_node, cte_map, dialect)

        if depth >= 3:
            return None

        from_clause = select_node.args.get("from_") or select_node.args.get("from")
        if not from_clause or not isinstance(from_clause.this, exp.Table):
            return None

        ref_name = from_clause.this.name
        inner = cte_defs.get(ref_name)
        if isinstance(inner, exp.Select):
            return self._resolve_union_branch_columns(inner, cte_defs, cte_map, dialect, depth + 1)

        return None

    def _flatten_union_branches(self, node: exp.Expression) -> list[exp.Select]:
        """Trải phẳng 1 cây UNION/EXCEPT/INTERSECT (kể cả UNION nối chuỗi
        A UNION B UNION C, sqlglot parse lồng nhau) thành list Select theo
        đúng thứ tự trái sang phải."""
        branches: list[exp.Select] = []

        def walk(n: exp.Expression) -> None:
            if isinstance(n, (exp.Union, exp.Except, exp.Intersect)):
                walk(n.this)
                walk(n.expression)
            elif isinstance(n, exp.Select):
                branches.append(n)

        walk(node)
        return branches

    def _extract_column_lineage(
        self, parsed: exp.Expression, target_table: str, cte_map: dict, dialect: str
    ) -> list[LineageEdge]:
        """Duyệt các biểu thức SELECT để xác định nguồn gốc từng cột."""
        edges: list[LineageEdge] = []

        # Lấy câu lệnh SELECT chính (hoặc SELECT trong CTE cuối)
        select_statements = list(parsed.find_all(exp.Select))
        if not select_statements:
            return edges

        # Mặc định lấy câu SELECT ngoài cùng (phần tử đầu tiên trong DFS/AST của SQLGlot)
        main_select = select_statements[0]

        # Kiểm tra xem câu SELECT ngoài cùng có chứa các cột tường minh hay không
        # Nếu nó chỉ chứa Star (Wildcard) và có các CTE, ta sẽ chuyển sang phân tích câu SELECT của CTE cuối cùng
        has_explicit_columns = False
        for expression in main_select.expressions:
            if not isinstance(expression, exp.Star):
                has_explicit_columns = True
                break

        # Nếu chỉ có wildcard và có nhiều hơn 1 select (tức là có CTE)
        if not has_explicit_columns and len(select_statements) > 1:
            # UNION ALL của 2 CTE (vd `all_orders`) không phải 1 Select đơn —
            # select_statements[-1] có thể rơi vào nhánh UNION sai (vẫn là
            # SELECT * khác), khiến toàn bộ mất cạnh. Nếu CTE định nghĩa
            # target_table thực sự là 1 khối UNION/EXCEPT/INTERSECT, xử lý
            # riêng bằng cách match cột THEO VỊ TRÍ giữa các nhánh — khác hẳn
            # luật resolve theo TÊN của SELECT thường (xem docstring
            # `_resolve_union_branch_columns`). Chỉ kích hoạt khi thực sự có
            # UNION liên quan tới target_table — mọi case khác đi qua nhánh
            # cũ y nguyên, không đổi hành vi.
            cte_defs: dict[str, exp.Expression] = {cte.alias: cte.this for cte in parsed.find_all(exp.CTE)}
            union_node = cte_defs.get(target_table)
            if isinstance(union_node, (exp.Union, exp.Except, exp.Intersect)):
                union_edges = self._extract_union_column_lineage(union_node, target_table, cte_defs, cte_map, dialect)
                if union_edges:
                    return union_edges
                # Không resolve được nhánh nào (vd cả 2 nhánh đều tham chiếu
                # bảng thô ngoài dự án) — rơi về hành vi cũ bên dưới thay vì
                # trả rỗng sớm, giữ nguyên mức độ "cố gắng" như trước khi có
                # nhánh UNION này.

            main_select = select_statements[-1]

        # Thu thập các bảng ở nguồn (FROM & JOIN)
        tables_in_query = {}
        for table in main_select.find_all(exp.Table):
            tbl_name = table.name
            tbl_alias = table.alias or tbl_name
            # Resolve về bảng nguồn gốc nếu là CTE
            resolved_table = cte_map.get(tbl_name, qualified_table_name(table, dialect))
            tables_in_query[tbl_alias] = resolved_table
            tables_in_query[tbl_name] = resolved_table

        default_source_table = list(tables_in_query.values())[0] if tables_in_query else "unknown_source"

        # Duyệt từng cột đầu ra trong SELECT
        for expression in main_select.expressions:
            target_col = expression.alias_or_name

            # Bỏ qua wildcard (*)
            if isinstance(expression, exp.Star):
                continue

            expression_sql = expression.sql(dialect=dialect)

            # Xác định kiểu biến đổi (transform_type)
            transform_type = self._determine_transform_type(expression)

            # Tìm tất cả các cột nguồn xuất hiện trong biểu thức
            source_columns = list(expression.find_all(exp.Column))

            if source_columns:
                for src_col in source_columns:
                    raw_table = src_col.table or default_source_table
                    actual_source_table = tables_in_query.get(raw_table, raw_table)
                    # Trường hợp tham chiếu trực tiếp qua CTE map
                    actual_source_table = cte_map.get(actual_source_table, actual_source_table)

                    edge = LineageEdge(
                        source_table=actual_source_table,
                        source_column=src_col.name,
                        target_table=target_table,
                        target_column=target_col,
                        transform_type=transform_type,
                        confidence=1.0,
                        source_type="parser",
                        evidence=LineageEvidence(transform_expression=expression_sql),
                    )
                    edges.append(edge)

        edges.extend(
            self._extract_control_lineage(main_select, target_table, tables_in_query, cte_map, default_source_table)
        )
        return edges

    def _extract_control_lineage(
        self,
        select: exp.Select,
        target_table: str,
        tables_in_query: dict[str, str],
        cte_map: dict,
        default_source_table: str,
    ) -> list[LineageEdge]:
        """Control lineage: cột nguồn KHÔNG chảy vào cột output nào nhưng quyết
        định HÀNG NÀO của bảng đích xuất hiện — WHERE/HAVING (`filter`),
        ON/USING (`join_key`), GROUP BY (`group_key`), OVER PARTITION BY/ORDER
        BY (`window_partition`/`window_order`). `target_column` luôn None. Bổ
        sung cho _extract_column_lineage (chỉ bắt output lineage); cùng
        confidence 1.0 vì đọc thẳng từ AST.

        Cột không kèm tên bảng trong truy vấn nhiều bảng thì BỎ QUA (không
        đoán) — sai quy kết ở control edge tạo phụ thuộc ma, nguy hiểm hơn ở
        output edge.
        """
        edges: list[LineageEdge] = []
        distinct_sources = {v for v in tables_in_query.values()}
        multi_table = len(distinct_sources) > 1

        def emit(columns, kind: str) -> None:
            for col in columns:
                if not isinstance(col, exp.Column) or not col.name:
                    continue
                if col.table:
                    src_table = tables_in_query.get(col.table, col.table)
                elif not multi_table and distinct_sources:
                    src_table = next(iter(distinct_sources))
                else:
                    continue
                src_table = cte_map.get(src_table, src_table)
                if src_table == target_table:
                    continue
                edges.append(
                    LineageEdge(
                        source_table=src_table,
                        source_column=col.name,
                        target_table=target_table,
                        target_column=None,
                        dependency_kind=kind,  # type: ignore[arg-type]
                        transform_type="unknown",
                        confidence=1.0,
                        source_type="parser",
                    )
                )

        for clause in ("where", "having"):
            node = select.args.get(clause)
            if node is not None:
                emit(node.find_all(exp.Column), "filter")

        for join in select.find_all(exp.Join):
            on = join.args.get("on")
            if on is not None:
                emit(on.find_all(exp.Column), "join_key")
            for using in join.args.get("using") or []:
                emit(using.find_all(exp.Column) if hasattr(using, "find_all") else [], "join_key")

        group = select.args.get("group")
        if group is not None:
            emit(group.find_all(exp.Column), "group_key")

        for window in select.find_all(exp.Window):
            for part in window.args.get("partition_by") or []:
                emit(part.find_all(exp.Column), "window_partition")
            order = window.args.get("order")
            if order is not None:
                emit(order.find_all(exp.Column), "window_order")

        return edges

    def _extract_union_column_lineage(
        self,
        union_node: exp.Union | exp.Except | exp.Intersect,
        target_table: str,
        cte_defs: dict[str, exp.Expression],
        cte_map: dict,
        dialect: str,
    ) -> list[LineageEdge]:
        """Match cột giữa các nhánh UNION/EXCEPT/INTERSECT THEO VỊ TRÍ (cột
        thứ N nhánh A ứng với cột thứ N nhánh B) — tên cột output lấy theo
        nhánh trái nhất resolve được (đúng ngữ nghĩa SQL: UNION lấy tên cột
        theo SELECT đầu tiên). Mỗi cạnh vẫn là ánh xạ cột-sang-cột trực tiếp
        (giữ "direct"/transform_type của biểu thức gốc, không có giá trị
        "union" riêng — ngoài hợp đồng `LineageEdge.transform_type`).
        """
        branches = self._flatten_union_branches(union_node)
        resolved_branches = [self._resolve_union_branch_columns(b, cte_defs, cte_map, dialect) for b in branches]

        # Tên cột output theo nhánh trái nhất resolve được (không nhất thiết
        # là nhánh đầu tiên, nếu nhánh đầu chẳng may không resolve được).
        column_names: list[str] | None = None
        for resolved in resolved_branches:
            if resolved:
                column_names = [name for name, _transform, _sources in resolved]
                break
        if column_names is None:
            return []

        edges: list[LineageEdge] = []
        for resolved in resolved_branches:
            if not resolved:
                continue
            for position, (_name, transform_type, sources) in enumerate(resolved):
                if position >= len(column_names):
                    break
                for source_table, source_column in sources:
                    edges.append(
                        LineageEdge(
                            source_table=source_table,
                            source_column=source_column,
                            target_table=target_table,
                            target_column=column_names[position],
                            transform_type=transform_type,
                            confidence=1.0,
                            source_type="parser",
                        )
                    )
        return edges

    def _determine_transform_type(self, expression: exp.Expression) -> str:
        """
        Phân loại kiểu biến đổi dựa trên AST của biểu thức.

        Trả về 1 trong các giá trị của LineageEdge.transform_type
        (src/models/schemas.py: direct/conditional/aggregation/join/unknown) —
        hợp đồng dùng chung với llm_extraction_service và frontend
        (frontend/src/types/backend.ts). Window function gộp vào "aggregation"
        (đều là "tính toán, không truyền thẳng"); PARTITION BY/ORDER BY của
        window được bắt riêng qua dependency_kind.
        """
        # Trực tiếp (Direct column assignment)
        if isinstance(expression, exp.Column) or (
            isinstance(expression, exp.Alias) and isinstance(expression.this, exp.Column)
        ):
            return "direct"

        # Window Function (ROW_NUMBER(), RANK(), OVER...) -> gần với aggregation nhất
        if expression.find(exp.Window):
            return "aggregation"

        # Aggregate (kể cả SUM(CASE WHEN...)) — ưu tiên trước "conditional" vì
        # bản chất chính là gộp hàng, phần CASE chỉ là điều kiện bên trong.
        if any(expression.find(agg) for agg in [exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Group]):
            return "aggregation"

        # Conditional: giá trị cột đích PHỤ THUỘC điều kiện (CASE WHEN / COALESCE /
        # NULLIF / IF / IIF) — KHÔNG phải truyền nguyên trạng. Đổi tập giá trị của
        # cột điều kiện làm sai kết quả mà không có tín hiệu ở cấp cột.
        if expression.find(exp.Case, exp.Coalesce, exp.If, exp.Nullif):
            return "conditional"

        return "direct"

    def _deduplicate_edges(self, edges: list[LineageEdge]) -> list[LineageEdge]:
        """Loại bỏ các cạnh bị lặp lại."""
        seen: set[tuple] = set()
        unique_edges: list[LineageEdge] = []

        for e in edges:
            key = (
                e.source_table,
                e.source_column,
                e.target_table,
                e.target_column,
                e.transform_type,
                e.dependency_kind,
            )
            if key not in seen:
                seen.add(key)
                unique_edges.append(e)

        return unique_edges
