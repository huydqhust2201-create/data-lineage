import React from 'react';
import { motion } from 'motion/react';
import { Play, LogIn, ArrowRight, CheckCircle2, Clock, Lock, Zap } from 'lucide-react';

const smoothTransition = {
  duration: 0.75,
  ease: [0.16, 1, 0.3, 1] as const,
};

interface FinalActionSectionProps {
  onLoginClick?: () => void;
}

export const FinalActionSection: React.FC<FinalActionSectionProps> = ({ onLoginClick }) => {
  return (
    <section id="cta" className="relative z-10 w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-20 md:py-28 overflow-hidden gpu-layer">
      
      {/* SCREEN 6 SIGNATURE EFFECT: Ambient Rotating Cosmic Glow Vortex */}
      <div className="absolute inset-0 pointer-events-none -z-10 flex items-center justify-center">
        <motion.div
          initial={{ rotate: 0, scale: 0.85, opacity: 0 }}
          whileInView={{ rotate: 360, scale: [0.85, 1.1, 0.85], opacity: [0.2, 0.45, 0.2] }}
          viewport={{ once: false, amount: 0.15 }}
          transition={{ duration: 18, repeat: Infinity, ease: 'linear' }}
          className="w-[700px] h-[400px] bg-gradient-to-r from-cyan-500/20 via-indigo-500/20 to-teal-500/20 blur-[110px] rounded-full transform-gpu"
        />
      </div>

      {/* M3 Elevated Surface Container (rounded-3xl: 28px) */}
      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.97 }}
        whileInView={{ opacity: 1, y: 0, scale: 1 }}
        viewport={{ once: false, amount: 0.15 }}
        transition={smoothTransition}
        className="relative overflow-hidden rounded-3xl p-8 sm:p-12 md:p-14 text-center border border-cyan-500/30 bg-gradient-to-b from-[#0e1628]/95 via-[#0a101d]/95 to-[#070b14]/95 backdrop-blur-2xl shadow-[0_0_70px_rgba(6,182,212,0.2)] transform-gpu"
      >
        {/* Glow backdrop overlay */}
        <div
          className="absolute -top-32 left-1/2 -translate-x-1/2 w-96 h-96 bg-cyan-500/25 rounded-full blur-[100px] pointer-events-none"
          aria-hidden="true"
        />

        {/* Content Box */}
        <div className="relative z-10 max-w-3xl mx-auto flex flex-col items-center">
          
          {/* M3 Badge Pill */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: false, amount: 0.15 }}
            transition={smoothTransition}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full border border-cyan-500/30 bg-cyan-500/10 text-cyan-300 text-xs font-semibold uppercase tracking-wider mb-5 shadow-[0_0_15px_rgba(6,182,212,0.3)] transform-gpu"
          >
            <Zap className="w-3.5 h-3.5 animate-bounce" />
            <span>Sẵn sàng chuyển đổi</span>
          </motion.div>

          {/* Headline */}
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: false, amount: 0.15 }}
            transition={{ ...smoothTransition, delay: 0.08 }}
            className="text-3xl sm:text-4xl md:text-5xl lg:text-5xl font-bold tracking-tight text-white leading-[1.15] transform-gpu"
          >
            Bảo vệ hệ thống dữ liệu{' '}
            <span className="bg-gradient-to-r from-cyan-400 via-teal-300 to-indigo-400 bg-clip-text text-transparent drop-shadow-[0_0_30px_rgba(6,182,212,0.3)]">
              ngay hôm nay.
            </span>
          </motion.h2>

          {/* Sub-headline */}
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: false, amount: 0.15 }}
            transition={{ ...smoothTransition, delay: 0.16 }}
            className="mt-4 text-base sm:text-lg text-slate-300 max-w-xl mx-auto leading-relaxed transform-gpu"
          >
            Thiết lập trong 5 phút. Tối ưu chi phí, không cần thẻ tín dụng.
          </motion.p>

          {/* M3 Action Pill Buttons (No modal click events) */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: false, amount: 0.15 }}
            transition={{ ...smoothTransition, delay: 0.24 }}
            className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4 w-full max-w-md sm:max-w-none transform-gpu"
          >
            
            {/* Primary M3 Button: Đăng nhập ngay */}
            <motion.button
              type="button"
              onClick={onLoginClick}
              whileHover={{ scale: 1.02, y: -2 }}
              whileTap={{ scale: 0.98 }}
              transition={{ type: 'spring', stiffness: 400, damping: 25 }}
              className="w-full sm:w-auto group relative inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-full bg-indigo-600 text-white font-semibold text-sm sm:text-base shadow-[0_0_30px_rgba(79,70,229,0.4)] hover:shadow-[0_0_50px_rgba(79,70,229,0.65)] hover:bg-indigo-500 cursor-pointer overflow-hidden transform-gpu"
            >
              <div className="absolute inset-0 -translate-x-full group-hover:translate-x-full bg-gradient-to-r from-transparent via-white/25 to-transparent transition-transform duration-700 pointer-events-none" />
              <span>Đăng nhập ngay</span>
              <ArrowRight className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-1" />
            </motion.button>

            {/* Secondary M3 Button: Xem demo */}
            <motion.button
              type="button"
              whileHover={{ scale: 1.02, y: -2 }}
              whileTap={{ scale: 0.98 }}
              transition={{ type: 'spring', stiffness: 400, damping: 25 }}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-full bg-slate-800/80 hover:bg-slate-700/80 text-white border border-slate-700/60 font-semibold text-sm sm:text-base backdrop-blur-md cursor-pointer shadow-md hover:border-cyan-500/40 transform-gpu"
            >
              <Play className="w-4 h-4 text-cyan-400 fill-cyan-400" />
              <span>Xem demo</span>
            </motion.button>

          </motion.div>

          {/* 3 Value Pillars — M3 Cards with smooth staggered entry */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: false, amount: 0.15 }}
            transition={{ ...smoothTransition, delay: 0.32 }}
            className="mt-10 pt-6 border-t border-slate-800 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs text-slate-300 max-w-xl w-full transform-gpu"
          >
            {[
              { icon: CheckCircle2, text: 'Không cần thẻ', color: 'text-emerald-400' },
              { icon: Clock, text: 'Cài đặt 5 phút', color: 'text-cyan-400' },
              { icon: Lock, text: 'Bảo mật tuyệt đối', color: 'text-purple-400' },
            ].map((pillar, idx) => {
              const Icon = pillar.icon;
              return (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, scale: 0.92 }}
                  whileInView={{ opacity: 1, scale: 1 }}
                  viewport={{ once: false, amount: 0.15 }}
                  transition={{ duration: 0.5, delay: 0.36 + idx * 0.08, ease: [0.16, 1, 0.3, 1] }}
                  whileHover={{ y: -2, scale: 1.02 }}
                  className="flex items-center justify-center gap-2 p-2.5 rounded-2xl bg-[#0e1628] border border-slate-700/50 transform-gpu shadow-sm"
                >
                  <Icon className={`w-4 h-4 ${pillar.color}`} />
                  <span className="font-medium text-slate-200">{pillar.text}</span>
                </motion.div>
              );
            })}
          </motion.div>

        </div>
      </motion.div>

    </section>
  );
};
