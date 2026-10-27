import React from 'react';
import { motion } from 'motion/react';
import { 
  ShieldCheck, 
  UserCheck, 
  Cpu, 
  FileSearch,
  CheckCircle2
} from 'lucide-react';

const smoothTransition = {
  duration: 0.75,
  ease: [0.16, 1, 0.3, 1] as const,
};

export const AccuracyTrustSection: React.FC = () => {
  return (
    <section id="accuracy" className="relative z-10 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 md:py-28 border-t border-slate-800/80 overflow-hidden gpu-layer">
      
      {/* Ambient Emerald & Cyan Aura */}
      <div className="absolute top-1/2 left-1/4 -translate-y-1/2 w-96 h-96 pointer-events-none -z-10">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          whileInView={{ opacity: [0.12, 0.28, 0.12], scale: [0.9, 1.15, 0.9] }}
          viewport={{ once: false, amount: 0.15 }}
          transition={{ duration: 4.5, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute inset-0 bg-emerald-500/15 blur-[100px] rounded-full transform-gpu"
        />
      </div>

      {/* 2-Column Layout: Left 60% (Visual Architecture Canvas) — Right 40% (Text) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-14 items-center">
        
        {/* CỘT TRÁI (HÌNH MINH HỌA KIẾN TRÚC DUAL-ENGINE CHÍNH XÁC THEO HÌNH - 60% / col-span-7) */}
        <motion.div
          initial={{ opacity: 0, x: -30, scale: 0.9 }}
          whileInView={{ opacity: 1, x: 0, scale: 0.92 }}
          viewport={{ once: false, amount: 0.15 }}
          transition={smoothTransition}
          className="lg:col-span-7 order-2 lg:order-1 transform-gpu w-full origin-center lg:origin-left"
        >
          {/* Glass Card với viền bo tròn và phát sáng cao cấp đúng như ảnh mẫu */}
          <div className="relative w-full rounded-[28px] p-6 sm:p-8 bg-[#09111e]/90 border border-cyan-500/30 backdrop-blur-2xl shadow-[0_0_60px_rgba(6,182,212,0.15)] overflow-hidden transform-gpu">
            
            {/* Top Bar Indicator */}
            <div className="flex items-center justify-between pb-3.5 border-b border-slate-800/80">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                <span className="text-xs font-bold text-emerald-400 font-mono uppercase tracking-wider">
                  KIẾN TRÚC DUAL-ENGINE (ZERO-HALLUCINATION)
                </span>
              </div>
              <span className="text-[10px] font-mono px-2.5 py-0.5 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 font-bold">
                100% Deterministic
              </span>
            </div>

            {/* SVG Diagram Canvas hoàn chỉnh với tỉ lệ chuẩn & hiệu ứng động mượt mà */}
            <div className="relative w-full aspect-[16/10] min-h-[340px] sm:min-h-[380px] select-none mt-2">
              <svg 
                className="w-full h-full overflow-visible" 
                viewBox="0 0 700 420" 
                preserveAspectRatio="xMidYMid meet"
              >
                <defs>
                  {/* Glow Filters */}
                  <filter id="cyanLaserGlow" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur stdDeviation="3.5" result="glow" />
                    <feMerge>
                      <feMergeNode in="glow" />
                      <feMergeNode in="glow" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>

                  <filter id="greenLaserGlow" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur stdDeviation="3.5" result="glow" />
                    <feMerge>
                      <feMergeNode in="glow" />
                      <feMergeNode in="glow" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>

                  <filter id="redLaserGlow" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur stdDeviation="3.5" result="glow" />
                    <feMerge>
                      <feMergeNode in="glow" />
                      <feMergeNode in="glow" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>

                  {/* Gradient Lines */}
                  <linearGradient id="cyanLineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#00f5d4" />
                    <stop offset="100%" stopColor="#00b4d8" />
                  </linearGradient>

                  <linearGradient id="redFallbackGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#ff4d6d" />
                    <stop offset="100%" stopColor="#e63946" />
                  </linearGradient>

                  <linearGradient id="greenUpGrad" x1="0%" y1="100%" x2="0%" y2="0%">
                    <stop offset="0%" stopColor="#00f5d4" />
                    <stop offset="100%" stopColor="#10b981" />
                  </linearGradient>

                  {/* Arrowheads */}
                  <marker id="arrowCyan" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
                    <path d="M 1 1 L 7 4 L 1 7 Z" fill="#00f5d4" />
                  </marker>
                  <marker id="arrowRed" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
                    <path d="M 1 1 L 7 4 L 1 7 Z" fill="#ff4d6d" />
                  </marker>
                  <marker id="arrowGreen" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
                    <path d="M 1 1 L 7 4 L 1 7 Z" fill="#10b981" />
                  </marker>
                </defs>

                {/* ======================= CÁC ĐƯỜNG NỐI & HIỆU ỨNG ĐỘNG ĐỒNG BỘ DUAL-ENGINE ======================= */}

                {/* 1. ĐƯỜNG NỐI: SQL Code -> Parser (Hiệu ứng dòng chảy Laser Cyan đồng bộ) */}
                <path
                  d="M 130 185 L 218 185"
                  fill="none"
                  stroke="#00f5d4"
                  strokeWidth="2.5"
                  opacity="0.3"
                />
                <motion.path
                  d="M 130 185 L 218 185"
                  fill="none"
                  stroke="url(#cyanLineGrad)"
                  strokeWidth="3"
                  filter="url(#cyanLaserGlow)"
                  markerEnd="url(#arrowCyan)"
                  strokeLinecap="round"
                  strokeDasharray="10 8"
                  animate={{ strokeDashoffset: [0, -36] }}
                  transition={{ duration: 1.4, repeat: Infinity, ease: 'linear' }}
                />

                {/* 2. ĐƯỜNG NHÁNH TRÊN: Parser -> Lineage Graph */}
                <path
                  d="M 265 145 L 265 102 Q 265 95, 275 95 L 558 95"
                  fill="none"
                  stroke="#00f5d4"
                  strokeWidth="2.5"
                  opacity="0.3"
                />
                <motion.path
                  d="M 265 145 L 265 102 Q 265 95, 275 95 L 558 95"
                  fill="none"
                  stroke="url(#cyanLineGrad)"
                  strokeWidth="3"
                  filter="url(#cyanLaserGlow)"
                  markerEnd="url(#arrowCyan)"
                  strokeLinecap="round"
                  strokeDasharray="10 8"
                  animate={{ strokeDashoffset: [0, -36] }}
                  transition={{ duration: 1.8, repeat: Infinity, ease: 'linear' }}
                />

                {/* 3. ĐƯỜNG NHÁNH DƯỚI (Fallback): Parser -> LLM (Hiệu ứng dòng chảy Laser Đỏ Coral) */}
                <path
                  d="M 265 225 Q 265 285, 310 285 L 363 285"
                  fill="none"
                  stroke="#ff4d6d"
                  strokeWidth="2.5"
                  opacity="0.3"
                />
                <motion.path
                  d="M 265 225 Q 265 285, 310 285 L 363 285"
                  fill="none"
                  stroke="url(#redFallbackGrad)"
                  strokeWidth="3"
                  filter="url(#redLaserGlow)"
                  markerEnd="url(#arrowRed)"
                  strokeLinecap="round"
                  strokeDasharray="10 8"
                  animate={{ strokeDashoffset: [0, -36] }}
                  transition={{ duration: 1.4, repeat: Infinity, ease: 'linear' }}
                />

                {/* 4. ĐƯỜNG NỐI: LLM -> Human Verification (Hiệu ứng dòng chảy Laser Cyan đồng bộ) */}
                <path
                  d="M 445 285 L 493 285"
                  fill="none"
                  stroke="#00f5d4"
                  strokeWidth="2.5"
                  opacity="0.3"
                />
                <motion.path
                  d="M 445 285 L 493 285"
                  fill="none"
                  stroke="url(#cyanLineGrad)"
                  strokeWidth="3"
                  filter="url(#cyanLaserGlow)"
                  markerEnd="url(#arrowCyan)"
                  strokeLinecap="round"
                  strokeDasharray="10 8"
                  animate={{ strokeDashoffset: [0, -36] }}
                  transition={{ duration: 1.4, repeat: Infinity, ease: 'linear' }}
                />

                {/* 5. ĐƯỜNG NỐI: Human Verification -> Lineage Graph */}
                <path
                  d="M 575 285 Q 605 285, 605 255 L 605 142"
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="2.5"
                  opacity="0.3"
                />
                <motion.path
                  d="M 575 285 Q 605 285, 605 255 L 605 142"
                  fill="none"
                  stroke="url(#greenUpGrad)"
                  strokeWidth="3"
                  filter="url(#greenLaserGlow)"
                  markerEnd="url(#arrowGreen)"
                  strokeLinecap="round"
                  strokeDasharray="12 8"
                  animate={{ strokeDashoffset: [0, -40] }}
                  transition={{ duration: 1.6, repeat: Infinity, ease: 'linear' }}
                />

                {/* ======================= CÁC HUY HIỆU EVIDENCE 🔍 (CÓ HIỆU ỨNG NHẤP NHÁY TINH TẾ) ======================= */}
                
                {/* Badge 1: Trên đường SQL Input */}
                <motion.g 
                  transform="translate(170, 160)"
                  animate={{ scale: [1, 1.1, 1] }}
                  transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
                >
                  <rect width="20" height="20" rx="5" fill="#091b2c" stroke="#00f5d4" strokeWidth="1.2" />
                  <circle cx="9" cy="9" r="3.5" stroke="#38bdf8" strokeWidth="1.3" fill="none" />
                  <line x1="12" y1="12" x2="15.5" y2="15.5" stroke="#38bdf8" strokeWidth="1.3" strokeLinecap="round" />
                </motion.g>

                {/* Badge 2: Trên đường trên tới Lineage Graph */}
                <motion.g 
                  transform="translate(420, 72)"
                  animate={{ scale: [1, 1.1, 1] }}
                  transition={{ duration: 2.2, repeat: Infinity, delay: 0.3, ease: 'easeInOut' }}
                >
                  <rect width="20" height="20" rx="5" fill="#091b2c" stroke="#00f5d4" strokeWidth="1.2" />
                  <circle cx="9" cy="9" r="3.5" stroke="#38bdf8" strokeWidth="1.3" fill="none" />
                  <line x1="12" y1="12" x2="15.5" y2="15.5" stroke="#38bdf8" strokeWidth="1.3" strokeLinecap="round" />
                </motion.g>

                {/* Badge 3: Trên đường Fallback tới LLM */}
                <motion.g 
                  transform="translate(330, 255)"
                  animate={{ scale: [1, 1.1, 1] }}
                  transition={{ duration: 2.2, repeat: Infinity, delay: 0.6, ease: 'easeInOut' }}
                >
                  <rect width="20" height="20" rx="5" fill="#260d16" stroke="#ff4d6d" strokeWidth="1.2" />
                  <circle cx="9" cy="9" r="3.5" stroke="#ff758f" strokeWidth="1.3" fill="none" />
                  <line x1="12" y1="12" x2="15.5" y2="15.5" stroke="#ff758f" strokeWidth="1.3" strokeLinecap="round" />
                </motion.g>

                {/* Badge 4: Trên đường giữa LLM và Human */}
                <motion.g 
                  transform="translate(465, 260)"
                  animate={{ scale: [1, 1.1, 1] }}
                  transition={{ duration: 2.2, repeat: Infinity, delay: 0.9, ease: 'easeInOut' }}
                >
                  <rect width="20" height="20" rx="5" fill="#091b2c" stroke="#00f5d4" strokeWidth="1.2" />
                  <circle cx="9" cy="9" r="3.5" stroke="#38bdf8" strokeWidth="1.3" fill="none" />
                  <line x1="12" y1="12" x2="15.5" y2="15.5" stroke="#38bdf8" strokeWidth="1.3" strokeLinecap="round" />
                </motion.g>

                {/* Badge 5: Trên đường từ Human lên Lineage Graph */}
                <motion.g 
                  transform="translate(618, 220)"
                  animate={{ scale: [1, 1.1, 1] }}
                  transition={{ duration: 2.2, repeat: Infinity, delay: 1.2, ease: 'easeInOut' }}
                >
                  <rect width="20" height="20" rx="5" fill="#091b2c" stroke="#00f5d4" strokeWidth="1.2" />
                  <circle cx="9" cy="9" r="3.5" stroke="#38bdf8" strokeWidth="1.3" fill="none" />
                  <line x1="12" y1="12" x2="15.5" y2="15.5" stroke="#38bdf8" strokeWidth="1.3" strokeLinecap="round" />
                </motion.g>

                {/* ======================= TEXT LABELS TRÊN ĐƯỜNG DẪN ======================= */}
                <text x="175" y="210" fill="#00f5d4" fontSize="11" fontFamily="ui-monospace, monospace" fontWeight="600" textAnchor="middle">
                  SQL Input
                </text>

                <text x="315" y="322" fill="#ff758f" fontSize="11" fontFamily="ui-monospace, monospace" fontWeight="600" textAnchor="middle">
                  Complex SQL
                </text>
                <text x="315" y="337" fill="#ff758f" fontSize="10" fontFamily="ui-monospace, monospace" fontWeight="500" textAnchor="middle">
                  (Fallback)
                </text>

                {/* ======================= 5 KHỐI NODE CHÍNH ======================= */}

                {/* NODE 1: SQL Code (Trái) */}
                <g transform="translate(55, 145)" className="cursor-pointer">
                  {/* Card Body */}
                  <rect width="75" height="80" rx="16" fill="#101928" stroke="#334155" strokeWidth="1.5" />
                  
                  {/* Code lines graphic */}
                  <path d="M 20 28 L 26 33 L 20 38" fill="none" stroke="#00f5d4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <line x1="32" y1="33" x2="55" y2="33" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" />
                  <line x1="20" y1="46" x2="48" y2="46" stroke="#00f5d4" strokeWidth="2" strokeLinecap="round" />
                  <line x1="20" y1="56" x2="58" y2="56" stroke="#10b981" strokeWidth="2" strokeLinecap="round" />
                  <line x1="20" y1="66" x2="38" y2="66" stroke="#64748b" strokeWidth="2" strokeLinecap="round" />

                  {/* Node label */}
                  <text x="37.5" y="105" fill="#ffffff" fontSize="13" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                    SQL Code
                  </text>
                </g>

                {/* NODE 2: Parser `sqlglot` (Xanh lá neon với checkmark) */}
                <g transform="translate(225, 145)" className="cursor-pointer">
                  {/* Card Body với viền xanh lá neon phát sáng */}
                  <rect width="80" height="80" rx="16" fill="#061e16" stroke="#10b981" strokeWidth="2" filter="url(#greenLaserGlow)" />
                  <rect width="80" height="80" rx="16" fill="#061e16" stroke="#34d399" strokeWidth="1.5" />

                  {/* Document + Magnifier Icon */}
                  <path d="M 28 24 L 44 24 L 52 32 L 52 56 L 28 56 Z" fill="none" stroke="#34d399" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M 44 24 L 44 32 L 52 32" fill="none" stroke="#34d399" strokeWidth="1.5" />
                  <line x1="33" y1="36" x2="40" y2="36" stroke="#34d399" strokeWidth="1.5" strokeLinecap="round" />
                  <line x1="33" y1="44" x2="45" y2="44" stroke="#34d399" strokeWidth="1.5" strokeLinecap="round" />
                  
                  {/* Small Magnifier at bottom right of icon */}
                  <circle cx="48" cy="52" r="5" fill="#061e16" stroke="#6ee7b7" strokeWidth="1.5" />
                  <line x1="52" y1="56" x2="57" y2="61" stroke="#6ee7b7" strokeWidth="2" strokeLinecap="round" />

                  {/* Top-Right Green Checkmark Badge */}
                  <motion.g
                    animate={{ scale: [1, 1.15, 1] }}
                    transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
                  >
                    <circle cx="74" cy="8" r="10" fill="#10b981" stroke="#a7f3d0" strokeWidth="1.5" />
                    <path d="M 70 8 L 73 11 L 78 5" fill="none" stroke="#061e16" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                  </motion.g>

                  {/* Labels under Node */}
                  <text x="40" y="105" fill="#34d399" fontSize="13" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                    Parser
                  </text>
                </g>

                {/* NODE 3: LLM Speedometer (98%) */}
                <g transform="translate(370, 245)" className="cursor-pointer">
                  {/* Card Body */}
                  <rect width="75" height="80" rx="16" fill="#140e1c" stroke="#475569" strokeWidth="1.5" />

                  {/* Speedometer graphic */}
                  <path d="M 20 48 A 18 18 0 1 1 55 48" fill="none" stroke="#334155" strokeWidth="3.5" strokeLinecap="round" />
                  <path d="M 20 48 A 18 18 0 1 1 50 30" fill="none" stroke="#10b981" strokeWidth="3.5" strokeLinecap="round" />
                  
                  {/* Needle with subtle dynamic sway */}
                  <motion.g
                    animate={{ rotate: [0, 2.5, -2.5, 0] }}
                    transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                    style={{ transformOrigin: '37.5px 48px' }}
                  >
                    <line x1="37.5" y1="48" x2="48" y2="30" stroke="#00f5d4" strokeWidth="2.5" strokeLinecap="round" />
                    <circle cx="37.5" cy="48" r="3.5" fill="#00f5d4" />
                  </motion.g>

                  {/* 98% inside card */}
                  <text x="37.5" y="66" fill="#10b981" fontSize="12" fontWeight="bold" fontFamily="ui-monospace, monospace" textAnchor="middle">
                    98%
                  </text>

                  {/* LLM Label */}
                  <text x="37.5" y="105" fill="#ffffff" fontSize="13" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                    LLM
                  </text>
                </g>

                {/* NODE 4: Human Verification */}
                <g transform="translate(500, 245)" className="cursor-pointer">
                  {/* Card Body với viền Cyan phát sáng */}
                  <rect width="75" height="80" rx="16" fill="#091b26" stroke="#00f5d4" strokeWidth="2" filter="url(#cyanLaserGlow)" />
                  <rect width="75" height="80" rx="16" fill="#091b26" stroke="#38bdf8" strokeWidth="1.5" />

                  {/* Magnifier with Checkmark inside */}
                  <circle cx="35" cy="38" r="14" fill="none" stroke="#38bdf8" strokeWidth="2" />
                  <line x1="45" y1="48" x2="55" y2="58" stroke="#38bdf8" strokeWidth="2.5" strokeLinecap="round" />
                  <path d="M 29 38 L 33 42 L 41 33" fill="none" stroke="#00f5d4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />

                  {/* Top-Right Amber Checkmark Badge */}
                  <motion.g
                    animate={{ scale: [1, 1.15, 1] }}
                    transition={{ duration: 2, repeat: Infinity, delay: 0.5, ease: 'easeInOut' }}
                  >
                    <circle cx="70" cy="8" r="10" fill="#f59e0b" stroke="#fde68a" strokeWidth="1.5" />
                    <path d="M 66 8 L 69 11 L 74 5" fill="none" stroke="#1c1917" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                  </motion.g>

                  {/* Node label */}
                  <text x="37.5" y="105" fill="#ffffff" fontSize="13" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                    Human
                  </text>
                  <text x="37.5" y="122" fill="#ffffff" fontSize="13" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                    Verification
                  </text>
                </g>

                {/* NODE 5: Lineage Graph (Đồ thị góc phải trên) */}
                <g transform="translate(565, 55)" className="cursor-pointer">
                  {/* Card Body với viền Cyan/Teal */}
                  <rect width="80" height="80" rx="16" fill="#061824" stroke="#00f5d4" strokeWidth="2" filter="url(#cyanLaserGlow)" />
                  <rect width="80" height="80" rx="16" fill="#061824" stroke="#38bdf8" strokeWidth="1.5" />

                  {/* Network Graph Nodes & Links */}
                  <line x1="24" y1="40" x2="40" y2="24" stroke="#00f5d4" strokeWidth="1.8" />
                  <line x1="24" y1="40" x2="40" y2="56" stroke="#00f5d4" strokeWidth="1.8" />
                  <line x1="40" y1="24" x2="58" y2="40" stroke="#10b981" strokeWidth="1.8" />
                  <line x1="40" y1="56" x2="58" y2="40" stroke="#10b981" strokeWidth="1.8" />
                  <line x1="40" y1="24" x2="40" y2="56" stroke="#00f5d4" strokeWidth="1.2" strokeDasharray="3 2" />

                  <motion.circle 
                    cx="24" cy="40" r="4.5" fill="#38bdf8" 
                    animate={{ r: [4.5, 5.5, 4.5] }} 
                    transition={{ duration: 2, repeat: Infinity }} 
                  />
                  <motion.circle 
                    cx="40" cy="24" r="5" fill="#34d399" 
                    animate={{ r: [5, 6, 5] }} 
                    transition={{ duration: 2, repeat: Infinity, delay: 0.3 }} 
                  />
                  <motion.circle 
                    cx="40" cy="56" r="5" fill="#34d399" 
                    animate={{ r: [5, 6, 5] }} 
                    transition={{ duration: 2, repeat: Infinity, delay: 0.6 }} 
                  />
                  <motion.circle 
                    cx="58" cy="40" r="5.5" fill="#38bdf8" 
                    animate={{ r: [5.5, 6.5, 5.5] }} 
                    transition={{ duration: 2, repeat: Infinity, delay: 0.9 }} 
                  />

                  {/* Node label */}
                  <text x="40" y="105" fill="#ffffff" fontSize="13" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                    Lineage Graph
                  </text>
                </g>

              </svg>
            </div>

            {/* Bottom Solution Footer */}
            <div className="mt-4 pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-300">
              <span className="flex items-center gap-2 text-emerald-400 font-medium">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                Không bao giờ tự tin sai LLM — Mọi cạnh đều có Evidence rõ ràng.
              </span>
              <span className="font-mono text-emerald-400 font-bold tracking-wider hidden sm:inline">
                Zero-Hallucination
              </span>
            </div>

          </div>
        </motion.div>

        {/* CỘT PHẢI (CHỮ - 40% / col-span-5) */}
        <motion.div
          initial={{ opacity: 0, x: 30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: false, amount: 0.15 }}
          transition={smoothTransition}
          className="lg:col-span-5 flex flex-col items-start order-1 lg:order-2 transform-gpu"
        >
          {/* Eyebrow badge */}
          <div className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-semibold uppercase tracking-wider mb-5 shadow-[0_0_15px_rgba(16,185,129,0.2)]">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Độ chính xác & Đáng tin cậy</span>
          </div>

          {/* Tiêu đề ngắn gọn */}
          <h2 className="text-3xl sm:text-4xl md:text-4xl lg:text-5xl font-bold tracking-tight text-white leading-[1.18]">
            Chính xác tuyệt đối.{' '}
            <span className="bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 bg-clip-text text-transparent drop-shadow-[0_0_25px_rgba(16,185,129,0.3)]">
              Không ảo giác AI.
            </span>
          </h2>

          {/* Mô tả giải pháp chính xác */}
          <div className="mt-4 space-y-3 text-sm sm:text-base text-slate-300 leading-relaxed">
            <p>
              Agent parse SQL bằng <strong>`sqlglot`</strong> trước (chắc chắn 100%, <code>source_type=parser</code>), chỉ gọi LLM khi parser fail (dynamic SQL, Jinja macro) và luôn gắn <code>confidence</code>.
            </p>
          </div>

          {/* 3 Trụ cột cơ chế với Icon nổi bật */}
          <div className="mt-6 w-full space-y-2.5 pt-4 border-t border-slate-800">
            
            <div className="flex items-center gap-3 p-3 rounded-2xl bg-slate-900/80 border border-slate-800">
              <div className="w-9 h-9 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 shrink-0">
                <Cpu className="w-4 h-4" />
              </div>
              <div className="text-xs">
                <span className="font-bold text-white">`sqlglot` Parser 100%:</span> Độ chính xác tuyệt đối từ mã AST.
              </div>
            </div>

            <div className="flex items-center gap-3 p-3 rounded-2xl bg-slate-900/80 border border-slate-800">
              <div className="w-9 h-9 rounded-xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400 shrink-0">
                <UserCheck className="w-4 h-4" />
              </div>
              <div className="text-xs">
                <span className="font-bold text-white">Human-in-the-loop:</span> Cạnh confidence thấp phải duyệt trước khi ghi đồ thị.
              </div>
            </div>

            <div className="flex items-center gap-3 p-3 rounded-2xl bg-slate-900/80 border border-slate-800">
              <div className="w-9 h-9 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shrink-0">
                <FileSearch className="w-4 h-4" />
              </div>
              <div className="text-xs">
                <span className="font-bold text-white">Minh chứng Evidence:</span> Kèm file, dòng code và lý do LLM để tự thẩm định.
              </div>
            </div>

          </div>
        </motion.div>

      </div>
    </section>
  );
};
