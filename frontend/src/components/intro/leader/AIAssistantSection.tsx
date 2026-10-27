import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Bot, 
  User, 
  Sparkles, 
  Zap,
  CheckCircle2,
  TrendingUp,
  Database,
  Layers
} from 'lucide-react';

const smoothTransition = {
  duration: 0.75,
  ease: [0.16, 1, 0.3, 1] as const,
};

export const AIAssistantSection: React.FC = () => {
  const [selectedPrompt, setSelectedPrompt] = useState<number>(0);

  const queryOptions = [
    {
      id: 0,
      question: 'Doanh thu lấy từ đâu?',
      sourceA: 'Source A',
      sourceB: 'Source B',
      target: 'Revenue',
      badge: '100%',
      speed: '< 0.5s',
      colorA: '#38bdf8',
      colorB: '#34d399',
    },
    {
      id: 1,
      question: 'Khách hàng VIP tính thế nào?',
      sourceA: 'dim_users',
      sourceB: 'orders_fact',
      target: 'VIP Cohort',
      badge: '100%',
      speed: '< 0.4s',
      colorA: '#818cf8',
      colorB: '#38bdf8',
    },
    {
      id: 2,
      question: 'Báo cáo thuế lấy dữ liệu nào?',
      sourceA: 'stripe_logs',
      sourceB: 'vat_invoice',
      target: 'Tax Report',
      badge: '99.9%',
      speed: '< 0.5s',
      colorA: '#f43f5e',
      colorB: '#fbbf24',
    }
  ];

  const currentData = queryOptions[selectedPrompt];

  return (
    <section id="ai-assistant" className="relative z-10 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 md:py-28 border-t border-slate-800/80 overflow-hidden gpu-layer">
      
      {/* Background Neural Glow */}
      <div className="absolute top-1/2 left-1/4 -translate-y-1/2 w-[480px] h-[480px] pointer-events-none -z-10">
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          whileInView={{ opacity: [0.12, 0.28, 0.12], scale: [0.9, 1.15, 0.9] }}
          viewport={{ once: false, amount: 0.15 }}
          transition={{ duration: 4.5, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute inset-0 bg-gradient-to-tr from-teal-500/15 via-cyan-500/10 to-indigo-500/15 blur-[105px] rounded-full transform-gpu"
        />
      </div>

      {/* 2-Column Layout: Left 60% (Interactive AI Visual Mockup) — Right 40% (Text) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-14 items-center">
        
        {/* BÊN TRÁI (HÌNH MINH HỌA CHUẨN THEO ẢNH USER - 60% / col-span-7) */}
        <motion.div
          initial={{ opacity: 0, x: -30, scale: 0.9 }}
          whileInView={{ opacity: 1, x: 0, scale: 0.92 }}
          viewport={{ once: false, amount: 0.15 }}
          transition={smoothTransition}
          className="lg:col-span-7 order-2 lg:order-1 transform-gpu w-full origin-center lg:origin-left"
        >
          {/* Main Glass Card Frame */}
          <div className="relative w-full rounded-[28px] p-5 sm:p-7 bg-[#09121f]/90 border border-teal-500/30 backdrop-blur-2xl shadow-[0_0_55px_rgba(20,184,166,0.18)] overflow-hidden">
            
            {/* Quick interactive selector pills above chat */}
            <div className="flex flex-wrap gap-2 mb-4">
              {queryOptions.map((item, idx) => (
                <button
                  key={item.id}
                  onClick={() => setSelectedPrompt(idx)}
                  className={`text-xs px-3 py-1.5 rounded-xl border transition-all cursor-pointer font-mono ${
                    selectedPrompt === idx
                      ? 'bg-teal-500/25 border-teal-500/60 text-teal-200 font-bold shadow-[0_0_15px_rgba(20,184,166,0.25)]'
                      : 'bg-[#10192b] border-slate-800 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {item.question}
                </button>
              ))}
            </div>

            {/* HÀNG 1: USER PROMPT ROW */}
            <div className="flex items-center gap-3.5 mb-4">
              {/* User Avatar */}
              <div className="w-10 h-10 rounded-2xl bg-cyan-950/80 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.2)] shrink-0">
                <User className="w-5 h-5" />
              </div>
              
              {/* User Input Bubble */}
              <div className="flex-1 px-5 py-3.5 rounded-2xl bg-[#0d1829]/90 border border-slate-700/80 text-white text-sm sm:text-base font-medium shadow-inner flex items-center justify-between">
                <span>{currentData.question}</span>
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse hidden sm:block" />
              </div>
            </div>

            {/* HÀNG 2: AI BOT RESPONSE CANVAS */}
            <div className="flex items-start gap-3.5">
              {/* Bot Avatar */}
              <div className="w-10 h-10 rounded-2xl bg-teal-950/80 border border-teal-500/40 flex items-center justify-center text-teal-300 shadow-[0_0_15px_rgba(20,184,166,0.25)] shrink-0 mt-1">
                <Bot className="w-5 h-5" />
              </div>

              {/* Bot Visual Card Frame */}
              <div className="flex-1 rounded-2xl p-4 sm:p-6 bg-[#0c1626]/95 border border-teal-500/25 shadow-lg relative overflow-hidden">
                
                {/* Speed Badge Pill (⚡ < 0.5s) */}
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl bg-teal-500/15 border border-teal-400/40 text-teal-300 text-xs font-mono font-bold shadow-[0_0_12px_rgba(20,184,166,0.2)] mb-4">
                  <Zap className="w-3.5 h-3.5 text-teal-300 fill-teal-300" />
                  <span>{currentData.speed}</span>
                </div>

                {/* Inner Pipeline Canvas Container */}
                <div className="relative w-full rounded-2xl p-4 sm:p-6 bg-[#080f1b] border border-slate-800/90 shadow-inner">
                  
                  {/* SVG DIAGRAM: SOURCE A + SOURCE B -> REVENUE CHART */}
                  <div className="relative w-full aspect-[16/9] min-h-[220px] select-none">
                    <svg 
                      className="w-full h-full overflow-visible" 
                      viewBox="0 0 600 280" 
                      preserveAspectRatio="xMidYMid meet"
                    >
                      <defs>
                        {/* Glow filters */}
                        <filter id="laserCyanGlow" x="-30%" y="-30%" width="160%" height="160%">
                          <feGaussianBlur stdDeviation="3.5" result="glow" />
                          <feMerge>
                            <feMergeNode in="glow" />
                            <feMergeNode in="SourceGraphic" />
                          </feMerge>
                        </filter>
                        <filter id="boxGlow" x="-20%" y="-20%" width="140%" height="140%">
                          <feGaussianBlur stdDeviation="6" result="glow" />
                          <feMerge>
                            <feMergeNode in="glow" />
                            <feMergeNode in="SourceGraphic" />
                          </feMerge>
                        </filter>

                        {/* Laser Gradient */}
                        <linearGradient id="aiLaserGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                          <stop offset="0%" stopColor="#00f5d4" />
                          <stop offset="60%" stopColor="#10b981" />
                          <stop offset="100%" stopColor="#34d399" />
                        </linearGradient>

                        {/* Arrow Marker */}
                        <marker id="arrowAiMerge" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">
                          <path d="M 1 1 L 8 4.5 L 1 8 Z" fill="#10b981" />
                        </marker>
                      </defs>

                      {/* ========================================================= */}
                      {/* 1. NODE NGUỒN 1: SOURCE A (Top Left 3D Isometric DB Stack) */}
                      {/* ========================================================= */}
                      <g transform="translate(130, 45)">
                        {/* Glowing backdrop */}
                        <rect x="-10" y="-5" width="80" height="75" rx="14" fill="#0284c7" opacity="0.12" filter="url(#boxGlow)" />
                        
                        {/* 3D Isometric Stack Layer 1 (Top) */}
                        <path d="M 30 5 L 55 18 L 30 31 L 5 18 Z" fill="#0369a1" stroke="#38bdf8" strokeWidth="2" strokeLinejoin="round" />
                        <path d="M 5 18 L 5 24 L 30 37 L 55 24 L 55 18" fill="#075985" stroke="#38bdf8" strokeWidth="2" strokeLinejoin="round" />

                        {/* Layer 2 (Middle) */}
                        <path d="M 5 28 L 5 34 L 30 47 L 55 34 L 55 28" fill="#075985" stroke="#38bdf8" strokeWidth="2" strokeLinejoin="round" />

                        {/* Layer 3 (Bottom) */}
                        <path d="M 5 38 L 5 44 L 30 57 L 55 44 L 55 38" fill="#0c4a6e" stroke="#38bdf8" strokeWidth="2" strokeLinejoin="round" />

                        {/* Label */}
                        <text x="30" y="78" fill="#93c5fd" fontSize="13" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                          {currentData.sourceA}
                        </text>
                      </g>

                      {/* ========================================================= */}
                      {/* 2. NODE NGUỒN 2: SOURCE B (Bottom Left 3D Isometric Stack)*/}
                      {/* ========================================================= */}
                      <g transform="translate(130, 155)">
                        {/* Glowing backdrop */}
                        <rect x="-10" y="-5" width="80" height="75" rx="14" fill="#059669" opacity="0.12" filter="url(#boxGlow)" />
                        
                        {/* 3D Isometric Stack Layer 1 (Top - Emerald) */}
                        <path d="M 30 5 L 55 18 L 30 31 L 5 18 Z" fill="#047857" stroke="#34d399" strokeWidth="2" strokeLinejoin="round" />
                        <path d="M 5 18 L 5 24 L 30 37 L 55 24 L 55 18" fill="#065f46" stroke="#34d399" strokeWidth="2" strokeLinejoin="round" />

                        {/* Layer 2 */}
                        <path d="M 5 28 L 5 34 L 30 47 L 55 34 L 55 28" fill="#065f46" stroke="#34d399" strokeWidth="2" strokeLinejoin="round" />

                        {/* Layer 3 */}
                        <path d="M 5 38 L 5 44 L 30 57 L 55 44 L 55 38" fill="#064e3b" stroke="#34d399" strokeWidth="2" strokeLinejoin="round" />

                        {/* Label */}
                        <text x="30" y="78" fill="#6ee7b7" fontSize="13" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                          {currentData.sourceB}
                        </text>
                      </g>

                      {/* ========================================================= */}
                      {/* 3. DÒNG LASER HỘI TỤ (CONVERGING FLOW LINES)               */}
                      {/* ========================================================= */}
                      <g>
                        {/* Static Base Lines */}
                        <path d="M 195 75 C 265 75, 275 140, 345 140" fill="none" stroke="#38bdf8" strokeWidth="3" opacity="0.25" />
                        <path d="M 195 185 C 265 185, 275 140, 345 140" fill="none" stroke="#34d399" strokeWidth="3" opacity="0.25" />

                        {/* Laser Flow 1 (Top -> Middle) */}
                        <motion.path
                          d="M 195 75 C 265 75, 275 140, 345 140"
                          fill="none"
                          stroke="url(#aiLaserGrad)"
                          strokeWidth="4"
                          filter="url(#laserCyanGlow)"
                          strokeLinecap="round"
                          strokeDasharray="12 8"
                          animate={{ strokeDashoffset: [0, -40] }}
                          transition={{ duration: 1.3, repeat: Infinity, ease: 'linear' }}
                        />

                        {/* Laser Flow 2 (Bottom -> Middle) with End Arrow */}
                        <motion.path
                          d="M 195 185 C 265 185, 275 140, 345 140"
                          fill="none"
                          stroke="url(#aiLaserGrad)"
                          strokeWidth="4"
                          filter="url(#laserCyanGlow)"
                          strokeLinecap="round"
                          strokeDasharray="12 8"
                          markerEnd="url(#arrowAiMerge)"
                          animate={{ strokeDashoffset: [0, -40] }}
                          transition={{ duration: 1.3, repeat: Infinity, ease: 'linear' }}
                        />
                      </g>

                      {/* ========================================================= */}
                      {/* 4. TARGET NODE: REVENUE (Glassmorphic Chart Card + 100%) */}
                      {/* ========================================================= */}
                      <g transform="translate(370, 95)">
                        {/* Ambient Neon Glow */}
                        <rect x="-6" y="-6" width="96" height="96" rx="22" fill="#10b981" opacity="0.2" filter="url(#boxGlow)" />

                        {/* Glassmorphic Rounded Card */}
                        <rect width="84" height="84" rx="18" fill="#0f2634" stroke="#00f5d4" strokeWidth="2" filter="url(#laserCyanGlow)" />
                        <rect width="84" height="84" rx="18" fill="url(#aiLaserGrad)" opacity="0.08" />

                        {/* Trend Up Line Chart Icon */}
                        {/* Chart Axes (Bottom & Left) */}
                        <path d="M 18 24 L 18 64 L 66 64" fill="none" stroke="#38bdf8" strokeWidth="2.5" strokeLinecap="round" opacity="0.5" />
                        
                        {/* Upward Glowing Trend Line */}
                        <motion.path
                          d="M 24 54 L 38 42 L 48 48 L 62 26"
                          fill="none"
                          stroke="#00f5d4"
                          strokeWidth="3.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          filter="url(#laserCyanGlow)"
                          animate={{ pathLength: [0.8, 1, 0.8] }}
                          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
                        />
                        {/* Arrowhead on chart */}
                        <path d="M 54 26 L 62 26 L 62 34" fill="none" stroke="#00f5d4" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />

                        {/* 100% Badge Pill at Top Right */}
                        <g transform="translate(48, -12)">
                          <rect width="66" height="24" rx="12" fill="#042f2e" stroke="#10b981" strokeWidth="1.5" filter="url(#laserCyanGlow)" />
                          {/* Mini checkmark */}
                          <circle cx="12" cy="12" r="6" fill="#10b981" />
                          <path d="M 9.5 12 L 11.5 14 L 14.5 10" fill="none" stroke="#042f2e" strokeWidth="1.5" strokeLinecap="round" />
                          
                          <text x="38" y="16" fill="#6ee7b7" fontSize="11" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                            {currentData.badge}
                          </text>
                        </g>

                        {/* Label below */}
                        <text x="42" y="112" fill="#e2e8f0" fontSize="14" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                          {currentData.target}
                        </text>
                      </g>

                    </svg>
                  </div>

                </div>
              </div>
            </div>

            {/* HÀNG 3: FOOTER VỚI LOGO SLACK & MICROSOFT TEAMS CHUẨN XÁC THEO ẢNH */}
            <div className="mt-5 pt-3.5 border-t border-slate-800/80 flex items-center justify-center gap-4">
              {/* Slack Logo */}
              <div className="w-8 h-8 rounded-xl bg-slate-900/90 border border-slate-700/80 flex items-center justify-center p-1.5 shadow-sm hover:border-teal-500/50 transition-colors">
                <svg viewBox="0 0 128 128" className="w-full h-full">
                  <path d="M26.7 82.6c0 6.6-5.4 12-12 12s-12-5.4-12-12 5.4-12 12-12h12v12zm6 0c0-6.6 5.4-12 12-12s12 5.4 12 12v30c0 6.6-5.4 12-12 12s-12-5.4-12-12v-30z" fill="#E01E5A"/>
                  <path d="M45.4 26.7c-6.6 0-12-5.4-12-12s5.4-12 12-12 12 5.4 12 12v12h-12zm0 6c6.6 0 12 5.4 12 12s-5.4 12-12 12h-30c-6.6 0-12-5.4-12-12s5.4-12 12-12h30z" fill="#36C5F0"/>
                  <path d="M101.3 45.4c0-6.6 5.4-12 12-12s12 5.4 12 12-5.4 12-12 12h-12v-12zm-6 0c0 6.6-5.4 12-12 12s-12-5.4-12-12v-30c0-6.6 5.4-12 12-12s12 5.4 12 12v30z" fill="#2EB67D"/>
                  <path d="M82.6 101.3c6.6 0 12 5.4 12 12s-5.4 12-12 12-12-5.4-12-12v-12h12zm0-6c-6.6 0-12-5.4-12-12s5.4-12 12-12h30c6.6 0 12 5.4 12 12s-5.4 12-12 12h-30z" fill="#ECB22E"/>
                </svg>
              </div>

              {/* Microsoft Teams Logo */}
              <div className="w-8 h-8 rounded-xl bg-slate-900/90 border border-slate-700/80 flex items-center justify-center p-1.5 shadow-sm hover:border-teal-500/50 transition-colors">
                <svg viewBox="0 0 24 24" className="w-full h-full">
                  <path d="M19.5 7.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm2 2h-4a1.5 1.5 0 0 0-1.5 1.5v3.25c0 .35.08.68.22.98.5.21 1.05.33 1.63.33h3.65A1.5 1.5 0 0 0 23 14.06V11a1.5 1.5 0 0 0-1.5-1.5z" fill="#5059C9"/>
                  <path d="M14.5 5.5a2.75 2.75 0 1 0 0-5.5 2.75 2.75 0 0 0 0 5.5zm2.75 2.75h-5.5A2.25 2.25 0 0 0 9.5 10.5v6.25A2.25 2.25 0 0 0 11.75 19h5.5a2.25 2.25 0 0 0 2.25-2.25V10.5a2.25 2.25 0 0 0-2.25-2.25z" fill="#7B83EB"/>
                  <rect x="2" y="7" width="9" height="9" rx="2" fill="#464EB8"/>
                  <path d="M5 9.5h3v1H7v3H6v-3H5v-1z" fill="#FFFFFF"/>
                </svg>
              </div>
            </div>

          </div>
        </motion.div>

        {/* BÊN PHẢI (CHỮ - 40% / col-span-5) */}
        <motion.div
          initial={{ opacity: 0, x: 30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: false, amount: 0.15 }}
          transition={smoothTransition}
          className="lg:col-span-5 flex flex-col items-start order-1 lg:order-2 transform-gpu"
        >
          {/* Eyebrow badge */}
          <div className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full border border-teal-500/30 bg-teal-500/10 text-teal-400 text-xs font-semibold uppercase tracking-wider mb-5 shadow-[0_0_15px_rgba(20,184,166,0.2)]">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Trợ lý dữ liệu ảo</span>
          </div>

          {/* Tiêu đề ngắn gọn */}
          <h2 className="text-3xl sm:text-4xl md:text-4xl lg:text-5xl font-bold tracking-tight text-white leading-[1.18]">
            Tra cứu tức thì.{' '}
            <span className="bg-gradient-to-r from-teal-400 via-cyan-300 to-blue-400 bg-clip-text text-transparent drop-shadow-[0_0_25px_rgba(20,184,166,0.3)]">
              Không cần lục code.
            </span>
          </h2>

          {/* Mô tả ngắn gọn */}
          <p className="mt-4 text-sm sm:text-base text-slate-300 leading-relaxed">
            Hỏi đáp bằng ngôn ngữ tự nhiên về nguồn gốc chỉ số, phạm vi tác động hay người phụ trách dữ liệu mà không cần làm phiền kỹ sư data.
          </p>

          {/* 2 Điểm nhấn trực quan */}
          <div className="mt-6 w-full space-y-2.5 pt-4 border-t border-slate-800">
            <div className="flex items-center gap-3 p-3.5 rounded-2xl bg-[#0c1424]/90 border border-slate-800 hover:border-teal-500/40 transition-colors">
              <div className="w-8 h-8 rounded-xl bg-teal-500/20 border border-teal-500/40 flex items-center justify-center text-teal-400 shrink-0">
                <Bot className="w-4 h-4" />
              </div>
              <div className="text-xs sm:text-sm">
                <span className="font-bold text-white">Phản hồi dưới 0.5s:</span> Tự động trả lời nguồn gốc số liệu cho lãnh đạo và PM.
              </div>
            </div>

            <div className="flex items-center gap-3 p-3.5 rounded-2xl bg-[#0c1424]/90 border border-slate-800 hover:border-cyan-500/40 transition-colors">
              <div className="w-8 h-8 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shrink-0">
                <Sparkles className="w-4 h-4" />
              </div>
              <div className="text-xs sm:text-sm">
                <span className="font-bold text-white">Tích hợp Slack / Teams:</span> Nhận cảnh báo lỗi ngay tại không gian làm việc của đội ngũ.
              </div>
            </div>
          </div>
        </motion.div>

      </div>
    </section>
  );
};
