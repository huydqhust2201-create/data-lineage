import React from 'react';
import { motion } from 'motion/react';
import { 
  Workflow, 
  Code2, 
  ShieldCheck, 
  CheckCircle2, 
  Network
} from 'lucide-react';

const smoothTransition = {
  duration: 0.75,
  ease: [0.16, 1, 0.3, 1] as const,
};

export const ProductivityLineageSection: React.FC = () => {
  return (
    <section id="productivity" className="relative z-10 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 md:py-28 border-t border-slate-800/80 overflow-hidden gpu-layer">
      
      {/* Background Aura */}
      <div className="absolute top-1/2 right-1/4 -translate-y-1/2 w-96 h-96 pointer-events-none -z-10">
        <motion.div
          initial={{ opacity: 0, scale: 0.85 }}
          whileInView={{ opacity: [0.1, 0.25, 0.1], scale: [0.9, 1.15, 0.9] }}
          viewport={{ once: false, amount: 0.15 }}
          transition={{ duration: 4.5, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute inset-0 bg-gradient-to-tr from-cyan-500/15 via-blue-500/10 to-emerald-500/15 blur-[110px] rounded-full transform-gpu"
        />
      </div>

      {/* 2-Column Layout: Left 40% (Text) — Right 60% (Comparison Canvas) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-14 items-center">
        
        {/* BÊN TRÁI (CHỮ - 40% / col-span-5) */}
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: false, amount: 0.15 }}
          transition={smoothTransition}
          className="lg:col-span-5 flex flex-col items-start transform-gpu"
        >
          {/* Eyebrow Badge */}
          <div className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full border border-cyan-500/30 bg-cyan-500/10 text-cyan-400 text-xs font-semibold uppercase tracking-wider mb-5 shadow-[0_0_15px_rgba(6,182,212,0.2)]">
            <Workflow className="w-3.5 h-3.5" />
            <span>Tối ưu năng suất đội ngũ</span>
          </div>

          {/* Tiêu đề */}
          <h2 className="text-3xl sm:text-4xl md:text-4xl lg:text-5xl font-bold tracking-tight text-white leading-[1.18]">
            Rút ngắn 80% thời gian{' '}
            <span className="bg-gradient-to-r from-cyan-400 via-teal-300 to-indigo-400 bg-clip-text text-transparent drop-shadow-[0_0_25px_rgba(6,182,212,0.3)]">
              tìm lỗi và đào tạo nhân sự mới.
            </span>
          </h2>

          {/* 2 Điểm nổi bật */}
          <div className="mt-6 w-full space-y-4 pt-2">
            
            {/* Điểm 1: Minh bạch nguồn gốc */}
            <div className="p-4 rounded-2xl bg-[#0c1424]/90 border border-slate-800 hover:border-cyan-500/40 transition-colors">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shrink-0 mt-0.5">
                  <Code2 className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    Minh bạch nguồn gốc
                  </h3>
                  <p className="mt-1.5 text-xs sm:text-sm text-slate-300 leading-relaxed">
                    Bất kỳ ai trong team đều xem được chính xác đoạn mã nguồn tạo ra chỉ số dữ liệu đó mà không cần hỏi người viết cũ.
                  </p>
                </div>
              </div>
            </div>

            {/* Điểm 2: Đo lường tác động trước khi sửa */}
            <div className="p-4 rounded-2xl bg-[#0c1424]/90 border border-slate-800 hover:border-emerald-500/40 transition-colors">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 shrink-0 mt-0.5">
                  <ShieldCheck className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    Đo lường tác động trước khi sửa
                  </h3>
                  <p className="mt-1.5 text-xs sm:text-sm text-slate-300 leading-relaxed">
                    Kiểm tra ngay các báo cáo nào sẽ bị ảnh hưởng trước khi cập nhật hệ thống, tránh hoàn toàn các đợt gián đoạn bất ngờ.
                  </p>
                </div>
              </div>
            </div>

          </div>
        </motion.div>

        {/* BÊN PHẢI (HÌNH MINH HỌA SO SÁNH CHUẨN THEO ẢNH - 60% / col-span-7) */}
        <motion.div
          initial={{ opacity: 0, x: 30, scale: 0.9 }}
          whileInView={{ opacity: 1, x: 0, scale: 0.92 }}
          viewport={{ once: false, amount: 0.15 }}
          transition={{ ...smoothTransition, delay: 0.12 }}
          className="lg:col-span-7 transform-gpu w-full origin-center lg:origin-right"
        >
          {/* Main Glass Card Container */}
          <div className="relative w-full rounded-[28px] p-5 sm:p-7 bg-[#09111e]/90 border border-cyan-500/30 backdrop-blur-2xl shadow-[0_0_60px_rgba(6,182,212,0.15)] overflow-hidden">
            
            {/* Top Bar Header */}
            <div className="flex items-center justify-between pb-3.5 border-b border-slate-800/80">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-xl bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center text-cyan-300 shadow-[0_0_12px_rgba(6,182,212,0.3)]">
                  <Network className="w-4 h-4" />
                </div>
                <span className="text-xs sm:text-sm font-bold text-white font-mono uppercase tracking-wider">
                  CÂY PHẢ HỆ DỮ LIỆU TỰ ĐỘNG
                </span>
              </div>
            </div>

            {/* Canvas So sánh 2 bên (Trước đây vs. Với Lineage AI) */}
            <div className="relative w-full aspect-[16/11] min-h-[350px] sm:min-h-[390px] select-none mt-3">
              <svg 
                className="w-full h-full overflow-visible" 
                viewBox="0 0 740 430" 
                preserveAspectRatio="xMidYMid meet"
              >
                <defs>
                  {/* Glow Filters */}
                  <filter id="cyanGlow" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur stdDeviation="3" result="glow" />
                    <feMerge>
                      <feMergeNode in="glow" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                  <filter id="redWireGlow" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="2" result="glow" />
                    <feMerge>
                      <feMergeNode in="glow" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>

                  {/* Laser Line Gradient */}
                  <linearGradient id="laserMergeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#00f5d4" />
                    <stop offset="60%" stopColor="#10b981" />
                    <stop offset="100%" stopColor="#34d399" />
                  </linearGradient>

                  {/* Marker Arrow for Lineage Flow */}
                  <marker id="arrowLineage" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
                    <path d="M 1 1 L 7 4 L 1 7 Z" fill="#10b981" />
                  </marker>
                </defs>

                {/* Đường phân cách mờ ở giữa (Vertical Divider) */}
                <line x1="370" y1="15" x2="370" y2="395" stroke="#334155" strokeWidth="1" strokeDasharray="4 4" opacity="0.5" />

                {/* ========================================================================= */}
                {/* 1. CỘT TRÁI: TRƯỚC ĐÂY (Manual / Chưa có Tool)                           */}
                {/* ========================================================================= */}
                <g transform="translate(0, 0)">
                  
                  {/* Tiêu đề Cột Trái */}
                  <text x="185" y="38" fill="#ffffff" fontSize="16" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                    Trước đây
                  </text>
                  <text x="185" y="58" fill="#94a3b8" fontSize="12" fontFamily="sans-serif" textAnchor="middle">
                    (Manual/Chưa có Tool)
                  </text>

                  {/* DATABASE CYLINDER (Top Left) */}
                  <g transform="translate(65, 90)">
                    {/* Glow backdrop */}
                    <ellipse cx="26" cy="12" rx="28" ry="14" fill="#0369a1" opacity="0.3" filter="url(#cyanGlow)" />
                    {/* Database Layers */}
                    <path d="M 6 16 C 6 22 46 22 46 16 L 46 44 C 46 50 6 50 6 44 Z" fill="#0f2b3e" stroke="#38bdf8" strokeWidth="1.5" />
                    <path d="M 6 28 C 6 34 46 34 46 28" fill="none" stroke="#38bdf8" strokeWidth="1.2" />
                    <path d="M 6 40 C 6 46 46 46 46 40" fill="none" stroke="#38bdf8" strokeWidth="1.2" />
                    <ellipse cx="26" cy="16" rx="20" ry="7" fill="#1e3a5f" stroke="#38bdf8" strokeWidth="1.5" />
                  </g>

                  {/* SQL WINDOW TOP-RIGHT */}
                  <g transform="translate(235, 80)">
                    <rect width="65" height="50" rx="8" fill="#1e293b" stroke="#475569" strokeWidth="1.2" />
                    {/* Top dots */}
                    <circle cx="10" cy="8" r="2" fill="#ef4444" />
                    <circle cx="16" cy="8" r="2" fill="#f59e0b" />
                    <circle cx="22" cy="8" r="2" fill="#10b981" />
                    <line x1="8" y1="16" x2="45" y2="16" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" />
                    <line x1="8" y1="23" x2="55" y2="23" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />
                    <line x1="8" y1="30" x2="38" y2="30" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" />
                    <line x1="8" y1="37" x2="25" y2="37" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />
                  </g>

                  {/* SQL WINDOW BOTTOM-LEFT */}
                  <g transform="translate(60, 250)">
                    <rect width="60" height="48" rx="8" fill="#1e293b" stroke="#475569" strokeWidth="1.2" />
                    <circle cx="9" cy="8" r="2" fill="#ef4444" />
                    <circle cx="15" cy="8" r="2" fill="#f59e0b" />
                    <circle cx="21" cy="8" r="2" fill="#10b981" />
                    <line x1="8" y1="16" x2="42" y2="16" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" />
                    <line x1="8" y1="23" x2="50" y2="23" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />
                    <line x1="8" y1="30" x2="32" y2="30" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" />
                  </g>

                  {/* TANGLED CHAOTIC CORDS & WIRES (CUỘN DÂY RỐI BÙNG NHÙNG ĐỎ & XÁM) */}
                  <g>
                    {/* Dây xám nhạt đan chéo */}
                    <path
                      d="M 90 135 C 130 180, 100 230, 160 210 C 220 190, 200 130, 245 110 C 270 100, 290 140, 260 180 C 230 220, 270 270, 210 280 C 150 290, 130 240, 95 265"
                      fill="none"
                      stroke="#64748b"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                    />
                    <path
                      d="M 245 125 C 190 160, 210 230, 150 220 C 110 210, 120 160, 165 150 C 210 140, 225 180, 190 240 C 160 290, 110 270, 85 260"
                      fill="none"
                      stroke="#94a3b8"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                    <path
                      d="M 85 120 C 140 110, 160 170, 130 200 C 100 230, 180 260, 220 230 C 260 200, 230 150, 255 125"
                      fill="none"
                      stroke="#475569"
                      strokeWidth="3"
                      strokeLinecap="round"
                    />
                    
                    {/* Dây đỏ rực rối loạn */}
                    <path
                      d="M 92 130 C 150 170, 110 250, 180 240 C 240 230, 250 160, 200 140 C 150 120, 130 210, 190 260 C 240 300, 270 240, 240 190 C 220 150, 270 120, 250 105"
                      fill="none"
                      stroke="#e11d48"
                      strokeWidth="3.2"
                      filter="url(#redWireGlow)"
                      strokeLinecap="round"
                    />
                    <path
                      d="M 240 115 C 180 130, 140 180, 190 200 C 240 220, 210 280, 150 260 C 100 240, 120 180, 160 160 C 200 140, 260 170, 220 250 C 190 290, 140 280, 95 270"
                      fill="none"
                      stroke="#f43f5e"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                    />
                  </g>

                  {/* FLOATING QUESTION MARKS (?) */}
                  <motion.text 
                    x="135" y="105" fill="#94a3b8" fontSize="22" fontWeight="bold" fontFamily="sans-serif"
                    animate={{ y: [105, 98, 105], opacity: [0.6, 1, 0.6] }}
                    transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                  >?</motion.text>
                  <motion.text 
                    x="165" y="90" fill="#cbd5e1" fontSize="28" fontWeight="bold" fontFamily="sans-serif"
                    animate={{ y: [90, 82, 90], opacity: [0.7, 1, 0.7] }}
                    transition={{ duration: 3, repeat: Infinity, delay: 0.5, ease: 'easeInOut' }}
                  >?</motion.text>
                  <motion.text 
                    x="80" y="200" fill="#94a3b8" fontSize="20" fontWeight="bold" fontFamily="sans-serif"
                    animate={{ y: [200, 193, 200], opacity: [0.5, 0.9, 0.5] }}
                    transition={{ duration: 2.8, repeat: Infinity, delay: 0.8, ease: 'easeInOut' }}
                  >?</motion.text>
                  <motion.text 
                    x="275" y="225" fill="#cbd5e1" fontSize="24" fontWeight="bold" fontFamily="sans-serif"
                    animate={{ y: [225, 217, 225], opacity: [0.6, 1, 0.6] }}
                    transition={{ duration: 3.2, repeat: Infinity, delay: 1.1, ease: 'easeInOut' }}
                  >?</motion.text>

                  {/* PIXEL MAGNIFIER (Kính lúp góc phải dưới) */}
                  <g transform="translate(230, 240)">
                    <circle cx="28" cy="28" r="18" fill="#1e293b" stroke="#38bdf8" strokeWidth="3" />
                    <circle cx="28" cy="28" r="13" fill="#0f172a" stroke="#64748b" strokeWidth="1" />
                    <path d="M 23 20 A 10 10 0 0 1 33 20" fill="none" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
                    <rect x="40" y="40" width="10" height="24" rx="2" transform="rotate(-45 40 40)" fill="#d97706" stroke="#b45309" strokeWidth="1.5" />
                  </g>

                  {/* Nhãn Kết quả Cột Trái */}
                  <text x="185" y="375" fill="#f43f5e" fontSize="15" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                    Mất 4-8 giờ tra cứu
                  </text>
                </g>

                {/* ========================================================================= */}
                {/* 2. CỘT PHẢI: VỚI LINEAGE AI                                               */}
                {/* ========================================================================= */}
                <g transform="translate(370, 0)">
                  
                  {/* Tiêu đề Cột Phải */}
                  <text x="185" y="38" fill="#38bdf8" fontSize="16" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                    Với Lineage AI
                  </text>

                  {/* 1-CLICK SEARCH BAR */}
                  <g transform="translate(40, 52)">
                    {/* Search pill container */}
                    <rect width="290" height="34" rx="17" fill="#0f172a" stroke="#334155" strokeWidth="1.2" />
                    
                    {/* Search icon & placeholder */}
                    <circle cx="22" cy="17" r="4.5" fill="none" stroke="#94a3b8" strokeWidth="1.3" />
                    <line x1="25.5" y1="20.5" x2="29" y2="24" stroke="#94a3b8" strokeWidth="1.3" strokeLinecap="round" />
                    <text x="36" y="21" fill="#94a3b8" fontSize="12" fontFamily="sans-serif">
                      1-click search
                    </text>

                    {/* Find Lineage Button */}
                    <g transform="translate(180, 4)">
                      <rect width="102" height="26" rx="13" fill="url(#laserMergeGrad)" filter="url(#cyanGlow)" />
                      <text x="51" y="17" fill="#032117" fontSize="11" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                        Find Lineage
                      </text>
                    </g>
                  </g>

                  {/* 3 NGUỒN NODE BÊN TRÁI (DATABASE, AIRFLOW, CONNECTOR) */}

                  {/* Node 1: Database Cylinder */}
                  <g transform="translate(50, 115)">
                    <rect width="52" height="52" rx="14" fill="#0b2030" stroke="#00f5d4" strokeWidth="1.5" filter="url(#cyanGlow)" />
                    {/* Mini DB Icon */}
                    <path d="M 16 20 C 16 24 36 24 36 20 L 36 34 C 36 38 16 38 16 34 Z" fill="#0369a1" stroke="#38bdf8" strokeWidth="1.2" />
                    <ellipse cx="26" cy="20" rx="10" ry="4" fill="#38bdf8" />
                  </g>

                  {/* Node 2: Airflow/Transform (Propeller Logo) */}
                  <g transform="translate(50, 185)">
                    <rect width="52" height="52" rx="14" fill="#1e1315" stroke="#ff4d6d" strokeWidth="1.2" />
                    {/* Airflow Pinwheel/Propeller Icon */}
                    <path d="M 26 26 L 18 16 C 22 14 28 14 30 18 Z" fill="#f43f5e" />
                    <path d="M 26 26 L 36 18 C 38 22 38 28 34 30 Z" fill="#fb7185" />
                    <path d="M 26 26 L 34 36 C 30 38 24 38 22 34 Z" fill="#f43f5e" />
                    <path d="M 26 26 L 16 34 C 14 30 14 24 18 22 Z" fill="#fb7185" />
                    <circle cx="26" cy="26" r="3" fill="#ffffff" />
                  </g>

                  {/* Node 3: Connector / Pipeline */}
                  <g transform="translate(50, 255)">
                    <rect width="52" height="52" rx="14" fill="#081c1c" stroke="#10b981" strokeWidth="1.2" />
                    {/* Bowtie / Pipeline spool icon */}
                    <path d="M 17 19 L 23 26 L 17 33 Z" fill="#10b981" />
                    <path d="M 35 19 L 29 26 L 35 33 Z" fill="#10b981" />
                    <line x1="23" y1="26" x2="29" y2="26" stroke="#34d399" strokeWidth="2.5" />
                  </g>

                  {/* 3 CONVERGING GLOWING LASER LINES (3 DÒNG NĂNG LƯỢNG HỘI TỤ VÀO MỤC TIÊU) */}
                  <g>
                    {/* Background paths */}
                    <path d="M 102 141 C 145 141, 145 211, 195 211" fill="none" stroke="#00f5d4" strokeWidth="3" opacity="0.3" />
                    <path d="M 102 211 L 195 211" fill="none" stroke="#00f5d4" strokeWidth="3" opacity="0.3" />
                    <path d="M 102 281 C 145 281, 145 211, 195 211" fill="none" stroke="#10b981" strokeWidth="3" opacity="0.3" />

                    {/* Laser Flow Top (Database -> Merge) */}
                    <motion.path
                      d="M 102 141 C 145 141, 145 211, 195 211"
                      fill="none"
                      stroke="url(#laserMergeGrad)"
                      strokeWidth="3.5"
                      filter="url(#cyanGlow)"
                      strokeLinecap="round"
                      strokeDasharray="10 8"
                      animate={{ strokeDashoffset: [0, -36] }}
                      transition={{ duration: 1.4, repeat: Infinity, ease: 'linear' }}
                    />

                    {/* Laser Flow Middle (Airflow -> Merge) */}
                    <motion.path
                      d="M 102 211 L 195 211"
                      fill="none"
                      stroke="url(#laserMergeGrad)"
                      strokeWidth="3.5"
                      filter="url(#cyanGlow)"
                      strokeLinecap="round"
                      strokeDasharray="10 8"
                      animate={{ strokeDashoffset: [0, -36] }}
                      transition={{ duration: 1.4, repeat: Infinity, ease: 'linear' }}
                    />

                    {/* Laser Flow Bottom (Connector -> Merge) */}
                    <motion.path
                      d="M 102 281 C 145 281, 145 211, 195 211"
                      fill="none"
                      stroke="url(#laserMergeGrad)"
                      strokeWidth="3.5"
                      filter="url(#cyanGlow)"
                      strokeLinecap="round"
                      strokeDasharray="10 8"
                      markerEnd="url(#arrowLineage)"
                      animate={{ strokeDashoffset: [0, -36] }}
                      transition={{ duration: 1.4, repeat: Infinity, ease: 'linear' }}
                    />
                  </g>

                  {/* TARGET TERMINAL / SQL WINDOW */}
                  <g transform="translate(195, 140)">
                    {/* Window Container */}
                    <rect width="125" height="110" rx="14" fill="#08141f" stroke="#00f5d4" strokeWidth="1.5" filter="url(#cyanGlow)" />
                    
                    {/* macOS Style Dots */}
                    <circle cx="15" cy="14" r="3" fill="#ef4444" />
                    <circle cx="24" cy="14" r="3" fill="#f59e0b" />
                    <circle cx="33" cy="14" r="3" fill="#10b981" />
                    
                    {/* SQL Code text */}
                    <text x="14" y="34" fill="#00f5d4" fontSize="9" fontFamily="ui-monospace, monospace" fontWeight="bold">
                      SELECT
                    </text>
                    <text x="22" y="48" fill="#94a3b8" fontSize="8" fontFamily="ui-monospace, monospace">
                      SELECT → 90LT,
                    </text>
                    <text x="22" y="62" fill="#38bdf8" fontSize="8" fontFamily="ui-monospace, monospace">
                      MODEL 3,
                    </text>
                    <text x="22" y="76" fill="#10b981" fontSize="8" fontFamily="ui-monospace, monospace">
                      FROM 2
                    </text>
                    <text x="14" y="90" fill="#00f5d4" fontSize="9" fontFamily="ui-monospace, monospace" fontWeight="bold">
                      END
                    </text>

                    {/* OWNER BADGE (DATA ENG.) */}
                    <g transform="translate(20, 118)">
                      <rect width="85" height="24" rx="12" fill="#061e29" stroke="#00f5d4" strokeWidth="1.2" />
                      {/* Avatar icon */}
                      <circle cx="12" cy="12" r="8" fill="#f59e0b" />
                      <circle cx="12" cy="10" r="3" fill="#ffffff" />
                      <path d="M 7 17 C 7 14 17 14 17 17 Z" fill="#ffffff" />
                      
                      <text x="26" y="16" fill="#ffffff" fontSize="10" fontWeight="bold" fontFamily="sans-serif">
                        Data Eng.
                      </text>
                    </g>
                  </g>

                  {/* Nhãn Kết quả Cột Phải */}
                  <text x="185" y="375" fill="#10b981" fontSize="15" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
                    30 giây - Instant
                  </text>
                </g>

              </svg>
            </div>

            {/* Bottom Solution Footer Badge */}
            <div className="mt-4 pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-300">
              <span className="flex items-center gap-2 text-cyan-400 font-medium">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                Truy vết toàn diện tự động từ bảng nguồn đến báo cáo.
              </span>
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 font-mono text-[11px] font-bold shadow-[0_0_12px_rgba(16,185,129,0.2)]">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                14 pipeline tự động
              </span>
            </div>

          </div>
        </motion.div>

      </div>
    </section>
  );
};
