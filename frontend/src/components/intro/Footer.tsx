import React from 'react';
import logoImg from '../../assets/logo.png';
import { 
  Mail, 
  Phone, 
  MapPin, 
  ShieldCheck, 
  DollarSign, 
  FileText, 
  Lock, 
  CheckCircle2, 
  Globe
} from 'lucide-react';

export const Footer: React.FC = () => {
  return (
    <footer id="footer" className="w-full relative z-10 border-t border-slate-800/80 bg-[#060a12] text-slate-300 pt-16 pb-12 mt-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Main Footer Columns */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-10 pb-12 border-b border-slate-800/80">
          
          {/* Col 1: Brand & Contact Info (span 2 on large screens) */}
          <div className="lg:col-span-2 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 flex items-center justify-center">
                <img src={logoImg} alt="Lineage AI Logo" className="w-9 h-9 object-contain" />
              </div>
              <span className="font-bold text-xl tracking-tight text-white">
                Lineage<span className="text-cyan-400">AI</span>
              </span>
            </div>

            <p className="text-sm text-slate-400 leading-relaxed max-w-sm">
              Nền tảng kiểm soát phụ thuộc dữ liệu tự động, ngăn ngừa sự cố báo cáo cho Tech & Data Leader.
            </p>

            <div className="pt-2 space-y-2.5 text-xs text-slate-400">
              <div className="flex items-center gap-2.5 text-slate-300">
                <Mail className="w-4 h-4 text-cyan-400 shrink-0" />
                <span className="font-mono">contact@lineageai.io</span>
              </div>
              <div className="flex items-center gap-2.5 text-slate-300">
                <Phone className="w-4 h-4 text-cyan-400 shrink-0" />
                <span className="font-mono">+84 (024) 8888 6688</span>
              </div>
              <div className="flex items-center gap-2.5 text-slate-300">
                <MapPin className="w-4 h-4 text-cyan-400 shrink-0" />
                <span>302 Cầu Giấy, Hà Nội</span>
              </div>
            </div>
          </div>

          {/* Col 2: Bảng giá */}
          <div className="space-y-3.5">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white flex items-center gap-1.5 font-mono">
              <DollarSign className="w-3.5 h-3.5 text-cyan-400" />
              Bảng giá
            </h4>
            <ul className="space-y-2.5 text-sm text-slate-400">
              <li>
                <a href="#pricing-starter" className="hover:text-cyan-300 transition-colors block">
                  Gói Khởi động (14 ngày)
                </a>
              </li>
              <li>
                <a href="#pricing-growth" className="hover:text-cyan-300 transition-colors block">
                  Gói Đội ngũ (Growth)
                </a>
              </li>
              <li>
                <a href="#pricing-enterprise" className="hover:text-cyan-300 transition-colors block">
                  Gói Doanh nghiệp (On-Prem)
                </a>
              </li>
            </ul>
          </div>

          {/* Col 3: Tài liệu */}
          <div className="space-y-3.5">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white flex items-center gap-1.5 font-mono">
              <FileText className="w-3.5 h-3.5 text-cyan-400" />
              Tài liệu
            </h4>
            <ul className="space-y-2.5 text-sm text-slate-400">
              <li>
                <a href="#doc-setup" className="hover:text-cyan-300 transition-colors block">
                  Cài đặt 5 phút
                </a>
              </li>
              <li>
                <a href="#doc-integrations" className="hover:text-cyan-300 transition-colors block">
                  Tích hợp dbt & Airflow
                </a>
              </li>
              <li>
                <a href="#doc-blast-radius" className="hover:text-cyan-300 transition-colors block">
                  API Blast Radius
                </a>
              </li>
            </ul>
          </div>

          {/* Col 4: Bảo mật */}
          <div className="space-y-3.5">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5 font-mono">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              Bảo mật
            </h4>
            <ul className="space-y-2.5 text-sm text-slate-400">
              <li className="flex items-start gap-2">
                <Lock className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
                <span className="text-slate-300">Không lưu dữ liệu thô</span>
              </li>
              <li className="text-xs text-slate-400 leading-relaxed pl-5.5">
                Chỉ phân tích metadata AST. Dữ liệu luôn nằm trong VPC của bạn.
              </li>
              <li className="flex items-center gap-2 pt-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span className="text-slate-300 font-medium">SOC2 & GDPR</span>
              </li>
            </ul>
          </div>

        </div>

        {/* Bottom Bar: Copyright & Standard Links */}
        <div className="pt-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
          <div className="flex items-center gap-2 font-mono">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span>© {new Date().getFullYear()} LineageAI, Inc. Tất cả quyền được bảo lưu.</span>
          </div>

          <div className="flex flex-wrap items-center gap-5 text-slate-400">
            <a href="#terms" className="hover:text-cyan-300 transition-colors">
              Điều khoản dịch vụ
            </a>
            <a href="#privacy" className="hover:text-cyan-300 transition-colors">
              Chính sách bảo mật
            </a>
            <a href="#status" className="hover:text-cyan-300 transition-colors flex items-center gap-1.5">
              <Globe className="w-3 h-3 text-cyan-400" />
              <span>Trạng thái hệ thống</span>
            </a>
          </div>
        </div>

      </div>
    </footer>
  );
};
