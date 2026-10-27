"""Shared impact-query logic for HTTP routes and chatbot fact collection."""

from typing import Literal

from src.models.schemas import ImpactEdgeView, ImpactQueryResult, LineageEdge
from src.services import graph_service, review_service, storage_service

ChangeKind = Literal[
    "type", "value", "drop", "rename", "drop_table", "rename_table", "add_column", "constraint"
]

# Rủi ro khi user hỏi/chọn "nếu đổi/xóa/đổi tên cột (hoặc cả bảng) X thì sao"
# — map theo transform_type của TỪNG cạnh đã đi qua, không phải 1 câu chung
# chung cho cả kết quả. 8 change_kind, mức độ nghiêm trọng khác hẳn nhau:
# - "type": đổi kiểu dữ liệu 1 cột (schema change) — có thể vỡ phép toán/join ngay.
# - "value": đổi giá trị/nội dung 1 cột — không crash nhưng sai số liệu downstream.
# - "drop": xóa hẳn 1 CỘT — dữ liệu biến mất, downstream chắc chắn lỗi nếu
#   còn tham chiếu (nghiêm trọng nhất trong nhóm cột, vì không có gì để rơi về).
# - "rename": đổi tên 1 CỘT — dữ liệu còn nguyên, chỉ downstream tham chiếu
#   tên cũ sẽ không tìm thấy cột (nhẹ hơn "drop" vì chỉ cần cập nhật SQL).
# - "drop_table"/"rename_table": tương ứng "drop"/"rename" nhưng ở mức CẢ
#   BẢNG — văn phong phải nói về "bảng"/"nguồn dữ liệu", KHÔNG được ghi
#   "cột" (case có thật: user chọn "Xóa toàn bộ bảng" nhưng risk text lại
#   ghi "xóa cột" — sai ngữ cảnh, đã sửa bằng cách tách change_kind riêng
#   thay vì dùng chung "drop"/"rename" cho cả 2 cấp độ).
# - "add_column": thêm 1 CỘT MỚI — không phá dữ liệu hiện có, rủi ro chỉ tới
#   từ downstream dùng SELECT * và validate schema cứng (silent schema drift).
#   Nhẹ nhất trong 8 change_kind, nhưng vẫn cần cảnh báo vì có case vỡ thật.
# - "constraint": thêm NOT NULL / đổi PRIMARY KEY-FOREIGN KEY / đổi
#   partition-clustering key trên 1 CỘT đã tồn tại — không đổi giá trị dữ
#   liệu nên khác hẳn "type"/"value", nhưng có thể chặn ghi dữ liệu hiện có
#   (NOT NULL) hoặc mất ràng buộc tham chiếu (đổi FK) — cảnh báo riêng thay
#   vì gộp vào "type" vì bản chất rủi ro khác nhau (constraint vs kiểu dữ liệu).
# Dùng chung cho cả REST /impact/{table} lẫn chat capability downstream/
# upstream — không lặp bảng này ở 2 nơi.
_RISK_BY_TRANSFORM: dict[str, dict[ChangeKind, str]] = {
    "join": {
        "type": "Rủi ro cao: cột này dùng làm khoá join — đổi kiểu dữ liệu có thể làm join không còn khớp kiểu, mất hàng ở kết quả.",
        "value": "Rủi ro trung bình: cột này dùng làm khoá join — đổi giá trị làm thay đổi tập hàng match, ảnh hưởng số liệu ở bảng đích.",
        "drop": "Rủi ro nghiêm trọng: cột này dùng làm khoá join — xóa sẽ làm downstream lỗi ngay lập tức vì mất điều kiện join.",
        "rename": "Rủi ro cao: cột này dùng làm khoá join — đổi tên làm downstream không còn tìm thấy cột để join, phải cập nhật SQL đồng thời.",
        "drop_table": "Rủi ro nghiêm trọng: bảng này là nguồn cho 1 phép join ở downstream — xóa cả bảng làm mất toàn bộ điều kiện join, downstream lỗi ngay lập tức (không chỉ mất 1 cột).",
        "rename_table": "Rủi ro cao: bảng này là nguồn cho 1 phép join ở downstream — đổi tên cả bảng làm downstream không còn tìm thấy bảng nguồn để join, phải cập nhật SQL/ref đồng thời.",
        "add_column": "Rủi ro thấp: thêm cột mới không ảnh hưởng khoá join hiện có ở cạnh này — nhưng nếu downstream dùng SELECT * để join tiếp, cột mới sẽ lan xuống ngoài dự kiến.",
        "constraint": "Rủi ro cao: cột này dùng làm khoá join — thêm NOT NULL hoặc đổi PRIMARY KEY/FOREIGN KEY có thể chặn ghi dữ liệu hiện có (nếu đang tồn tại NULL) hoặc làm mất ràng buộc tham chiếu, ảnh hưởng trực tiếp tính đúng đắn của phép join.",
    },
    "aggregation": {
        "type": "Rủi ro cao: cột này được tổng hợp (SUM/AVG/COUNT...) — đổi kiểu dữ liệu có thể làm phép tổng hợp lỗi hoặc tính sai.",
        "value": "Rủi ro trung bình: cột này được tổng hợp — đổi giá trị làm thay đổi trực tiếp kết quả tổng hợp ở bảng đích.",
        "drop": "Rủi ro nghiêm trọng: cột này được tổng hợp (SUM/AVG/COUNT...) — xóa sẽ làm downstream lỗi vì mất input cho phép tổng hợp.",
        "rename": "Rủi ro cao: cột này được tổng hợp — đổi tên làm downstream lỗi vì không tìm thấy cột nguồn, phải cập nhật SQL đồng thời.",
        "drop_table": "Rủi ro nghiêm trọng: bảng này là nguồn cho 1 phép tổng hợp (SUM/AVG/COUNT...) ở downstream — xóa cả bảng làm mất toàn bộ input, downstream lỗi ngay lập tức.",
        "rename_table": "Rủi ro cao: bảng này là nguồn cho 1 phép tổng hợp ở downstream — đổi tên cả bảng làm downstream lỗi vì không tìm thấy bảng nguồn, phải cập nhật SQL/ref đồng thời.",
        "add_column": "Rủi ro thấp: thêm cột mới không ảnh hưởng phép tổng hợp hiện có ở cạnh này — nhưng downstream dùng SELECT * bao quanh phép tổng hợp sẽ nhận thêm cột ngoài dự kiến.",
        "constraint": "Rủi ro trung bình: cột này được tổng hợp — đổi constraint không đổi phép tính, nhưng đổi PRIMARY KEY/FOREIGN KEY có thể làm mất ràng buộc tham chiếu tới dữ liệu nguồn cho phép tổng hợp.",
    },
    "direct": {
        "type": "Rủi ro trung bình: dữ liệu được truyền nguyên trạng — đổi kiểu có thể phá vỡ hệ thống đích nếu họ kỳ vọng kiểu cũ.",
        "value": "Rủi ro thấp: giá trị mới truyền thẳng xuống bảng đích, cần rà lại logic dùng cột này ở đó.",
        "drop": "Rủi ro cao: dữ liệu được truyền nguyên trạng — xóa cột làm downstream mất hẳn trường dữ liệu này, lỗi nếu còn SELECT tường minh.",
        "rename": "Rủi ro trung bình: dữ liệu được truyền nguyên trạng — đổi tên làm downstream không còn thấy cột cũ, cần cập nhật SQL đồng thời.",
        "drop_table": "Rủi ro cao: dữ liệu từ bảng này được truyền nguyên trạng xuống downstream — xóa cả bảng làm downstream mất hẳn toàn bộ nguồn dữ liệu này, lỗi nếu còn tham chiếu.",
        "rename_table": "Rủi ro trung bình: dữ liệu từ bảng này được truyền nguyên trạng — đổi tên cả bảng làm downstream không còn thấy bảng nguồn, cần cập nhật SQL/ref đồng thời.",
        "add_column": "Rủi ro thấp: thêm cột mới không phá vỡ dữ liệu truyền nguyên trạng ở cạnh này — nhưng nếu downstream dùng SELECT * và validate schema cứng (BI tool, view khai báo cột), cột lạ có thể làm vỡ contract.",
        "constraint": "Rủi ro trung bình: đổi constraint (NOT NULL/PRIMARY KEY/FOREIGN KEY/partition key) không đổi giá trị dữ liệu truyền xuống, nhưng có thể chặn ghi dữ liệu hiện có (NOT NULL) hoặc đổi hiệu năng truy vấn downstream (đổi partition/clustering key).",
    },
    "conditional": {
        "type": "Rủi ro cao: cột đích suy ra từ biểu thức điều kiện (CASE/COALESCE) trên cột này — đổi kiểu có thể làm phép so sánh trong CASE sai kiểu hoặc đổi nhánh được chọn.",
        "value": "Rủi ro cao: cột đích là kết quả CASE/COALESCE dựa trên cột này — đổi TẬP GIÁ TRỊ (vd thêm 1 giá trị enum mới) làm nhánh điều kiện rơi sai, cột đích sai lệch mà không cột nào ở downstream báo. KHÔNG phải 'truyền thẳng'.",
        "drop": "Rủi ro nghiêm trọng: cột đích được tính bằng CASE/COALESCE trên cột này — xóa làm biểu thức điều kiện mất input, downstream lỗi biên dịch.",
        "rename": "Rủi ro cao: cột này là input cho biểu thức điều kiện (CASE/COALESCE) sinh ra cột đích — đổi tên làm downstream lỗi vì không tìm thấy cột, phải cập nhật SQL đồng thời.",
        "drop_table": "Rủi ro nghiêm trọng: bảng này cấp input cho một biểu thức điều kiện (CASE/COALESCE) ở downstream — xóa cả bảng làm mất input, downstream lỗi ngay.",
        "rename_table": "Rủi ro cao: bảng này cấp input cho biểu thức điều kiện ở downstream — đổi tên cả bảng làm downstream lỗi vì không tìm thấy bảng nguồn, phải cập nhật SQL/ref đồng thời.",
        "add_column": "Rủi ro thấp: thêm cột mới không ảnh hưởng biểu thức điều kiện hiện có ở cạnh này.",
        "constraint": "Rủi ro trung bình: cột đích tính bằng CASE/COALESCE trên cột này — đổi constraint không đổi giá trị, nhưng đổi PRIMARY KEY/FOREIGN KEY có thể mất ràng buộc tham chiếu tới dữ liệu nguồn của biểu thức.",
    },
    "unknown": {
        "type": "Chưa xác định được loại transform cho cạnh này — không thể đánh giá chắc chắn, cần kiểm tra thủ công.",
        "value": "Chưa xác định được loại transform cho cạnh này — không thể đánh giá chắc chắn, cần kiểm tra thủ công.",
        "drop": "Chưa xác định được loại transform cho cạnh này — không thể đánh giá chắc chắn mức độ ảnh hưởng khi xóa cột, cần kiểm tra thủ công.",
        "rename": "Chưa xác định được loại transform cho cạnh này — không thể đánh giá chắc chắn mức độ ảnh hưởng khi đổi tên cột, cần kiểm tra thủ công.",
        "drop_table": "Chưa xác định được loại transform cho cạnh này — không thể đánh giá chắc chắn mức độ ảnh hưởng khi xóa cả bảng, cần kiểm tra thủ công.",
        "rename_table": "Chưa xác định được loại transform cho cạnh này — không thể đánh giá chắc chắn mức độ ảnh hưởng khi đổi tên cả bảng, cần kiểm tra thủ công.",
        "add_column": "Chưa xác định được loại transform cho cạnh này — không thể đánh giá chắc chắn mức độ ảnh hưởng khi thêm cột mới, cần kiểm tra thủ công.",
        "constraint": "Chưa xác định được loại transform cho cạnh này — không thể đánh giá chắc chắn mức độ ảnh hưởng khi đổi constraint, cần kiểm tra thủ công.",
    },
}


# Rủi ro cho cạnh CONTROL LINEAGE (dependency_kind != "output"): cột nguồn KHÔNG
# vào giá trị cột output nào ở bảng đích, nhưng quyết định HÀNG NÀO của bảng đích
# xuất hiện. Rủi ro khác hẳn nhóm output: xoá/đổi tên làm model LỖI BIÊN DỊCH
# (tham chiếu cột không tồn tại); đổi kiểu/giá trị làm SỐ HÀNG bảng đích đổi mà
# không cột output nào báo. Mỗi dict phủ ĐỦ 8 change_kind (kể cả drop_table/
# rename_table/add_column/constraint) — cạnh control luôn transform_type="unknown"
# nên nếu rơi về _RISK_BY_TRANSFORM sẽ ra câu "chưa xác định, kiểm tra thủ công",
# vừa nhiễu vừa sai mức (thêm 1 cột mới KHÔNG đụng vai trò lọc/join; còn đổi
# PK/FK/UNIQUE trên khoá join lại là rủi ro CAO). risk_note() nhờ đó không bao
# giờ đụng _RISK_BY_TRANSFORM khi dependency_kind != "output".
_RISK_BY_DEPENDENCY: dict[str, dict[str, str]] = {
    "filter": {
        "drop": "Rủi ro nghiêm trọng: cột này nằm trong điều kiện lọc (WHERE/HAVING) của bảng đích, không xuất hiện ở cột output nào — xoá làm model đích LỖI BIÊN DỊCH (tham chiếu cột không tồn tại) và thay đổi tập hàng.",
        "rename": "Rủi ro cao: cột này dùng để lọc hàng ở bảng đích (WHERE/HAVING) — đổi tên làm model đích lỗi vì không còn tìm thấy cột, phải cập nhật SQL đồng thời.",
        "type": "Rủi ro cao: cột này nằm trong điều kiện lọc — đổi kiểu có thể làm phép so sánh trong WHERE sai kiểu hoặc đổi kết quả lọc, thay đổi số hàng bảng đích mà không cột nào báo.",
        "value": "Rủi ro trung bình: cột này quyết định hàng nào được giữ lại (WHERE/HAVING) — đổi giá trị làm tập hàng bảng đích thay đổi, sai số liệu downstream mà không có tín hiệu ở cấp cột.",
        "drop_table": "Rủi ro nghiêm trọng: bảng này cấp cột lọc (WHERE/HAVING) cho model đích — xoá cả bảng làm model đích LỖI BIÊN DỊCH ngay và mất toàn bộ điều kiện lọc, tập hàng thay đổi hoàn toàn.",
        "rename_table": "Rủi ro cao: bảng này cấp cột lọc (WHERE/HAVING) cho model đích — đổi tên cả bảng làm model đích không còn tìm thấy nguồn để lọc, phải cập nhật SQL/ref đồng thời.",
        "add_column": "Rủi ro thấp: thêm cột mới vào bảng nguồn không ảnh hưởng vai trò lọc (WHERE/HAVING) của cột này ở model đích.",
        "constraint": "Rủi ro trung bình: NOT NULL/PRIMARY KEY/FOREIGN KEY mới không đổi logic lọc, nhưng NOT NULL có thể chặn ghi dữ liệu nguồn hiện có; đổi partition/clustering key có thể đổi hiệu năng truy vấn ở model đích.",
    },
    "join_key": {
        "drop": "Rủi ro nghiêm trọng: cột này là khoá JOIN nối bảng đích với bảng khác — xoá làm phép JOIN vỡ, model đích lỗi biên dịch ngay.",
        "rename": "Rủi ro cao: cột này là khoá JOIN — đổi tên làm điều kiện ON không còn tìm thấy cột, phải cập nhật SQL đồng thời.",
        "type": "Rủi ro cao: cột này là khoá JOIN — đổi kiểu làm join không còn khớp kiểu, mất/thừa hàng ở kết quả.",
        "value": "Rủi ro trung bình: cột này là khoá JOIN — đổi giá trị làm tập hàng match thay đổi, ảnh hưởng số liệu ở bảng đích.",
        "drop_table": "Rủi ro nghiêm trọng: bảng này là một vế của phép JOIN ở model đích — xoá cả bảng làm phép JOIN vỡ, model đích lỗi biên dịch ngay và mất toàn bộ hàng phụ thuộc join này.",
        "rename_table": "Rủi ro cao: bảng này là một vế của phép JOIN ở model đích — đổi tên cả bảng làm điều kiện JOIN không còn tìm thấy nguồn, phải cập nhật SQL/ref đồng thời.",
        "add_column": "Rủi ro thấp: thêm cột mới vào bảng nguồn không ảnh hưởng khoá JOIN hiện có ở cạnh này.",
        "constraint": "Rủi ro cao: cột này là khoá JOIN — thêm/bỏ NOT NULL hoặc UNIQUE, đổi PRIMARY KEY/FOREIGN KEY làm đổi lực lượng (cardinality) phép JOIN hoặc mất ràng buộc tham chiếu, ảnh hưởng trực tiếp tính đúng đắn của join ở model đích.",
    },
    "group_key": {
        "drop": "Rủi ro nghiêm trọng: cột này nằm trong GROUP BY của bảng đích — xoá làm model đích lỗi biên dịch và mất chiều gom nhóm.",
        "rename": "Rủi ro cao: cột này nằm trong GROUP BY — đổi tên làm model đích lỗi vì không còn tìm thấy cột.",
        "type": "Rủi ro trung bình: cột này nằm trong GROUP BY — đổi kiểu có thể đổi cách gom nhóm (số nhóm), làm toàn bộ số liệu tổng hợp downstream lệch.",
        "value": "Rủi ro trung bình: cột này quyết định độ mịn gom nhóm (GROUP BY) — đổi giá trị làm số nhóm và số liệu tổng hợp thay đổi.",
        "drop_table": "Rủi ro nghiêm trọng: bảng này cấp cột GROUP BY cho model đích — xoá cả bảng làm model đích lỗi biên dịch và mất hoàn toàn chiều gom nhóm.",
        "rename_table": "Rủi ro cao: bảng này cấp cột GROUP BY cho model đích — đổi tên cả bảng làm model đích không còn tìm thấy nguồn, phải cập nhật SQL/ref đồng thời.",
        "add_column": "Rủi ro thấp: thêm cột mới vào bảng nguồn không ảnh hưởng cột GROUP BY hiện có ở cạnh này.",
        "constraint": "Rủi ro trung bình: đổi constraint không đổi logic gom nhóm, nhưng NOT NULL mới có thể chặn ghi dữ liệu nguồn hiện có; đổi partition/clustering key đổi hiệu năng truy vấn tổng hợp ở model đích.",
    },
}
_RISK_BY_DEPENDENCY["window_partition"] = {
    "drop": "Rủi ro nghiêm trọng: cột này nằm trong PARTITION BY của window function — xoá làm model đích lỗi biên dịch.",
    "rename": "Rủi ro cao: cột này nằm trong PARTITION BY — đổi tên làm model đích lỗi vì không tìm thấy cột.",
    "type": "Rủi ro trung bình: cột này chia khung tính toán (PARTITION BY) — đổi kiểu có thể đổi cách chia khung, làm kết quả ROW_NUMBER/RANK/SUM OVER... tính lại khác.",
    "value": "Rủi ro trung bình: cột này chia khung window — đổi giá trị làm các khung khác đi, kết quả window lệch.",
    "drop_table": "Rủi ro nghiêm trọng: bảng này cấp cột PARTITION BY cho window function ở model đích — xoá cả bảng làm model đích lỗi biên dịch.",
    "rename_table": "Rủi ro cao: bảng này cấp cột PARTITION BY cho window function — đổi tên cả bảng làm model đích không còn tìm thấy nguồn, phải cập nhật SQL/ref đồng thời.",
    "add_column": "Rủi ro thấp: thêm cột mới vào bảng nguồn không ảnh hưởng cột PARTITION BY hiện có ở cạnh này.",
    "constraint": "Rủi ro thấp: đổi constraint không đổi cách chia khung window; chỉ NOT NULL mới có thể chặn ghi dữ liệu nguồn hiện có.",
}
_RISK_BY_DEPENDENCY["window_order"] = {
    "drop": "Rủi ro nghiêm trọng: cột này nằm trong ORDER BY của window function — xoá làm model đích lỗi biên dịch.",
    "rename": "Rủi ro cao: cột này nằm trong ORDER BY của window — đổi tên làm model đích lỗi vì không tìm thấy cột.",
    "type": "Rủi ro trung bình: cột này quyết định thứ tự trong khung window — đổi kiểu có thể đảo thứ tự sắp xếp, làm ROW_NUMBER/LAG/LEAD... trả kết quả khác.",
    "value": "Rủi ro trung bình: cột này quyết định thứ tự trong khung window (ORDER BY) — đổi giá trị làm đảo thứ tự, lệch kết quả window và bộ lọc downstream dựa vào đó.",
    "drop_table": "Rủi ro nghiêm trọng: bảng này cấp cột ORDER BY cho window function ở model đích — xoá cả bảng làm model đích lỗi biên dịch.",
    "rename_table": "Rủi ro cao: bảng này cấp cột ORDER BY cho window function — đổi tên cả bảng làm model đích không còn tìm thấy nguồn, phải cập nhật SQL/ref đồng thời.",
    "add_column": "Rủi ro thấp: thêm cột mới vào bảng nguồn không ảnh hưởng cột ORDER BY của window hiện có ở cạnh này.",
    "constraint": "Rủi ro thấp: đổi constraint không đổi thứ tự trong khung window; chỉ NOT NULL mới có thể chặn ghi dữ liệu nguồn hiện có.",
}


# Ô trống trong bảng luật -> câu an toàn, KHÔNG bịa mức rủi ro. Thêm 1
# change_kind / dependency_kind mới KHÔNG bắt buộc điền lại 2 bảng trên — tổ
# hợp chưa có luật rơi về đây (xem ghi chú "phạm vi" cuối file).
_RISK_FALLBACK = (
    "Chưa có luật rủi ro riêng cho tổ hợp này — cần đánh giá thủ công tác động lên cạnh này."
)


def risk_note(transform_type: str, change_kind: ChangeKind, dependency_kind: str = "output") -> str:
    """Câu rủi ro cho 1 cạnh, tra bảng luật; ô trống -> _RISK_FALLBACK."""
    if dependency_kind != "output":
        by_dep = _RISK_BY_DEPENDENCY.get(dependency_kind, {})
        if change_kind in by_dep:
            return by_dep[change_kind]
    by_tf = _RISK_BY_TRANSFORM.get(transform_type) or _RISK_BY_TRANSFORM["unknown"]
    return by_tf.get(change_kind, _RISK_FALLBACK)


# ------------------------------------------------------------------------------
# Chủ đề 3: risk note NHẬN BIẾT kiểu + constraint hiện tại của cột đang đổi.
# risk_note() ở trên chỉ biết transform_type/dependency_kind của TỪNG cạnh —
# không biết cột `patient_id` vốn đã NOT NULL, hay đã là PK, hay kiểu gì. Khi
# graph có schema cột (từ DDL nguồn hoặc propagate), thêm 1 câu dẫn ĐẦU nói rõ
# tình trạng hiện tại + hệ quả cụ thể, ghép trước note theo-cạnh.
# ------------------------------------------------------------------------------

_TYPE_FAMILY: dict[str, str] = {
    "INT": "integer", "INTEGER": "integer", "BIGINT": "integer", "SMALLINT": "integer",
    "TINYINT": "integer", "INT2": "integer", "INT4": "integer", "INT8": "integer", "SERIAL": "integer",
    "NUMERIC": "decimal", "DECIMAL": "decimal", "REAL": "decimal", "DOUBLE": "decimal",
    "FLOAT": "decimal", "DOUBLE PRECISION": "decimal", "MONEY": "decimal",
    "TEXT": "text", "VARCHAR": "text", "CHAR": "text", "NVARCHAR": "text", "STRING": "text",
    "CHARACTER VARYING": "text", "CHARACTER": "text",
    "DATE": "temporal", "TIMESTAMP": "temporal", "DATETIME": "temporal", "TIME": "temporal",
    "TIMESTAMPTZ": "temporal", "TIMESTAMP WITH TIME ZONE": "temporal",
    "BOOLEAN": "boolean", "BOOL": "boolean",
}
_INT_WIDTH = {"TINYINT": 1, "SMALLINT": 2, "INT2": 2, "INT": 4, "INTEGER": 4, "INT4": 4, "BIGINT": 8, "INT8": 8}


def _norm_type(raw: str) -> str:
    return raw.split("(")[0].strip().upper()


def _type_transition_verdict(current: str, target: str) -> str:
    cur_n, tgt_n = _norm_type(current), _norm_type(target)
    if cur_n == tgt_n:
        return (
            "cùng kiểu cơ bản, chỉ đổi tham số (độ dài/độ chính xác) — rủi ro thấp, "
            "chỉ cần rà downstream có hard-code độ rộng cột không"
        )
    fam_c, fam_t = _TYPE_FAMILY.get(cur_n), _TYPE_FAMILY.get(tgt_n)
    if fam_c is None or fam_t is None:
        return "không nhận dạng được 1 trong 2 kiểu — cần kiểm tra thủ công mức tương thích"
    if fam_c == fam_t == "integer":
        if _INT_WIDTH.get(tgt_n, 0) >= _INT_WIDTH.get(cur_n, 0):
            return "mở rộng trong họ số nguyên — tương thích, chỉ cần downstream không hard-code độ rộng"
        return "THU HẸP số nguyên — rủi ro CAO: giá trị lớn hiện có sẽ tràn/lỗi"
    if fam_c == "integer" and fam_t == "decimal":
        return "mở rộng số nguyên -> thập phân — thường an toàn; downstream mong số nguyên cần rà"
    if fam_c == "decimal" and fam_t == "integer":
        return "THU HẸP thập phân -> nguyên — rủi ro CAO: mất phần lẻ, có thể tràn"
    if fam_c == fam_t == "decimal":
        return "cùng họ số thực — rà lại độ chính xác (precision/scale) ở downstream"
    if fam_c == fam_t == "text":
        return "cùng họ chuỗi — rà độ dài tối đa và padding (CHAR vs VARCHAR)"
    return (
        f"ĐỔI HỌ KIỂU ({fam_c} -> {fam_t}) — rủi ro NGHIÊM TRỌNG: mọi phép toán/so sánh/JOIN "
        "theo cột này ở downstream có thể vỡ kiểu"
    )


def _describe_column(col: dict) -> str:
    """Liệt kê SỰ THẬT về cột — KHÔNG phán mức rủi ro. Người đọc tự suy ra hệ
    quả từ sự thật ('PRIMARY KEY' ⇒ thêm NOT NULL là no-op), tránh việc phải
    viết 1 câu verdict riêng cho từng tổ hợp (kiểu × constraint × vai trò)."""
    name = col.get("name") or "cột"
    dt = col.get("data_type") or "?"
    if col.get("origin") == "propagated":
        return (
            f"Cột `{name}`: kiểu suy diễn `{dt}` (không có DDL khai báo — chưa rõ ràng buộc "
            "NULL/khoá, cần xác minh)."
        )
    parts = [f"kiểu `{dt}`"]
    if col.get("is_primary_key"):
        parts.append("PRIMARY KEY (ngầm NOT NULL)")
    elif not col.get("is_nullable", True):
        parts.append("NOT NULL")
    else:
        parts.append("cho phép NULL")
    if col.get("is_foreign_key"):
        ref = col.get("references_table")
        parts.append(f"FOREIGN KEY → {ref}" if ref else "FOREIGN KEY")
    return f"Cột `{name}`: " + ", ".join(parts) + "."


def schema_change_note(
    col: dict | None,
    change_kind: ChangeKind,
    target_type: str | None = None,
    join_key_count: int = 0,
) -> str | None:
    """1 câu SỰ THẬT về cột đang đổi + (khi TÍNH ĐƯỢC) 1 hệ quả cụ thể.

    Không phán mức rủi ro tổng quát — đó là việc của risk_note() theo-cạnh. Chỉ
    thêm hệ quả khi có gì đó cụ thể và đáng giá: đổi kiểu + có kiểu đích
    (transition verdict), hoặc thêm NOT NULL vào cột đang nullable (backfill).
    Còn lại: chỉ sự thật, để người đọc + risk_note theo-cạnh lo phần đánh giá.

    None khi không có schema hoặc change_kind không liên quan schema.
    """
    if col is None or change_kind in ("value", "rename", "rename_table", "add_column"):
        return None
    facts = _describe_column(col)
    declared = col.get("origin") != "propagated"
    consequence: str | None = None

    if change_kind == "type" and target_type and col.get("data_type"):
        v = _type_transition_verdict(col["data_type"], target_type)
        consequence = v[:1].upper() + v[1:] + "."
    elif (
        change_kind == "constraint"
        and declared
        and col.get("is_nullable", True)
        and not col.get("is_primary_key")
    ):
        consequence = "Thêm NOT NULL/UNIQUE cần backfill + kiểm dữ liệu hiện có trước."
        if join_key_count:
            consequence += f" {join_key_count} model downstream JOIN trên cột này (NULL bị loại khỏi JOIN)."

    return f"{facts} {consequence}" if consequence else facts


# ------------------------------------------------------------------------------
# PHẠM VI (chốt 2026-08-31, sau khi code chấm rủi ro phình combinatorial):
# - `_RISK_BY_TRANSFORM` / `_RISK_BY_DEPENDENCY` ĐÔNG CỨNG ở mức hiện tại. KHÔNG
#   mở rộng thêm luật mịn. Thêm `change_kind` / `dependency_kind` / `transform_type`
#   mới -> KHÔNG bắt buộc điền lại 2 bảng; ô trống rơi về `_RISK_FALLBACK`
#   ("cần đánh giá thủ công") — đó là hành vi ĐÚNG, không phải thiếu sót.
# - `schema_change_note` theo hướng SỰ THẬT: `_describe_column` liệt kê cái biết
#   chắc, chỉ thêm 1 `consequence` khi TÍNH ĐƯỢC điều cụ thể (transition kiểu,
#   backfill NOT NULL). Không viết verdict cho từng tổ hợp.
# - Verdict rủi ro là LỜI KHUYÊN cho người sẽ tự kiểm tra, không phải phán quyết.
#   Nếu cần trường hợp mới: ưu tiên (a) rơi vào nhóm thô có sẵn, (b) để fallback
#   lo, (c) chỉ code riêng khi có người dùng thật đang vướng.
# ------------------------------------------------------------------------------


def _matching_pending_edges_with_hops(
    database_id: int, table: str, column: str | None, direction: Literal["downstream", "upstream"], reached_tables: dict[str, int]
) -> list[tuple[LineageEdge, int]]:
    """Như _matching_pending_edges, kèm hops (hop của cạnh pending = hop của bảng neo + 1)."""
    downstream = direction == "downstream"
    matches: list[tuple[LineageEdge, int]] = []
    for edge in review_service.list_pending(database_id):
        anchor_table = edge.source_table if downstream else edge.target_table
        anchor_column = edge.source_column if downstream else edge.target_column
        if anchor_table == table:
            if column is None or anchor_column in (None, column):
                matches.append((edge, 1))
        elif anchor_table in reached_tables:
            matches.append((edge, reached_tables[anchor_table] + 1))
    return matches


def query_impact_edges(
    database_id: int,
    table: str,
    column: str | None,
    direction: Literal["downstream", "upstream"],
    depth: int | None = None,
) -> tuple[list[LineageEdge], list[LineageEdge]]:
    """Collect confirmed and pending edges for both impact consumers."""
    downstream = direction == "downstream"
    confirmed_with_hops = (
        graph_service.get_downstream_with_hops(database_id, table, column, depth)
        if direction == "downstream"
        else graph_service.get_upstream_with_hops(database_id, table, column, depth)
    )
    reached_tables: dict[str, int] = {table: 0}
    for edge, hops in confirmed_with_hops:
        neighbor = edge.target_table if downstream else edge.source_table
        if neighbor not in reached_tables or hops < reached_tables[neighbor]:
            reached_tables[neighbor] = hops
    pending_with_hops = _matching_pending_edges_with_hops(database_id, table, column, direction, reached_tables)
    if depth is not None:
        pending_with_hops = [(edge, hops) for edge, hops in pending_with_hops if hops <= depth]
    return [edge for edge, _ in confirmed_with_hops], [edge for edge, _ in pending_with_hops]


def query_impact(
    database_id: int,
    table: str,
    column: str | None,
    direction: Literal["downstream", "upstream"],
    change_kind: ChangeKind | None = None,
    target_type: str | None = None,
) -> ImpactQueryResult:
    """Build the public impact response from the shared raw edge query.

    change_kind (tuỳ chọn): "type" (đổi kiểu dữ liệu cột) hoặc "value" (đổi
    giá trị) — khi có, mỗi cạnh trả về kèm risk note tính theo transform_type
    của chính cạnh đó, xem risk_note()/_RISK_BY_TRANSFORM ở trên.

    Mỗi cạnh trả về kèm `hops` (hop 1 = xuất phát trực tiếp từ `table`) —
    dùng cho FE nhóm sub-graph impact theo từng tầng thay vì 1 danh sách phẳng.
    """
    downstream = direction == "downstream"
    confirmed_edges = (
        graph_service.get_downstream_with_hops(database_id, table, column)
        if downstream
        else graph_service.get_upstream_with_hops(database_id, table, column)
    )

    # Chủ đề 3: schema hiện tại của cột đang đổi (`table`.`column`) — 1 câu dẫn
    # đầu chung cho MỌI cạnh, ghép trước note theo-cạnh. Chỉ tra DB khi thật sự
    # cần (có change_kind liên quan schema + có tên cột). Schema là làm giàu TÙY
    # CHỌN — DB lỗi/bảng chưa có thì impact vẫn chạy với note tĩnh (không hard-fail).
    changed_col: dict | None = None
    if change_kind and column and change_kind not in ("value", "rename", "rename_table", "add_column"):
        try:
            by_table = storage_service.load_column_schema_by_names(database_id, [table])
            changed_col = next((c for c in by_table.get(table, []) if c.get("name") == column), None)
        except Exception:  # noqa: BLE001 — schema chỉ là enrichment, không được làm vỡ impact
            changed_col = None
    reached_tables: dict[str, int] = {table: 0}
    for edge, hops in confirmed_edges:
        neighbor = edge.target_table if downstream else edge.source_table
        if neighbor not in reached_tables or hops < reached_tables[neighbor]:
            reached_tables[neighbor] = hops
    pending_edges = _matching_pending_edges_with_hops(database_id, table, column, direction, reached_tables)

    join_key_count = sum(
        1 for edge, _ in confirmed_edges if edge.dependency_kind == "join_key"
    )
    schema_prefix = (
        schema_change_note(changed_col, change_kind, target_type, join_key_count) if change_kind else None
    )

    def to_view(edge: LineageEdge, hops: int, hitl_status: Literal["confirmed", "pending"]) -> ImpactEdgeView:
        risk = None
        if change_kind:
            risk = risk_note(edge.transform_type, change_kind, edge.dependency_kind)
            if schema_prefix:
                risk = f"{schema_prefix} — {risk}"
        return ImpactEdgeView.from_edge(
            edge,
            hitl_status=hitl_status,
            risk=risk,
            schema_note=schema_prefix if change_kind else None,
            hops=hops,
        )

    return ImpactQueryResult(
        table=table,
        column=column,
        direction=direction,
        confirmed=[to_view(edge, hops, "confirmed") for edge, hops in confirmed_edges],
        inferred_pending=[to_view(edge, hops, "pending") for edge, hops in pending_edges],
    )
