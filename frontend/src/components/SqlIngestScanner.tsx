import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useIngest } from '../hooks/useIngest';
import { listIngestRuns } from '../api/ingest';
import type { Database } from '../api/database';
import type { IngestRun } from '../types/backend';
import {
  Database as DatabaseIcon,
  Upload,
  Check,
  FileCheck,
  FileText,
  Folder,
  Trash2,
  ArrowRight,
  Network,
  Columns,
  RefreshCw,
  Layers,
  Code2,
  Sparkles,
  CheckCircle2,
  Plus,
  History,
  X
} from 'lucide-react';

interface SqlIngestScannerProps {
  // Chỉ là tín hiệu "ingest xong, reload lại dữ liệu thật" — không còn nhận
  // node/edge giả nữa (trước đây UI tự bịa lineage từ string-matching thay
  // vì đọc kết quả ingest thật).
  onIngestSuccess: () => void;
  onNavigateToGraph?: () => void;
  canIngest?: boolean;
  databases: Database[];
  selectedDatabaseId: number | null;
  onSelectDatabase: (database: Database) => void;
  onCreateDatabase: (name: string) => Promise<void>;
}

const sampleSnippets = {
  stagingModel: {
    name: 'stg_subscription_invoices.sql',
    schema: 'staging',
    description: 'Chuyển đổi bảng raw payments từ cổng thanh toán Stripe thành bảng staging hoá đơn.',
    sql: `/* dbt Staging Model: stg_subscription_invoices.sql */
WITH source AS (
  SELECT * FROM {{ source('source_raw', 'raw_stripe_payments') }}
),
invoices AS (
  SELECT
    charge_id AS invoice_id,
    order_id,
    amount_cents / 100.0 AS invoice_amount_usd,
    payment_status,
    captured_at AS invoice_date
  FROM source
  WHERE payment_status = 'succeeded'
)
SELECT * FROM invoices`
  },
  intermediateModel: {
    name: 'int_dynamic_campaign_attribution.sql',
    schema: 'intermediate',
    description: 'Kết hợp dữ liệu đơn hàng (stg_orders) và chi phí quảng cáo (stg_ad_spend) để tính attribution.',
    sql: `/* dbt Intermediate: int_dynamic_campaign_attribution.sql */
{% set channels = ['google_ads', 'facebook_ads', 'tiktok_ads', 'email_campaign'] %}

WITH orders AS (
  SELECT * FROM {{ ref('stg_orders') }}
),
ad_touchpoints AS (
  SELECT * FROM {{ ref('stg_ad_spend') }}
)
SELECT
  o.order_id,
  o.customer_id,
  o.order_total_usd,
  {% for channel in channels %}
    MAX(CASE WHEN a.campaign_id LIKE '%{{ channel }}%' THEN a.spend_usd ELSE 0 END) AS {{ channel }}_weight,
  {% endfor %}
  o.order_created_at
FROM orders o
LEFT JOIN ad_touchpoints a ON o.order_created_at >= a.ad_date
GROUP BY 1, 2, 3, o.order_created_at`
  },
  storedProcedure: {
    name: 'sp_daily_reconciliation.sql',
    schema: 'analytics_marts',
    description: 'Stored Procedure tổng hợp doanh thu từ raw Shopify sang bảng báo cáo fct_daily_sales_revenue.',
    sql: `/* Stored Procedure: sp_daily_reconciliation.sql */
CREATE PROCEDURE sp_daily_reconciliation(IN v_period VARCHAR(10))
BEGIN
  SET @source_table = CONCAT('source_raw.raw_shopify_orders_', v_period);
  SET @target_mart = 'analytics_marts.fct_daily_sales_revenue';
  
  SET @dyn_query = CONCAT(
    'INSERT INTO ', @target_mart, ' (gross_revenue_usd) ',
    'SELECT SUM(total_amount) FROM ', @source_table, ' WHERE status = "settled"'
  );
  
  PREPARE stmt FROM @dyn_query;
  EXECUTE stmt;
  DEALLOCATE PREPARE stmt;
END;`
  }
};

export const SqlIngestScanner: React.FC<SqlIngestScannerProps> = ({
  onIngestSuccess,
  onNavigateToGraph,
  canIngest = true,
  databases,
  selectedDatabaseId,
  onSelectDatabase,
  onCreateDatabase,
}) => {
  const { runUpload, loading: isConverting, error: ingestError, result: ingestResult } = useIngest();

  // Lịch sử ingest của dự án đang chọn — audit "đã ingest gì, từ path nào,
  // khi nào" vì 1 project có thể ingest nhiều lần từ nhiều thư mục khác nhau.
  const [ingestRuns, setIngestRuns] = useState<IngestRun[]>([]);
  const refreshIngestRuns = useCallback(() => {
    if (!selectedDatabaseId) { setIngestRuns([]); return; }
    listIngestRuns(selectedDatabaseId).then(setIngestRuns).catch(() => setIngestRuns([]));
  }, [selectedDatabaseId]);
  useEffect(() => { refreshIngestRuns(); }, [refreshIngestRuns]);

  // Tạo/chuyển dự án nhanh ngay tại trang Ingest — trước đây phải rời hẳn
  // sang Workspace Hub mới tạo được database mới.
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [creatingProjectBusy, setCreatingProjectBusy] = useState(false);
  const currentDatabase = databases.find(d => d.id === selectedDatabaseId);

  const handleCreateProject = async () => {
    const name = newProjectName.trim();
    if (!name) return;
    setCreatingProjectBusy(true);
    try {
      await onCreateDatabase(name);
      setNewProjectName('');
      setIsCreatingProject(false);
    } finally {
      setCreatingProjectBusy(false);
    }
  };
  const [inputMethod, setInputMethod] = useState<'upload' | 'paste'>('upload');
  const [pasteSqlCode, setPasteSqlCode] = useState(sampleSnippets.stagingModel.sql);
  const [conversionSuccess, setConversionSuccess] = useState(false);

  // Uploaded files state
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ 
    name: string; 
    size: number; 
    content: string; 
    path?: string;
    schema: string;
    tableName: string;
  }>>([]);
  const [isDragging, setIsDragging] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const determineSchemaAndTable = (fileName: string, path: string = '') => {
    let schema = 'staging';
    if (path.includes('intermediate') || fileName.startsWith('int_')) {
      schema = 'intermediate';
    } else if (path.includes('marts') || fileName.startsWith('fct_') || fileName.startsWith('dim_') || fileName.startsWith('mart_')) {
      schema = 'analytics_marts';
    } else if (path.includes('source') || fileName.startsWith('raw_') || fileName.startsWith('src_')) {
      schema = 'source_raw';
    }
    const tableName = fileName.replace(/\.(sql|jinja|dbt)$/i, '');
    return { schema, tableName };
  };

  const processFiles = (files: FileList | File[]) => {
    const fileArray = Array.from(files).filter(f => 
      f.name.endsWith('.sql') || f.name.endsWith('.dbt') || f.name.endsWith('.jinja') || f.name.endsWith('.sql.jinja') || f.name.includes('.')
    );

    if (fileArray.length === 0) {
      alert('Vui lòng chọn hoặc kéo thả các tệp định dạng .sql, .sql.jinja hoặc .dbt!');
      return;
    }

    const readers: Promise<{ name: string; size: number; content: string; path?: string; schema: string; tableName: string }>[] = fileArray.map(file => {
      return new Promise((resolve) => {
        const reader = new FileReader();
        const path = (file as any).webkitRelativePath || file.name;
        const { schema, tableName } = determineSchemaAndTable(file.name, path);
        reader.onload = (e) => {
          resolve({
            name: file.name,
            size: file.size,
            content: (e.target?.result as string) || '',
            path,
            schema,
            tableName
          });
        };
        reader.readAsText(file);
      });
    });

    Promise.all(readers).then(results => {
      setUploadedFiles(prev => [...prev, ...results]);
      setConversionSuccess(false);
    });
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFiles(e.dataTransfer.files);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(e.target.files);
    }
  };

  const handleRemoveFile = (index: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setUploadedFiles(prev => prev.filter((_, i) => i !== index));
    setConversionSuccess(false);
  };

  const handleClearAllFiles = () => {
    setUploadedFiles([]);
    setConversionSuccess(false);
  };

  // Convert single SQL script or batch of uploaded files
  const handleConvertFilesToLineage = async () => {
    const filesToProcess = inputMethod === 'upload' 
      ? uploadedFiles 
      : [{
          name: 'pasted_model.sql',
          size: pasteSqlCode.length,
          content: pasteSqlCode,
          schema: 'staging',
          tableName: 'stg_subscription_invoices'
        }];

    if (filesToProcess.length === 0) {
      alert('Vui lòng tải lên ít nhất một file .sql hoặc dán mã SQL để chuyển đổi!');
      return;
    }

    setConversionSuccess(false);

    try {
      // Giữ nguyên f.path (webkitRelativePath khi chọn cả folder) làm tên
      // file gửi lên — trước đây dùng f.name (chỉ tên file trần) làm mất cấu
      // trúc thư mục, khiến evidence.file_path cụt và backend không suy luận
      // được project từ thư mục gốc chung của các file.
      const files: File[] = filesToProcess.map(
        f => new File([f.content], f.path || f.name, { type: 'text/plain' })
      );

      // runUpload trả thẳng IngestResponse thật (POST /api/v1/ingest/upload) —
      // KHÔNG tự suy luận/bịa lineage ở client nữa. overview_graph là bức
      // tranh table-level của ĐÚNG lượt ingest này (không phải toàn bộ đồ thị
      // tích luỹ — xem docstring backend _overview_graph()).
      const response = await runUpload(files);
      if (!response) {
        throw new Error(ingestError || 'Ingestion failed on backend');
      }

      onIngestSuccess();
      setConversionSuccess(true);
      refreshIngestRuns();

    } catch (err: any) {
      alert(`Lỗi trong quá trình chuyển đổi: ${err.message || err}`);
    }
  };

  return (
    <div className="w-full max-w-7xl mx-auto p-4 sm:p-6 space-y-6">
      {/* Hidden File Inputs */}
      <input
        type="file"
        ref={fileInputRef}
        accept=".sql,.sql.jinja,.dbt,.txt"
        multiple
        onChange={handleFileChange}
        className="hidden"
      />
      <input
        type="file"
        ref={folderInputRef}
        {...({ webkitdirectory: '', directory: '' } as any)}
        multiple
        onChange={handleFileChange}
        className="hidden"
      />

      {/* Main Header: Clearly state this tab converts Database/SQL into Lineage */}
      <div className="bg-gradient-to-r from-indigo-50 via-slate-50 to-indigo-50 dark:from-slate-900 dark:via-indigo-950 dark:to-slate-900 border border-indigo-100 dark:border-slate-800 rounded-3xl p-6 sm:p-8 text-slate-900 dark:text-white shadow-xl flex flex-col lg:flex-row lg:items-center justify-between gap-6 transition-all duration-300">
        <div className="space-y-2 max-w-3xl">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-indigo-100 dark:bg-indigo-500/20 text-indigo-755 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-500/30">
              <DatabaseIcon className="w-5 h-5" />
            </span>
            <span className="text-[11px] font-semibold text-indigo-700 dark:text-indigo-300 uppercase tracking-wider">
              Governance Hub &bull; Ingestion SQL Engine
            </span>
          </div>
          
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Database to Lineage Parser
          </h1>
          
          <p className="text-xs sm:text-sm text-slate-650 dark:text-slate-350 leading-relaxed font-medium">
            Nạp các file SQL / dbt model hoặc dán câu lệnh truy vấn để <strong className="text-indigo-600 dark:text-indigo-300 font-semibold">tự động chuyển đổi cơ sở dữ liệu thành sơ đồ Lineage DAG</strong> trực quan với đầy đủ quan hệ upstream, downstream và metadata.
          </p>
        </div>
      </div>

      {/* Ingest history — 1 dự án có thể ingest nhiều lần từ nhiều thư mục
          khác nhau (không phải mọi dữ liệu luôn nằm gọn trong 1 file/folder),
          nên cần xem lại được lượt nào, từ path nào, ra bao nhiêu cạnh. */}
      {ingestRuns.length > 0 && (
        <div className="bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
          <h3 className="font-bold text-xs text-slate-900 dark:text-white flex items-center gap-2 mb-3">
            <History className="w-3.5 h-3.5 text-slate-400" />
            <span>Lịch sử ingest của dự án này</span>
          </h3>
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {ingestRuns.map(run => (
              <div
                key={run.id}
                className="flex items-center justify-between gap-3 p-2 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 text-[11px] font-mono"
              >
                <span className="text-slate-700 dark:text-slate-300 truncate flex-1">{run.input_path}</span>
                <span className="text-slate-400 shrink-0">{run.sql_files_found} file &bull; {run.parsed_count} parser &bull; {run.pending_review_count} chờ duyệt</span>
                <span className="text-slate-400 shrink-0">{new Date(run.started_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main Container */}
      <div className="bg-white dark:bg-slate-900 p-5 sm:p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-6">
        {/* Navigation Tabs (Upload File vs. Paste SQL) */}
        <div className="flex items-center border-b border-slate-200 dark:border-slate-800">
          <button
            id="tab-upload-file"
            onClick={() => setInputMethod('upload')}
            className={`px-8 py-3 text-sm font-semibold transition-all relative cursor-pointer flex items-center gap-2 ${
              inputMethod === 'upload'
                ? 'text-[#4338ca] dark:text-indigo-400 font-bold'
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            <Upload className="w-4 h-4" />
            <span>Upload SQL Files &amp; Folders</span>
            {inputMethod === 'upload' && (
              <div className="absolute bottom-0 left-0 right-0 h-[2.5px] bg-[#4338ca] dark:bg-indigo-500 rounded-full" />
            )}
          </button>
          <button
            id="tab-paste-sql"
            onClick={() => setInputMethod('paste')}
            className={`px-8 py-3 text-sm font-semibold transition-all relative cursor-pointer flex items-center gap-2 ${
              inputMethod === 'paste'
                ? 'text-[#4338ca] dark:text-indigo-400 font-bold'
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            <Code2 className="w-4 h-4" />
            <span>Paste SQL Script</span>
            {inputMethod === 'paste' && (
              <div className="absolute bottom-0 left-0 right-0 h-[2.5px] bg-[#4338ca] dark:bg-indigo-500 rounded-full" />
            )}
          </button>
        </div>

        {/* MODE 1: Upload File & Folder */}
        {inputMethod === 'upload' && (
          <div className="space-y-6">
            {/* Drag & Drop Box */}
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center flex flex-col items-center justify-center transition-all ${
                isDragging
                  ? 'border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/40'
                  : 'border-slate-300 dark:border-slate-700 bg-slate-50/40 dark:bg-slate-900/40 hover:bg-slate-50 dark:hover:bg-slate-800/50'
              }`}
            >
              <div className="w-12 h-12 mb-4 rounded-2xl bg-white dark:bg-slate-800 flex items-center justify-center text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700 shadow-xs">
                <Upload className="w-6 h-6 stroke-[2]" />
              </div>

              <h3 className="text-base sm:text-lg font-bold text-slate-900 dark:text-slate-100">
                Drag and Drop SQL Files Here
              </h3>

              <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-1.5 mb-6 max-w-md">
                Hỗ trợ file đơn lẻ hoặc chọn toàn bộ thư mục dự án dbt / ETL để chuyển đổi hàng loạt sang Lineage
              </p>

              <div className="flex flex-wrap items-center justify-center gap-3">
                <button
                  type="button"
                  id="upload-single-file-btn"
                  onClick={() => fileInputRef.current?.click()}
                  className="px-6 py-2.5 bg-[#4338ca] hover:bg-[#3730a3] text-white rounded-xl text-xs sm:text-sm font-semibold flex items-center gap-2 shadow-md shadow-indigo-900/20 transition-all cursor-pointer"
                >
                  <FileText className="w-4 h-4" />
                  <span>Select .sql Files</span>
                </button>

                <button
                  type="button"
                  id="upload-folder-btn"
                  onClick={() => folderInputRef.current?.click()}
                  className="px-6 py-2.5 bg-[#4338ca] hover:bg-[#3730a3] text-white rounded-xl text-xs sm:text-sm font-semibold flex items-center gap-2 shadow-md shadow-indigo-900/20 transition-all cursor-pointer"
                >
                  <Folder className="w-4 h-4" />
                  <span>Select Folder</span>
                </button>
              </div>
            </div>

            {/* Uploaded Files Section */}
            {uploadedFiles.length > 0 && (
              <div className="p-5 rounded-3xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700/80 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200 dark:border-slate-700">
                  <div className="flex items-center gap-2 font-mono font-bold text-sm text-slate-800 dark:text-slate-100">
                    <FileCheck className="w-4 h-4 text-emerald-500" />
                    <span>Uploaded SQL Files ({uploadedFiles.length})</span>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleClearAllFiles}
                      className="px-3 py-1.5 rounded-lg text-xs text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors font-medium cursor-pointer"
                    >
                      Clear All
                    </button>
                    <button
                      id="convert-uploaded-btn"
                      onClick={handleConvertFilesToLineage}
                      disabled={isConverting || !canIngest}
                      className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold flex items-center gap-2 shadow-md shadow-indigo-600/25 cursor-pointer transition-all hover:scale-[1.02]"
                    >
                      {isConverting ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          <span>Converting to Lineage...</span>
                        </>
                      ) : (
                        <>
                          <Network className="w-3.5 h-3.5" />
                          <span>Convert {uploadedFiles.length} files to Lineage DAG</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* File Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 max-h-60 overflow-y-auto">
                  {uploadedFiles.map((file, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono flex items-center justify-between shadow-2xs"
                    >
                      <div className="flex items-center gap-2.5 truncate">
                        <FileText className="w-4 h-4 text-indigo-500 shrink-0" />
                        <div className="truncate">
                          <div className="font-semibold text-slate-800 dark:text-slate-200 truncate">
                            {file.name}
                          </div>
                          <div className="text-[10px] text-slate-400">
                            Layer: {file.schema} &bull; {(file.size / 1024).toFixed(1)} KB
                          </div>
                        </div>
                      </div>
                      <button
                        onClick={(e) => handleRemoveFile(idx, e)}
                        className="p-1.5 text-slate-400 hover:text-rose-500 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                        title="Xóa file này"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* MODE 2: Paste SQL Directly */}
        {inputMethod === 'paste' && (
          <div className="space-y-4">
            {/* Quick Sample Selector */}
            <div className="flex items-center justify-between flex-wrap gap-2">
              <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                Select Sample SQL Template or Paste Custom SQL Code
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPasteSqlCode(sampleSnippets.stagingModel.sql)}
                  className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-xs font-mono text-emerald-600 dark:text-emerald-400 cursor-pointer"
                >
                  Template 1: Staging
                </button>
                <button
                  onClick={() => setPasteSqlCode(sampleSnippets.intermediateModel.sql)}
                  className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-xs font-mono text-amber-600 dark:text-amber-400 cursor-pointer"
                >
                  Template 2: Jinja Join
                </button>
                <button
                  onClick={() => setPasteSqlCode(sampleSnippets.storedProcedure.sql)}
                  className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-xs font-mono text-indigo-600 dark:text-indigo-400 cursor-pointer"
                >
                  Template 3: Stored Procedure
                </button>
              </div>
            </div>

            {/* Textarea */}
            <textarea
              value={pasteSqlCode}
              onChange={(e) => setPasteSqlCode(e.target.value)}
              rows={10}
              placeholder="Dán câu lệnh SQL (SELECT ... FROM ...) hoặc dbt model tại đây..."
              className="w-full p-4 bg-slate-950 text-slate-100 font-mono text-xs rounded-2xl border border-slate-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none leading-relaxed resize-none shadow-inner"
            />

            {/* Convert Button */}
            <div className="flex justify-end">
              <button
                id="convert-paste-btn"
                onClick={handleConvertFilesToLineage}
                disabled={isConverting || !pasteSqlCode.trim() || !canIngest}
                className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold flex items-center gap-2 shadow-lg shadow-indigo-600/25 cursor-pointer transition-all hover:scale-[1.02]"
              >
                {isConverting ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Converting to Lineage...</span>
                  </>
                ) : (
                  <>
                    <Network className="w-4 h-4" />
                    <span>Convert to Lineage DAG</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Conversion Success Notification & Summary Card — số liệu thật từ
            IngestResponse (POST /api/v1/ingest/upload), không tự bịa nữa. */}
        {conversionSuccess && ingestResult && (
          <div className="p-5 rounded-3xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/80 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 animate-fadeIn">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-600 text-white flex items-center justify-center shrink-0 shadow-md shadow-emerald-600/20">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-emerald-900 dark:text-emerald-200">
                  Lineage Graph Converted Successfully!
                </h4>
                <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-0.5">
                  Đọc <strong>{ingestResult.sql_files_found} file .sql</strong> —{' '}
                  <strong>{ingestResult.parsed_count} cạnh parser</strong> (chắc chắn),{' '}
                  <strong>{ingestResult.unparsed_count} file</strong> phải qua LLM fallback,{' '}
                  <strong>{ingestResult.pending_review_count} cạnh</strong> đang chờ duyệt HITL.
                </p>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {ingestResult.overview_graph.nodes.map((n) => (
                    <span key={n.id} className="px-2 py-0.5 rounded-md bg-emerald-100 dark:bg-emerald-900/60 text-emerald-800 dark:text-emerald-300 font-mono text-[11px] border border-emerald-200 dark:border-emerald-700">
                      {n.label}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {onNavigateToGraph && (
              <button
                id="success-view-lineage-btn"
                onClick={onNavigateToGraph}
                className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold flex items-center gap-2 shadow-lg shadow-emerald-600/25 cursor-pointer transition-all hover:scale-[1.03] shrink-0"
              >
                <Network className="w-4 h-4" />
                <span>View on Lineage DAG</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
