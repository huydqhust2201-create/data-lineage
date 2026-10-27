import React, { useState, useEffect } from 'react';
import { LogIn, Play } from 'lucide-react';
import logoImg from '../../assets/logo.png';

interface HeaderProps {
  onLoginClick?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onLoginClick }) => {
  const [scrolled, setScrolled] = useState<boolean>(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <header
      className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 ${
        scrolled
          ? 'bg-[#080d1a]/95 backdrop-blur-xl border-b border-slate-800 py-3 shadow-md shadow-black/40'
          : 'bg-transparent py-5'
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between">
        
        {/* Brand Logo in Material 3 Style */}
        <a href="#hero" className="flex items-center gap-3 group">
          <div className="w-10 h-10 flex items-center justify-center">
            <img src={logoImg} alt="Lineage AI Logo" className="w-10 h-10 object-contain" />
          </div>
          <span className="text-lg font-bold text-white tracking-tight flex items-center gap-1">
            Lineage<span className="text-cyan-400">AI</span>
          </span>
        </a>

        {/* Action Buttons: Material 3 Pill Buttons (No click modal event) */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="inline-flex items-center gap-2 px-5 py-2 rounded-full text-xs font-semibold text-slate-200 hover:text-white bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/60 transition-all shadow-sm cursor-pointer"
          >
            <Play className="w-3.5 h-3.5 text-cyan-400 fill-cyan-400" />
            <span>Xem demo</span>
          </button>

          <button
            type="button"
            onClick={onLoginClick}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-full bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/25 transition-all cursor-pointer"
          >
            <span>Đăng nhập ngay</span>
          </button>
        </div>

      </div>
    </header>
  );
};
