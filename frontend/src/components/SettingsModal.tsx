import React, { useState, useEffect } from 'react';
import { 
  X, 
  Settings, 
  Cpu, 
  Layout, 
  Sliders, 
  Moon, 
  Sun, 
  RotateCcw, 
  Check, 
  Sparkles,
  ShieldAlert,
  Database,
  Network
} from 'lucide-react';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  darkMode: boolean;
  setDarkMode: (val: boolean) => void;
  layoutDirection: 'LR' | 'TB';
  setLayoutDirection: (val: 'LR' | 'TB') => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  darkMode,
  setDarkMode,
  layoutDirection,
  setLayoutDirection
}) => {
  const [localDarkMode, setLocalDarkMode] = useState<boolean>(darkMode);
  const [localLayoutDirection, setLocalLayoutDirection] = useState<'LR' | 'TB'>(layoutDirection);
  const [confidenceThreshold, setConfidenceThreshold] = useState<number>(0.80);
  const [enableLLMFallback, setEnableLLMFallback] = useState<boolean>(true);
  const [enableCLLAnimations, setEnableCLLAnimations] = useState<boolean>(true);
  const [edgeStyle, setEdgeStyle] = useState<'smoothstep' | 'bezier'>('smoothstep');
  const [isSaved, setIsSaved] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setLocalDarkMode(darkMode);
      setLocalLayoutDirection(layoutDirection);
    }
  }, [isOpen, darkMode, layoutDirection]);

  if (!isOpen) return null;

  const handleSave = () => {
    setDarkMode(localDarkMode);
    setLayoutDirection(localLayoutDirection);
    setIsSaved(true);
    setTimeout(() => {
      setIsSaved(false);
      onClose();
    }, 600);
  };

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div 
        className="w-full max-w-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col font-sans"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-4 sm:p-5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-slate-800/40">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-50 dark:bg-indigo-950/80 text-indigo-600 dark:text-indigo-400 flex items-center justify-center border border-indigo-200 dark:border-indigo-800">
              <Settings className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold font-mono text-slate-900 dark:text-white">
                Lineage System Settings
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Cấu hình công cụ phân tích cú pháp AST, ngưỡng phê duyệt thủ công HITL và giao diện đồ thị
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 sm:p-6 overflow-y-auto max-h-[70vh] space-y-6 text-xs text-slate-700 dark:text-slate-300">
          {/* Section 1: Ingestion & Parser Engine */}
          <div>
            <div className="flex items-center gap-2 mb-3 text-slate-900 dark:text-white font-mono font-bold">
              <Cpu className="w-4 h-4 text-indigo-500" />
              <span>Parser Engine &amp; AI Fallback</span>
            </div>
            
            <div className="space-y-3 bg-slate-50 dark:bg-slate-800/40 p-4 rounded-xl border border-slate-200 dark:border-slate-800">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold text-slate-900 dark:text-slate-100">
                    Kích hoạt suy diễn AI Fallback (Gemini / GPT-4o-mini)
                  </div>
                  <div className="text-[11px] text-slate-500 dark:text-slate-400">
                    Tự động suy diễn quan hệ lineage khi gặp SQL động hoặc Jinja macro phức tạp
                  </div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={enableLLMFallback}
                    onChange={(e) => setEnableLLMFallback(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-slate-300 peer-focus:outline-none rounded-full peer dark:bg-slate-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600"></div>
                </label>
              </div>

              <div className="pt-3 border-t border-slate-200 dark:border-slate-700/60">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="font-semibold text-slate-900 dark:text-slate-100">
                    Ngưỡng tin cậy HITL
                  </div>
                  <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950 px-2 py-0.5 rounded border border-indigo-200 dark:border-indigo-800">
                    {(confidenceThreshold * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="text-[11px] text-slate-500 dark:text-slate-400 mb-2">
                  Các liên kết do AI suy diễn có độ tin cậy dưới ngưỡng này sẽ được đưa vào hàng đợi HITL để phê duyệt thủ công.
                </div>
                <input
                  type="range"
                  min="0.5"
                  max="0.95"
                  step="0.05"
                  value={confidenceThreshold}
                  onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
                  className="w-full h-1.5 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-indigo-600"
                />
              </div>
            </div>
          </div>

          {/* Section 2: Graph Visualization Preferences */}
          <div>
            <div className="flex items-center gap-2 mb-3 text-slate-900 dark:text-white font-mono font-bold">
              <Layout className="w-4 h-4 text-cyan-500" />
              <span>DAG Visualization Preferences</span>
            </div>

            <div className="space-y-3 bg-slate-50 dark:bg-slate-800/40 p-4 rounded-xl border border-slate-200 dark:border-slate-800">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold text-slate-900 dark:text-slate-100">
                    Hướng hiển thị sơ đồ DAG
                  </div>
                  <div className="text-[11px] text-slate-500 dark:text-slate-400">
                    Hiển thị biểu đồ lineage theo chiều ngang (Left-to-Right) hoặc chiều dọc (Top-to-Bottom)
                  </div>
                </div>
                <div className="flex items-center gap-1 bg-slate-200 dark:bg-slate-700 p-1 rounded-lg">
                  <button
                    onClick={() => setLocalLayoutDirection('LR')}
                    className={`px-2.5 py-1 rounded font-mono font-bold text-xs transition-colors cursor-pointer ${
                      localLayoutDirection === 'LR' 
                        ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-sm' 
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                    }`}
                  >
                    Left → Right
                  </button>
                  <button
                    onClick={() => setLocalLayoutDirection('TB')}
                    className={`px-2.5 py-1 rounded font-mono font-bold text-xs transition-colors cursor-pointer ${
                      localLayoutDirection === 'TB' 
                        ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-sm' 
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                    }`}
                  >
                    Top → Bottom
                  </button>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-200 dark:border-slate-700/60 flex items-center justify-between">
                <div>
                  <div className="font-semibold text-slate-900 dark:text-slate-100">
                    Hiệu ứng liên kết mức cột (CLL)
                  </div>
                  <div className="text-[11px] text-slate-500 dark:text-slate-400">
                    Hiển thị các hạt chuyển động dọc theo liên kết lineage mức cột
                  </div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={enableCLLAnimations}
                    onChange={(e) => setEnableCLLAnimations(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-slate-300 peer-focus:outline-none rounded-full peer dark:bg-slate-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600"></div>
                </label>
              </div>

              <div className="pt-3 border-t border-slate-200 dark:border-slate-700/60 flex items-center justify-between">
                <div>
                  <div className="font-semibold text-slate-900 dark:text-slate-100">
                    Kiểu đường nối Edge
                  </div>
                  <div className="text-[11px] text-slate-500 dark:text-slate-400">
                    Sử dụng góc vuông bo tròn (Smooth Step) hoặc đường cong mềm (Bezier) cho các liên kết
                  </div>
                </div>
                <select
                  value={edgeStyle}
                  onChange={(e) => setEdgeStyle(e.target.value as any)}
                  className="px-2.5 py-1 text-xs bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg font-mono text-slate-800 dark:text-slate-200 cursor-pointer"
                >
                  <option value="smoothstep">Smooth Step</option>
                  <option value="bezier">Bezier Curve</option>
                </select>
              </div>
            </div>
          </div>

          {/* Section 3: Appearance */}
          <div>
            <div className="flex items-center justify-between bg-slate-50 dark:bg-slate-800/40 p-4 rounded-xl border border-slate-200 dark:border-slate-800">
              <div className="flex items-center gap-2.5">
                {localDarkMode ? <Moon className="w-4 h-4 text-indigo-400" /> : <Sun className="w-4 h-4 text-amber-500" />}
                <div>
                  <div className="font-semibold text-slate-900 dark:text-slate-100">Chế độ tối (Dark Mode)</div>
                  <div className="text-[11px] text-slate-500 dark:text-slate-400">Chuyển đổi giao diện hiển thị giữa chế độ sáng và chế độ tối</div>
                </div>
              </div>
              
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={localDarkMode}
                  onChange={(e) => setLocalDarkMode(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-9 h-5 bg-slate-300 peer-focus:outline-none rounded-full peer dark:bg-slate-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600"></div>
              </label>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/40 flex items-center justify-end gap-2.5">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          >
            Cancel
          </button>

          <button
            onClick={handleSave}
            className="px-4 py-2 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/20 flex items-center gap-1.5 transition-all cursor-pointer"
          >
            {isSaved ? (
              <>
                <Check className="w-4 h-4 text-white" />
                <span>Saved successfully</span>
              </>
            ) : (
              <span>Save Settings</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
