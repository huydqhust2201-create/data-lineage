import React from 'react';
import { motion } from 'motion/react';
import { 
  AlertTriangle, 
  TrendingDown, 
  AlertOctagon,
  ShieldCheck
} from 'lucide-react';

const smoothTransition = {
  duration: 0.75,
  ease: [0.16, 1, 0.3, 1] as const,
};

export const RiskImpactSection: React.FC = () => {
  return (
    <section id="risk" className="relative z-10 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 md:py-28 border-t border-slate-800/80 overflow-hidden gpu-layer">
      
      {/* Ambient Crimson Aura */}
      <div className="absolute top-1/2 right-1/4 -translate-y-1/2 w-96 h-96 pointer-events-none -z-10">
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          whileInView={{ opacity: [0.1, 0.25, 0.1], scale: [0.9, 1.15, 0.9] }}
          viewport={{ once: false, amount: 0.15 }}
          transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute inset-0 bg-rose-600/15 blur-[100px] rounded-full transform-gpu"
        />
      </div>

      {/* 2-Column Layout: Left 40% (Text) — Right 60% (Lightning Blast Radius Visual) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-14 items-center">
        
        {/* Left Column (40% - col-span-5) */}
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: false, amount: 0.15 }}
          transition={smoothTransition}
          className="lg:col-span-5 flex flex-col items-start transform-gpu"
        >
          {/* Eyebrow badge */}
          <div className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full border border-rose-500/30 bg-rose-500/10 text-rose-400 text-xs font-semibold uppercase tracking-wider mb-5 shadow-[0_0_15px_rgba(244,63,94,0.2)]">
            <AlertTriangle className="w-3.5 h-3.5 text-rose-400 animate-pulse" />
            <span>Rủi ro kinh doanh & Chi phí</span>
          </div>

          {/* Tiêu đề ngắn gọn, đanh thép */}
          <h2 className="text-3xl sm:text-4xl md:text-4xl lg:text-5xl font-bold tracking-tight text-white leading-[1.18]">
            Đừng để một lỗi nhỏ làm sập báo cáo{' '}
            <span className="bg-gradient-to-r from-rose-400 via-red-300 to-amber-400 bg-clip-text text-transparent drop-shadow-[0_0_25px_rgba(244,63,94,0.3)]">
              Ban Giám đốc.
            </span>
          </h2>

          {/* Mô tả ngắn gọn, dễ hiểu */}
          <p className="mt-4 text-sm sm:text-base text-slate-300 leading-relaxed">
            Hệ thống phình to khiến một chỉnh sửa nhỏ ở tầng database nguồn kích hoạt chuỗi lỗi lan truyền, làm sai lệch số liệu trên toàn bộ Dashboard tài chính cấp cao.
          </p>

          {/* Key Point Badge */}
          <div className="mt-6 p-4 rounded-2xl bg-slate-900/80 border border-slate-800 flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-rose-500/20 border border-rose-500/40 flex items-center justify-center text-rose-400 shrink-0">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div className="text-xs text-slate-300">
              <span className="font-bold text-white">Lan truyền rủi ro:</span> 1 thay đổi schema chưa kiểm soát có thể kéo theo hàng loạt sai lệch số liệu liên phòng ban.
            </div>
          </div>
        </motion.div>

        {/* Right Column (60% - col-span-7) - HÌNH MINH HỌA KÉO DÀI ĐỘ RỘNG (EXPANDED WIDTH) */}
        <motion.div
          initial={{ opacity: 0, x: 30, scale: 0.9 }}
          whileInView={{ opacity: 1, x: 0, scale: 0.92 }}
          viewport={{ once: false, amount: 0.15 }}
          transition={{ ...smoothTransition, delay: 0.12 }}
          className="lg:col-span-7 transform-gpu w-full origin-center lg:origin-right"
        >
          {/* Glass Card với viền phát sáng đỏ Neon cao cấp - Kéo dài toàn bộ chiều rộng w-full */}
          <div className="relative w-full rounded-3xl p-6 sm:p-7 bg-[#090d16]/95 border border-rose-500/40 backdrop-blur-2xl shadow-[0_0_55px_rgba(244,63,94,0.18)] overflow-hidden transform-gpu">
            
            {/* Top Header */}
            <div className="flex items-center justify-between pb-3.5 border-b border-slate-800/80">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
                <span className="text-xs font-bold text-rose-400 font-mono uppercase tracking-wider">
                  CẢNH BÁO LAN TRUYỀN SỰ CỐ
                </span>
              </div>
              <span className="text-[10px] font-mono px-2.5 py-0.5 rounded-full bg-rose-500/20 border border-rose-500/40 text-rose-300 font-bold">
                PR #142
              </span>
            </div>

            {/* SƠ ĐỒ THEO HÌNH: DATABASE TRÁI ➔ TIA SẤM SÉT THU GỌN ➔ NỐI ĐẾN MÉP TRÁI ICON BÊN PHẢI */}
            <div className="relative mt-5 min-h-[300px] sm:min-h-[330px] flex items-center justify-between">
              
              {/* CỘT TRÁI: 3D METALLIC GLOWING RED DATABASE */}
              <div className="relative z-20 flex flex-col items-center shrink-0 pl-1 sm:pl-2">
                <motion.div 
                  className="relative group cursor-pointer"
                  whileHover={{ scale: 1.05 }}
                  transition={{ type: 'spring', stiffness: 300, damping: 20 }}
                >
                  {/* Outer Red Ambient Pulse */}
                  <motion.div
                    animate={{
                      scale: [1, 1.2, 1],
                      opacity: [0.35, 0.65, 0.35],
                    }}
                    transition={{
                      duration: 2.2,
                      repeat: Infinity,
                      ease: 'easeInOut',
                    }}
                    className="absolute -inset-3 bg-rose-600/30 blur-xl rounded-full pointer-events-none transform-gpu"
                  />

                  {/* 3D Metallic Red Database Cylinder SVG */}
                  <div className="relative w-20 h-20 sm:w-24 sm:h-24 flex items-center justify-center">
                    <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-[0_0_18px_rgba(244,63,94,0.6)]">
                      <defs>
                        <radialGradient id="dbRedRadial" cx="50%" cy="30%" r="70%">
                          <stop offset="0%" stopColor="#ff4d6d" />
                          <stop offset="50%" stopColor="#d90429" />
                          <stop offset="100%" stopColor="#590d22" />
                        </radialGradient>
                        <linearGradient id="dbMetalRim" x1="0%" y1="0%" x2="100%" y2="0%">
                          <stop offset="0%" stopColor="#ff758f" />
                          <stop offset="30%" stopColor="#d90429" />
                          <stop offset="70%" stopColor="#800f2f" />
                          <stop offset="100%" stopColor="#ff758f" />
                        </linearGradient>
                      </defs>

                      {/* Bottom Cylinder Layer */}
                      <path d="M 20 50 L 20 70 C 20 82 80 82 80 70 L 80 50 C 80 62 20 62 20 50 Z" fill="url(#dbRedRadial)" stroke="#ff4d6d" strokeWidth="1.2" />
                      <ellipse cx="50" cy="50" rx="30" ry="12" fill="url(#dbMetalRim)" stroke="#ff758f" strokeWidth="1" />

                      {/* Middle Cylinder Layer */}
                      <path d="M 20 35 L 20 50 C 20 62 80 62 80 50 L 80 35 C 80 47 20 47 20 35 Z" fill="url(#dbRedRadial)" stroke="#ff4d6d" strokeWidth="1.2" />
                      <ellipse cx="50" cy="35" rx="30" ry="12" fill="url(#dbMetalRim)" stroke="#ff758f" strokeWidth="1" />

                      {/* Top Cylinder Layer */}
                      <path d="M 20 20 L 20 35 C 20 47 80 47 80 35 L 80 20 C 80 32 20 32 20 20 Z" fill="url(#dbRedRadial)" stroke="#ff4d6d" strokeWidth="1.2" />
                      <ellipse cx="50" cy="20" rx="30" ry="12" fill="url(#dbRedRadial)" stroke="#ff758f" strokeWidth="1.5" />

                      {/* Status indicator dot */}
                      <circle cx="70" cy="32" r="2.5" fill="#ffccd5" className="animate-ping" />
                      <circle cx="70" cy="47" r="2.5" fill="#ffccd5" />
                    </svg>

                    {/* Glowing Red Warning Triangle Overlay */}
                    <div className="absolute -bottom-1 -right-1 bg-[#120408] rounded-xl p-0.5 border border-rose-500 shadow-[0_0_12px_rgba(244,63,94,0.8)]">
                      <AlertTriangle className="w-5 h-5 sm:w-6 sm:h-6 text-rose-400 fill-rose-500/20" />
                    </div>
                  </div>
                </motion.div>

                {/* Subtitle dưới Database */}
                <div className="mt-2 text-center">
                  <div className="text-[10px] sm:text-[11px] font-mono font-bold text-rose-300 truncate max-w-[110px]">
                    raw_payments.amount
                  </div>
                  <div className="text-[9px] text-rose-400/80 font-mono">
                    Nguồn phát sinh lỗi
                  </div>
                </div>
              </div>

              {/* KHU VỰC TIA SẤM SÉT THU GỌN - DỪNG CHÍNH XÁC TẠI MÉP TRÁI CỦA KHỐI ICON BÊN PHẢI */}
              <div className="absolute inset-0 pointer-events-none z-10 flex items-center justify-center">
                <svg className="w-full h-full overflow-visible" preserveAspectRatio="none" viewBox="0 0 500 300">
                  <defs>
                    <filter id="laserGlowRed" x="-20%" y="-20%" width="140%" height="140%">
                      <feGaussianBlur stdDeviation="3" result="glow" />
                      <feMerge>
                        <feMergeNode in="glow" />
                        <feMergeNode in="glow" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>

                    <linearGradient id="lightningGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="#ff4d6d" stopOpacity="1" />
                      <stop offset="60%" stopColor="#ff0054" stopOpacity="0.9" />
                      <stop offset="100%" stopColor="#ff758f" stopOpacity="1" />
                    </linearGradient>
                  </defs>

                  {/* Tia 1: Rẽ nhánh lên trên (Dừng tại mép trái icon Bar Chart x=280) */}
                  <motion.path
                    d="M 95 150 Q 135 145, 160 120 T 195 78 Q 225 62, 250 56 L 280 54"
                    fill="none"
                    stroke="url(#lightningGrad)"
                    strokeWidth="2.2"
                    filter="url(#laserGlowRed)"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    animate={{
                      strokeDashoffset: [0, -30, 0],
                      opacity: [0.8, 1, 0.75, 0.95],
                      strokeWidth: [2, 2.8, 2],
                    }}
                    transition={{
                      duration: 1.4,
                      repeat: Infinity,
                      ease: 'easeInOut',
                    }}
                  />
                  {/* Tia phụ rễ cây 1 */}
                  <motion.path
                    d="M 160 120 L 178 102 L 194 107"
                    fill="none"
                    stroke="#ff4d6d"
                    strokeWidth="1.1"
                    opacity="0.6"
                    animate={{ opacity: [0.2, 0.8, 0.3] }}
                    transition={{ duration: 1.1, repeat: Infinity }}
                  />

                  {/* Tia 2: Nhánh giữa thẳng ngang (Dừng tại mép trái icon Trend Line x=280) */}
                  <motion.path
                    d="M 95 150 Q 140 152, 175 144 T 215 156 Q 250 150, 270 150 L 280 150"
                    fill="none"
                    stroke="url(#lightningGrad)"
                    strokeWidth="2.6"
                    filter="url(#laserGlowRed)"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    animate={{
                      strokeDashoffset: [0, 25, 0],
                      opacity: [0.9, 0.7, 1, 0.85],
                      strokeWidth: [2.2, 3.2, 2.2],
                    }}
                    transition={{
                      duration: 1.2,
                      repeat: Infinity,
                      ease: 'easeInOut',
                    }}
                  />
                  {/* Tia phụ rễ cây 2 */}
                  <motion.path
                    d="M 215 156 L 232 170 L 246 165"
                    fill="none"
                    stroke="#ff4d6d"
                    strokeWidth="1.1"
                    opacity="0.6"
                    animate={{ opacity: [0.3, 0.9, 0.4] }}
                    transition={{ duration: 0.9, repeat: Infinity }}
                  />

                  {/* Tia 3: Rẽ nhánh xuống dưới (Dừng tại mép trái icon Pie Chart x=280) */}
                  <motion.path
                    d="M 95 150 Q 135 155, 160 185 T 195 228 Q 225 242, 250 244 L 280 246"
                    fill="none"
                    stroke="url(#lightningGrad)"
                    strokeWidth="2.2"
                    filter="url(#laserGlowRed)"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    animate={{
                      strokeDashoffset: [0, -35, 0],
                      opacity: [0.75, 1, 0.8, 1],
                      strokeWidth: [2, 2.8, 2],
                    }}
                    transition={{
                      duration: 1.5,
                      repeat: Infinity,
                      ease: 'easeInOut',
                    }}
                  />
                  {/* Tia phụ rễ cây 3 */}
                  <motion.path
                    d="M 160 185 L 178 206 L 192 200"
                    fill="none"
                    stroke="#ff4d6d"
                    strokeWidth="1.1"
                    opacity="0.6"
                    animate={{ opacity: [0.4, 0.85, 0.3] }}
                    transition={{ duration: 1.3, repeat: Infinity }}
                  />

                  {/* 3 ĐIỂM ĐIỆN TỬ PHÁT SÁNG NẰM CHÍNH XÁC TRƯỚC MÉP TRÁI CỦA 3 ICON */}
                  <motion.circle
                    cx="280"
                    cy="54"
                    r="4"
                    fill="#ffccd5"
                    filter="url(#laserGlowRed)"
                    animate={{ scale: [1, 1.5, 1], opacity: [0.8, 1, 0.8] }}
                    transition={{ duration: 1, repeat: Infinity }}
                  />
                  <motion.circle
                    cx="280"
                    cy="150"
                    r="4.5"
                    fill="#ffccd5"
                    filter="url(#laserGlowRed)"
                    animate={{ scale: [1, 1.6, 1], opacity: [0.9, 1, 0.9] }}
                    transition={{ duration: 0.9, repeat: Infinity }}
                  />
                  <motion.circle
                    cx="280"
                    cy="246"
                    r="4"
                    fill="#ffccd5"
                    filter="url(#laserGlowRed)"
                    animate={{ scale: [1, 1.5, 1], opacity: [0.8, 1, 0.8] }}
                    transition={{ duration: 1.1, repeat: Infinity }}
                  />
                </svg>
              </div>

              {/* CỘT PHẢI: 3 BIỂU ĐỒ BỊ LỖI - ĐÃ DỊCH SÁNG BÊN PHẢI VÀ ICON ĐÓN ĐẦU TIA SÉT Ở MÉP TRÁI */}
              <div className="relative z-20 flex flex-col justify-between space-y-3.5 sm:space-y-4 ml-auto pr-1 sm:pr-3">
                
                {/* 1. Bar Chart Bị Lệch Cột (Broken Bar Chart) */}
                <motion.div 
                  whileHover={{ scale: 1.03, x: 2 }}
                  className="flex items-center gap-3.5 group cursor-pointer"
                >
                  {/* Graphic Icon Container */}
                  <div className="relative w-12 h-12 sm:w-14 sm:h-14 rounded-2xl bg-[#140a12]/90 border border-rose-500/50 flex items-center justify-center p-1.5 shadow-[0_0_18px_rgba(244,63,94,0.35)] group-hover:border-rose-400 transition-all shrink-0">
                    <svg viewBox="0 0 50 50" className="w-full h-full">
                      {/* Axis */}
                      <path d="M 6 6 L 6 44 L 46 44" stroke="#ff4d6d" strokeWidth="2" fill="none" strokeLinecap="round" />
                      {/* Bar 1 */}
                      <rect x="11" y="22" width="6" height="20" rx="1.5" fill="#a4133c" stroke="#ff4d6d" strokeWidth="1" />
                      {/* Bar 2 (Crack & Jagged) */}
                      <path d="M 21 30 L 21 14 L 27 14 L 27 28 L 24 30 L 27 34 L 27 42 L 21 42 Z" fill="#800f2f" stroke="#ff4d6d" strokeWidth="1" />
                      {/* Bar 3 */}
                      <rect x="31" y="8" width="6" height="34" rx="1.5" fill="#a4133c" stroke="#ff4d6d" strokeWidth="1" />
                    </svg>

                    {/* Warning Triangle on top */}
                    <div className="absolute -bottom-1 -right-1 bg-[#1a050b] rounded-lg p-0.5 border border-rose-500 shadow-md">
                      <AlertTriangle className="w-3.5 h-3.5 text-rose-400 fill-rose-500/30" />
                    </div>
                  </div>

                  {/* Caption Text */}
                  <div className="min-w-0">
                    <div className="text-xs sm:text-sm font-bold font-mono text-rose-200 group-hover:text-white transition-colors truncate">
                      Lệch 42.8 tỷ VND
                    </div>
                    <div className="text-[10px] text-slate-400 font-mono truncate">
                      Looker Dashboard CEO
                    </div>
                  </div>
                </motion.div>

                {/* 2. Downward Jagged Trend Line (Gãy Chỉ Số) */}
                <motion.div 
                  whileHover={{ scale: 1.03, x: 2 }}
                  className="flex items-center gap-3.5 group cursor-pointer"
                >
                  {/* Graphic Icon Container */}
                  <div className="relative w-12 h-12 sm:w-14 sm:h-14 rounded-2xl bg-[#140a12]/90 border border-rose-500/50 flex items-center justify-center p-1.5 shadow-[0_0_18px_rgba(244,63,94,0.35)] group-hover:border-rose-400 transition-all shrink-0">
                    <svg viewBox="0 0 50 50" className="w-full h-full">
                      {/* Axis Box */}
                      <path d="M 6 6 L 6 44 L 46 44" stroke="#ff4d6d" strokeWidth="2" fill="none" strokeLinecap="round" />
                      {/* Downward Falling Jagged Trend */}
                      <path d="M 9 16 L 18 30 L 25 20 L 33 34 L 42 40" fill="none" stroke="#ff4d6d" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                      {/* Arrowhead */}
                      <path d="M 37 40 L 43 40 L 43 34" fill="none" stroke="#ff4d6d" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      {/* Shaded Area underneath */}
                      <path d="M 9 16 L 18 30 L 25 20 L 33 34 L 42 40 L 42 44 L 9 44 Z" fill="#590d22" opacity="0.6" />
                    </svg>

                    {/* Warning icon */}
                    <div className="absolute -bottom-1 -right-1 bg-[#1a050b] rounded-lg p-0.5 border border-rose-500 shadow-md">
                      <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
                    </div>
                  </div>

                  {/* Caption Text */}
                  <div className="min-w-0">
                    <div className="text-xs sm:text-sm font-bold font-mono text-rose-200 group-hover:text-white transition-colors truncate">
                      Trễ họp HĐQT 3 ngày
                    </div>
                    <div className="text-[10px] text-slate-400 font-mono truncate">
                      Báo cáo Dòng tiền Q3
                    </div>
                  </div>
                </motion.div>

                {/* 3. Cracked Broken Pie Chart (Vỡ Cơ Cấu) */}
                <motion.div 
                  whileHover={{ scale: 1.03, x: 2 }}
                  className="flex items-center gap-3.5 group cursor-pointer"
                >
                  {/* Graphic Icon Container */}
                  <div className="relative w-12 h-12 sm:w-14 sm:h-14 rounded-2xl bg-[#140a12]/90 border border-rose-500/50 flex items-center justify-center p-1.5 shadow-[0_0_18px_rgba(244,63,94,0.35)] group-hover:border-rose-400 transition-all shrink-0">
                    <svg viewBox="0 0 50 50" className="w-full h-full">
                      {/* Main Broken Pie Body */}
                      <path d="M 23 23 L 23 7 A 18 18 0 1 0 41 25 L 25 25 Z" fill="#800f2f" stroke="#ff4d6d" strokeWidth="1.5" />
                      {/* Detached Broken Pie Slice */}
                      <path d="M 29 20 L 43 14 A 18 18 0 0 0 29 7 Z" fill="#c9184a" stroke="#ff758f" strokeWidth="1.5" transform="translate(3, -2)" />
                      {/* Crack Line */}
                      <path d="M 23 23 L 15 35 L 18 41" stroke="#ff4d6d" strokeWidth="1.5" fill="none" />
                    </svg>

                    {/* Exclamation badge */}
                    <div className="absolute -top-1 -right-1 bg-[#1a050b] rounded-full p-0.5 border border-rose-500 shadow-md">
                      <AlertOctagon className="w-3.5 h-3.5 text-rose-400 fill-rose-500/30" />
                    </div>
                  </div>

                  {/* Caption Text */}
                  <div className="min-w-0">
                    <div className="text-xs sm:text-sm font-bold font-mono text-rose-200 group-hover:text-white transition-colors truncate">
                      Khiếu nại bảng lương
                    </div>
                    <div className="text-[10px] text-slate-400 font-mono truncate">
                      Bảng lương 14 chi nhánh
                    </div>
                  </div>
                </motion.div>

              </div>

            </div>

            {/* Bottom Solution Footer */}
            <div className="mt-6 pt-3.5 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-300">
              <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
                <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
                LineageAI phát hiện và chặn đứng rủi ro này từ bước tạo Pull Request.
              </span>
              <span className="font-mono text-cyan-400 font-bold hidden sm:inline">0 Gián đoạn</span>
            </div>

          </div>
        </motion.div>

      </div>
    </section>
  );
};
