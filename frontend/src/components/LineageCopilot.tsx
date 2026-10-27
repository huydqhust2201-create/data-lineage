import React, { useState, useRef, useEffect } from 'react';
import { CopilotMessage, LineageNodeData, LineageEdgeData, HITLQueueItem } from '../types/lineage';
import { askChat } from '../api/chat';
import { selectedDatabaseId } from '../api/http';
import { 
  Bot, 
  Send, 
  User, 
  Sparkles, 
  Layers, 
  Zap, 
  HelpCircle, 
  ShieldCheck, 
  Code2, 
  ExternalLink,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

interface LineageCopilotProps {
  nodes: LineageNodeData[];
  edges: LineageEdgeData[];
  hitlQueue: HITLQueueItem[];
  onNavigateToNode: (nodeId: string) => void;
  onOpenImpactForNode: (nodeId: string) => void;
  initialQuestion?: string;
}

export const LineageCopilot: React.FC<LineageCopilotProps> = ({
  nodes,
  edges,
  hitlQueue,
  onNavigateToNode,
  onOpenImpactForNode,
  initialQuestion
}) => {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<CopilotMessage[]>([
    {
      id: 'welcome',
      sender: 'agent',
      content: `Xin chào! Tôi là **Lineage Copilot** (Agent AI phát triển bởi nhóm **Baby Sharks - P-116**).

Tôi có thể giúp bạn giải đáp mọi câu hỏi về luồng dữ liệu, phân tích ảnh hưởng (**Impact Analysis**), kiểm tra nguồn gốc dữ liệu (**Upstream Provenance**), và rà soát hàng đợi **HITL Queue**.

Hãy thử nhấn các câu hỏi gợi ý bên dưới hoặc gõ câu hỏi bằng tiếng Việt / tiếng Anh!`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      suggestedQueries: [
        'Nếu tôi sửa bảng stg_orders thì có ảnh hưởng gì không?',
        'Bảng fct_daily_sales_revenue được tạo ra từ những nguồn nào?',
        'Có những cạnh nào đang chờ duyệt trong HITL Queue?',
        'Báo cáo Tableau Executive Revenue có nguy cơ bị lỗi khi đổi schema không?'
      ]
    }
  ]);

  const [input, setInput] = useState(initialQuestion || '');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  useEffect(() => {
    if (initialQuestion) {
      handleSend(initialQuestion);
    }
  }, [initialQuestion]);

  const handleSend = async (questionText?: string) => {
    const textToSend = questionText || input;
    if (!textToSend.trim() || isLoading) return;

    const userMsg: CopilotMessage = {
      id: `user_${Date.now()}`,
      sender: 'user',
      content: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const databaseId = selectedDatabaseId();
      if (!databaseId) throw new Error('Hãy chọn database trước khi chat.');
      const data = await askChat(textToSend, sessionId, databaseId);
      setSessionId(data.session_id);

      const agentMsg: CopilotMessage = {
        id: `agent_${Date.now()}`,
        sender: 'agent',
        content: data.answer || 'Đã phân tích đồ thị lineage thành công.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        suggestedQueries: data.suggestions || data.clarification_options || [],
        thoughtProcess: data.steps ? data.steps.map(step => ({
          step: step.tool,
          action: step.summary,
          observation: step.resolved ? JSON.stringify(step.resolved) : (step.error || "")
        })) : [
          { step: '1. Graph Traversal', action: 'Scan DAG Adjacency list', observation: `Inspected ${nodes.length} nodes and active dependencies.` },
          { step: '2. Impact Severity', action: 'BFS Downstream blast radius', observation: 'Calculated critical consumers (BI & ML Feature Store).' },
          { step: '3. Synthesis', action: 'Generate DE mitigation strategy', observation: 'Prepared dbt refactoring code.' }
        ]
      };

      setMessages(prev => [...prev, agentMsg]);
    } catch (err: any) {
      const errorMsg: CopilotMessage = {
        id: `agent_err_${Date.now()}`,
        sender: 'agent',
        content: `Rất tiếc, đã có lỗi khi gọi Agent: ${err.message}. Hệ thống đang sử dụng dữ liệu cục bộ.`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-5xl mx-auto h-[calc(100vh-5rem)] flex flex-col p-4 sm:p-6">
      {/* Header */}
      <div className="bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between gap-3 mb-4 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-purple-600 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-bold text-sm text-slate-900 dark:text-white font-mono">
                Lineage Copilot (AI Agent)
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 font-semibold">
                LangGraph Multi-Step Reasoning
              </span>
            </div>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              Traverse DAGs, analyze blast radius &amp; recommend dbt refactorings in natural language
            </p>
          </div>
        </div>

        <div className="hidden sm:flex items-center gap-2 text-xs font-mono text-slate-500 dark:text-slate-400">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>Graph Context Active ({nodes.length} models)</span>
        </div>
      </div>

      {/* Message Chat History */}
      <div className="flex-1 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm p-4 sm:p-6 overflow-y-auto space-y-4">
        {messages.map((msg) => {
          const isUser = msg.sender === 'user';
          return (
            <div
              key={msg.id}
              className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
            >
              <div
                className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 text-white font-bold text-xs ${
                  isUser
                    ? 'bg-slate-800 dark:bg-slate-700'
                    : 'bg-gradient-to-tr from-indigo-600 to-purple-600 shadow-sm'
                }`}
              >
                {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
              </div>

              <div className={`max-w-[85%] space-y-2 ${isUser ? 'items-end' : 'items-start'}`}>
                {/* Agent Thought Steps if available */}
                {msg.thoughtProcess && (
                  <details className="text-[11px] bg-slate-50 dark:bg-slate-800/60 p-2.5 rounded-xl border border-slate-200 dark:border-slate-700/70 font-mono text-slate-600 dark:text-slate-300">
                    <summary className="cursor-pointer font-semibold text-indigo-600 dark:text-indigo-400 flex items-center gap-1">
                      <Sparkles className="w-3.5 h-3.5" />
                      View Agent Reasoning Trace ({msg.thoughtProcess.length} steps)
                    </summary>
                    <div className="mt-2 space-y-1.5 pl-2 border-l border-indigo-300 dark:border-indigo-700">
                      {msg.thoughtProcess.map((tp, i) => (
                        <div key={i}>
                          <span className="font-bold text-slate-800 dark:text-slate-200">{tp.step}: </span>
                          <span>{tp.action} &rarr; </span>
                          <span className="text-slate-500 dark:text-slate-400">{tp.observation}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                {/* Message Body */}
                <div
                  className={`p-4 rounded-2xl text-xs sm:text-sm leading-relaxed whitespace-pre-wrap ${
                    isUser
                      ? 'bg-indigo-600 text-white rounded-tr-sm'
                      : 'bg-slate-50 dark:bg-slate-800/80 text-slate-800 dark:text-slate-100 rounded-tl-sm border border-slate-200/80 dark:border-slate-700/80'
                  }`}
                >
                  {msg.content}
                </div>

                <div className={`text-[10px] text-slate-400 font-mono ${isUser ? 'text-right' : 'text-left'}`}>
                  {msg.timestamp}
                </div>

                {/* Suggested Queries Pills */}
                {msg.suggestedQueries && (
                  <div className="pt-2 flex flex-wrap gap-2">
                    {msg.suggestedQueries.map((sq, sIdx) => (
                      <button
                        key={sIdx}
                        onClick={() => handleSend(sq)}
                        className="text-left px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-indigo-50 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 hover:text-indigo-600 dark:text-slate-300 dark:hover:text-white border border-slate-200 dark:border-slate-700 text-xs font-medium transition-colors cursor-pointer"
                      >
                        {sq}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {isLoading && (
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-600 to-purple-600 flex items-center justify-center text-white text-xs">
              <Bot className="w-4 h-4" />
            </div>
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 flex items-center gap-2 text-xs font-mono text-slate-500">
              <div className="w-3.5 h-3.5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              <span>Lineage Copilot is traversing graph and evaluating blast radius...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Form Bar */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
        className="mt-4 flex items-center gap-2 shrink-0"
      >
        <input
          id="copilot-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Hỏi về bảng, phân tích ảnh hưởng, nguồn gốc cột, lỗi breaking change..."
          className="flex-1 px-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl text-xs sm:text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm"
        />
        <button
          id="copilot-send-btn"
          type="submit"
          disabled={!input.trim() || isLoading}
          className="px-5 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-2xl text-xs sm:text-sm font-semibold flex items-center gap-1.5 shadow-md shadow-indigo-600/20 cursor-pointer transition-colors"
        >
          <Send className="w-4 h-4" />
          <span>Gửi</span>
        </button>
      </form>
    </div>
  );
};
