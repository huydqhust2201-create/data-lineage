import React from 'react';
import { motion } from 'motion/react';
import { 
  Play, 
  LogIn, 
  ShieldCheck, 
  ArrowRight, 
  GitBranch, 
  Database, 
  CheckCircle2, 
  ChevronRight,
  Server,
  Layers,
  Cpu,
  BarChart3,
  Sparkles,
  Zap,
  Lock
} from 'lucide-react';

const smoothTransition = {
  duration: 0.75,
  ease: [0.16, 1, 0.3, 1] as const,
};

interface HeroSectionLeaderProps {
  onLoginClick?: () => void;
}

export const HeroSectionLeader: React.FC<HeroSectionLeaderProps> = ({ onLoginClick }) => {
  return (
    <section id="hero" className="relative z-10 w-full min-h-[92vh] flex flex-col items-center justify-center px-4 sm:px-6 lg:px-8 pt-24 pb-16 text-center overflow-hidden gpu-layer">
      
      {/* SCREEN 1 SIGNATURE EFFECT: Ambient Cyber Grid & Light Beams */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden -z-10">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: false, amount: 0.15 }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[400px] bg-gradient-to-tr from-cyan-500/20 via-blue-600/15 to-indigo-500/10 blur-[100px] rounded-full transform-gpu"
        />
        
        {/* Horizontal Laser Scanning Line */}
        <motion.div
          initial={{ x: '-100%', opacity: 0 }}
          whileInView={{ x: '100%', opacity: [0, 0.8, 0] }}
          viewport={{ once: false, amount: 0.15 }}
          transition={{ duration: 3.5, ease: 'easeInOut', repeat: Infinity, repeatDelay: 2 }}
          className="absolute top-1/2 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-cyan-400 to-transparent transform-gpu pointer-events-none"
        />
      </div>

      {/* Decorative M3 Assist Chip */}
      <motion.div
        initial={{ opacity: 0, y: -20, scale: 0.95 }}
        whileInView={{ opacity: 1, y: 0, scale: 1 }}
        viewport={{ once: false, amount: 0.15 }}
        transition={smoothTransition}
        className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-cyan-500/30 bg-cyan-500/10 text-cyan-300 text-xs font-medium backdrop-blur-md mb-6 shadow-[0_0_25px_rgba(6,182,212,0.2)] transform-gpu"
      >
        <span className="flex h-2 w-2 relative">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
        </span>
        <span className="tracking-wide">Quản trị luồng dữ liệu thế hệ mới cho Tech & Data Leader</span>
        <ChevronRight className="w-3.5 h-3.5 text-cyan-400/80" />
      </motion.div>

      {/* Main Headline with Material 3 Display Scale */}
      <motion.h1
        initial={{ opacity: 0, y: 25 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: false, amount: 0.15 }}
        transition={{ ...smoothTransition, delay: 0.08 }}
        className="max-w-4xl text-3xl sm:text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight text-white leading-[1.15] transform-gpu"
      >
        Nắm trọn dòng chảy dữ liệu.{' '}
        <span className="block mt-1 sm:mt-2 bg-gradient-to-r from-cyan-400 via-teal-300 to-indigo-400 bg-clip-text text-transparent drop-shadow-[0_0_35px_rgba(6,182,212,0.3)]">
          Loại bỏ sự cố báo cáo.
        </span>
      </motion.h1>

      {/* Sub-headline: Ngắn gọn, súc tích */}
      <motion.p
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: false, amount: 0.15 }}
        transition={{ ...smoothTransition, delay: 0.16 }}
        className="mt-4 max-w-2xl text-sm sm:text-base md:text-lg text-slate-300 leading-relaxed font-normal transform-gpu"
      >
        Tự động vẽ bản đồ phụ thuộc dữ liệu từ mã nguồn. Tự tin thay đổi hệ thống mà không làm gián đoạn quyết định kinh doanh.
      </motion.p>

      {/* M3 Action Pill Buttons */}
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        whileInView={{ opacity: 1, y: 0, scale: 1 }}
        viewport={{ once: false, amount: 0.15 }}
        transition={{ ...smoothTransition, delay: 0.22 }}
        className="mt-7 flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 w-full max-w-md sm:max-w-none transform-gpu"
      >
        <motion.button
          type="button"
          onClick={onLoginClick}
          whileHover={{ scale: 1.02, y: -2 }}
          whileTap={{ scale: 0.98 }}
          transition={{ type: 'spring', stiffness: 400, damping: 25 }}
          className="w-full sm:w-auto group relative inline-flex items-center justify-center gap-2 px-7 py-3 rounded-full bg-indigo-600 text-white font-semibold text-sm shadow-[0_0_30px_rgba(79,70,229,0.35)] hover:shadow-[0_0_45px_rgba(79,70,229,0.6)] hover:bg-indigo-500 cursor-pointer overflow-hidden transform-gpu"
        >
          <span>Đăng nhập ngay</span>
          <ArrowRight className="w-3.5 h-3.5 transition-transform duration-300 group-hover:translate-x-1" />
        </motion.button>

        <motion.button
          type="button"
          whileHover={{ scale: 1.02, y: -2 }}
          whileTap={{ scale: 0.98 }}
          transition={{ type: 'spring', stiffness: 400, damping: 25 }}
          className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-7 py-3 rounded-full bg-slate-800/80 hover:bg-slate-700/80 text-white border border-slate-700/60 font-semibold text-sm backdrop-blur-md cursor-pointer shadow-md hover:border-cyan-500/40 transform-gpu"
        >
          <Play className="w-4 h-4 text-cyan-400 fill-cyan-400" />
          <span>Xem demo</span>
        </motion.button>
      </motion.div>

    </section>
  );
};
