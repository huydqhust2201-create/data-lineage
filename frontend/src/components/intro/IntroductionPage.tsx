import React from 'react';
import { Header } from './Header';
import { HeroSectionLeader } from './leader/HeroSectionLeader';
import { RiskImpactSection } from './leader/RiskImpactSection';
import { AccuracyTrustSection } from './leader/AccuracyTrustSection';
import { ProductivityLineageSection } from './leader/ProductivityLineageSection';
import { AIAssistantSection } from './leader/AIAssistantSection';
import { FinalActionSection } from './leader/FinalActionSection';
import { Footer } from './Footer';
import { ContinuousBackground } from './ContinuousBackground';

interface IntroductionPageProps {
  onLoginClick: () => void;
}

export const IntroductionPage: React.FC<IntroductionPageProps> = ({ onLoginClick }) => {
  return (
    <div className="relative min-h-screen bg-[#070b14] text-slate-100 selection:bg-cyan-500 selection:text-white antialiased overflow-x-hidden">
      
      {/* Root SVG Noise Filter for polished shiny/glow surfaces */}
      <svg width="0" height="0" className="absolute pointer-events-none" aria-hidden="true">
        <defs>
          <filter id="c3-noise">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.9"
              numOctaves="2"
              stitchTiles="stitch"
            />
            <feColorMatrix
              type="matrix"
              values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0 0.35 0"
            />
            <feComposite in2="SourceGraphic" operator="in" result="noise" />
            <feBlend in="SourceGraphic" in2="noise" mode="multiply" />
          </filter>
        </defs>
      </svg>

      {/* Global Cinematic Looping Background with Guide Lines & Interactive Node Graph */}
      <ContinuousBackground />

      {/* Fixed Sticky Header Navigation */}
      <Header onLoginClick={onLoginClick} />

      {/* 6-Screen Streamlined Structure for Leader with Material Design 3 */}
      <main className="relative z-10 flex flex-col items-center w-full">
        
        {/* Màn 1: Hero Section (Căn giữa - Centered) */}
        <HeroSectionLeader onLoginClick={onLoginClick} />

        {/* Màn 2: Rủi ro kinh doanh & Chi phí (Chữ Trái 40% — Hình Phải 60%) */}
        <RiskImpactSection />

        {/* Màn 3: Độ chính xác & Đáng tin cậy (Hình Trái 60% — Chữ Phải 40%) */}
        <AccuracyTrustSection />

        {/* Màn 4: Tối ưu năng suất đội ngũ (Chữ Trái 40% — Hình Phải 60%) */}
        <ProductivityLineageSection />

        {/* Màn 5: Tra cứu tức thì qua Trợ lý ảo (Hình Trái 60% — Chữ Phải 40%) */}
        <AIAssistantSection />

        {/* Màn 6: Lời kêu gọi hành động (Căn giữa - Centered) */}
        <FinalActionSection onLoginClick={onLoginClick} />

      </main>

      {/* Footer M3 (Bảng giá, Tài liệu, Bảo mật với chuyển hướng trực tiếp đến các màn hình) */}
      <Footer />

    </div>
  );
};
