import React, { useState } from 'react';
import { GoogleLogin, GoogleOAuthProvider } from '@react-oauth/google';
import { login, loginWithGoogle, register, TokenResponse } from '../../api/auth';
import { ApiError } from '../../api/http';
import logoImg from '../../assets/logo.png';
import { Mail, Lock, Eye, EyeOff, User, ArrowRight, ArrowLeft, Check, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface LandingPageProps {
  onLogin: (result: TokenResponse) => void;
  onBackToIntro?: () => void;
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? '';

const DEMO_ACCOUNTS = [
  { email: 'engineer@example.com', password: 'password123', role: 'Chủ sở hữu database "default"' },
  { email: 'viewer@example.com', password: 'password123', role: 'Chỉ xem' },
];

export const LandingPage: React.FC<LandingPageProps> = ({ onLogin, onBackToIntro }) => {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPasswordLogin, setShowPasswordLogin] = useState(false);
  const [showPasswordRegister, setShowPasswordRegister] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [agreeTerms, setAgreeTerms] = useState(false);

  const isSignUp = mode === 'register';

  const describeError = (err: unknown): string => {
    if (err instanceof ApiError) {
      if (err.status === 409) return 'Email này đã được đăng ký.';
      if (err.status === 401) return 'Email hoặc mật khẩu không đúng.';
      if (err.status === 422) return 'Mật khẩu cần ít nhất 8 ký tự.';
      return err.message;
    }
    return err instanceof Error ? err.message : 'Đã xảy ra lỗi, vui lòng thử lại.';
  };

  const handleAuthAction = async (actionMode: 'login' | 'register', e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    if (actionMode === 'register' && !agreeTerms) {
      setError('Bạn cần đồng ý với Điều khoản & Chính sách bảo mật.');
      setLoading(false);
      return;
    }
    try {
      const result = actionMode === 'login'
        ? await login(email, password)
        : await register(email, password, displayName || undefined);
      onLogin(result);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  };


  const handleGoogleSuccess = async (credential?: string) => {
    if (!credential) {
      setError('Không nhận được thông tin đăng nhập từ Google.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const result = await loginWithGoogle(credential);
      onLogin(result);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  };

  const overlayVariants = {
    signIn: { 
      x: '100%', 
      rotateY: 0, 
      scale: 1, 
      borderRadius: '0px 40px 40px 0px',
      transition: { duration: 1.0, ease: [0.6, 0.05, 0.1, 0.9] as any }
    },
    signUp: { 
      x: '0%', 
      rotateY: 0, 
      scale: 1, 
      borderRadius: '40px 0px 0px 40px',
      transition: { duration: 1.0, ease: [0.6, 0.05, 0.1, 0.9] as any }
    },
    exit: (customMode: 'login' | 'register') => ({
      x: customMode === 'login' ? 'calc(100% + 800px)' : '-800px',
      opacity: 0,
      transition: { duration: 0.75, ease: [0.7, 0, 0.3, 1] as any }
    })
  };

  return (
    <motion.div
      initial={{ backgroundColor: 'rgba(0, 0, 0, 1)' }}
      exit={{ backgroundColor: 'rgba(0, 0, 0, 0)', backdropFilter: 'blur(0px)' }}
      transition={{ duration: 0.75, ease: 'easeInOut' }}
      className="fixed inset-0 z-[10000] flex items-center justify-center overflow-y-auto font-sans p-4 bg-black select-none"
    >
      <div className="relative z-10 w-full flex items-center justify-center">
        <div className="relative w-[900px] h-[600px] flex select-none" style={{ perspective: '1200px' }}>
          
          {/* LEFT HALF CARD */}
          <motion.div
            initial={{ x: 0 }}
            exit={{ x: -800, opacity: 0 }}
            transition={{ duration: 0.75, ease: [0.7, 0, 0.3, 1] }}
            style={{ willChange: 'transform, opacity' }}
            className="w-1/2 h-full bg-[#0B0F19] border-y border-l border-[#1E293B] rounded-l-[2.5rem] relative overflow-hidden"
          >
            <div className={`absolute inset-0 p-12 flex flex-col justify-between transition-all duration-500 ease-in-out ${isSignUp ? 'opacity-0 pointer-events-none' : 'opacity-100 pointer-events-auto'}`}>
              <div>
                <div className="flex items-center gap-2 cursor-pointer mb-6" onClick={onBackToIntro}>
                  <img src={logoImg} alt="Lineage AI Logo" className="w-6 h-6 object-contain" />
                  <span className="font-bold text-white text-sm tracking-tight">Lineage<span className="text-indigo-400">AI</span></span>
                </div>
                <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">YOUR WORKSPACE AWAITS</span>
                <h2 className="text-3xl font-extrabold text-white tracking-tight mt-1">Welcome back</h2>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">Đăng nhập để tiếp tục quản trị dòng chảy dữ liệu của bạn.</p>
              </div>
            
            <form onSubmit={(e) => handleAuthAction('login', e)} className="space-y-4 my-auto">
              <div className="space-y-1">
                <label className="block text-xs font-semibold text-slate-300">Email address</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500"><Mail className="w-4 h-4" /></div>
                  <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-full pl-10 pr-4 py-2 bg-[#131926] border border-[#222E45] rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:bg-[#131926] transition-all" placeholder="you@company.com" />
                </div>
              </div>
              <div className="space-y-1">
                <label className="block text-xs font-semibold text-slate-300">Password</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500"><Lock className="w-4 h-4" /></div>
                  <input type={showPasswordLogin ? 'text' : 'password'} required value={password} onChange={(e) => setPassword(e.target.value)} className="w-full pl-10 pr-10 py-2 bg-[#131926] border border-[#222E45] rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:bg-[#131926] transition-all" placeholder="Enter your password" />
                  <button type="button" onClick={() => setShowPasswordLogin(!showPasswordLogin)} className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-500 hover:text-slate-300 cursor-pointer">{showPasswordLogin ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
                </div>
              </div>
              <div className="flex items-center justify-between text-xs">
                <label className="flex items-center gap-2 text-slate-300 font-medium cursor-pointer">
                  <input type="checkbox" checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)} className="w-4 h-4 border border-slate-700 rounded text-indigo-600 focus:ring-indigo-500 accent-indigo-600 cursor-pointer bg-[#131926]" />
                  Remember me
                </label>
                <a href="#forgot" onClick={(e) => { e.preventDefault(); alert('Chức năng quên mật khẩu chưa được cấu hình.'); }} className="text-indigo-400 hover:text-indigo-300 font-semibold transition-colors">Forgot password?</a>
              </div>
              {error && !isSignUp && (
                <div className="flex items-center gap-2 text-red-400 bg-red-950/30 border border-red-900/50 rounded-xl px-3.5 py-2 text-xs">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{error}</span>
                </div>
              )}
              <button type="submit" disabled={loading} className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-sm font-semibold transition-all shadow-lg shadow-indigo-600/10 cursor-pointer flex items-center justify-center gap-2 active:scale-[0.99]">{loading && !isSignUp ? 'Signing in...' : 'Sign in'}<ArrowRight className="w-4 h-4" /></button>
            </form>
            <div className="space-y-1.5 mt-4">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Tài khoản dùng thử</span>
                <span className="text-[9px] text-indigo-400 font-semibold bg-indigo-950/40 border border-indigo-900/30 px-1.5 py-0.5 rounded">Demo account</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {DEMO_ACCOUNTS.map((account) => (
                  <button key={account.email} type="button" onClick={() => { setEmail(account.email); setPassword(account.password); setError(''); }} className="text-left px-2.5 py-1.5 rounded-lg bg-[#131926]/60 border border-[#222E45] hover:border-indigo-500 hover:bg-indigo-950/10 transition-all cursor-pointer group">
                    <div className="text-[10px] text-slate-300 font-semibold font-mono truncate group-hover:text-indigo-400">{account.email}</div>
                    <div className="text-[8px] text-slate-500 truncate">{account.role}</div>
                  </button>
                ))}
              </div>
            </div>
            </div>
          </motion.div>

          {/* RIGHT HALF CARD */}
          <motion.div
            initial={{ x: 0 }}
            exit={{ x: 800, opacity: 0 }}
            transition={{ duration: 0.75, ease: [0.7, 0, 0.3, 1] }}
            style={{ willChange: 'transform, opacity' }}
            className="w-1/2 h-full bg-[#0B0F19] border-y border-r border-[#1E293B] rounded-r-[2.5rem] relative overflow-hidden"
          >
            <div className={`absolute inset-0 p-12 flex flex-col justify-between transition-all duration-500 ease-in-out ${!isSignUp ? 'opacity-0 pointer-events-none' : 'opacity-100 pointer-events-auto'}`}>
              <div>
                <div className="flex items-center gap-2 cursor-pointer mb-6" onClick={onBackToIntro}>
                  <img src={logoImg} alt="Lineage AI Logo" className="w-6 h-6 object-contain" />
                  <span className="font-bold text-white text-sm tracking-tight">Lineage<span className="text-indigo-400">AI</span></span>
                </div>
                <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">START BUILDING IN MINUTES</span>
                <h2 className="text-3xl font-extrabold text-white tracking-tight mt-1">Create your account</h2>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">Đăng ký tài khoản để bắt đầu kết xuất và phân tích tác động rủi ro tự động.</p>
              </div>

            <form onSubmit={(e) => handleAuthAction('register', e)} className="space-y-4 my-auto">
              <div className="space-y-1">
                <label className="block text-xs font-semibold text-slate-300">Full name</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500"><User className="w-4 h-4" /></div>
                  <input type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)} className="w-full pl-10 pr-4 py-2 bg-[#131926] border border-[#222E45] rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:bg-[#131926] transition-all" placeholder="Ada Lovelace" />
                </div>
              </div>
              <div className="space-y-1">
                <label className="block text-xs font-semibold text-slate-300">Email address</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500"><Mail className="w-4 h-4" /></div>
                  <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-full pl-10 pr-4 py-2 bg-[#131926] border border-[#222E45] rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:bg-[#131926] transition-all" placeholder="you@company.com" />
                </div>
              </div>
              <div className="space-y-1">
                <label className="block text-xs font-semibold text-slate-300">Password</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500"><Lock className="w-4 h-4" /></div>
                  <input type={showPasswordRegister ? 'text' : 'password'} required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} className="w-full pl-10 pr-10 py-2 bg-[#131926] border border-[#222E45] rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:bg-[#131926] transition-all" placeholder="At least 8 characters" />
                  <button type="button" onClick={() => setShowPasswordRegister(!showPasswordRegister)} className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-500 hover:text-slate-300 cursor-pointer">{showPasswordRegister ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
                </div>
                <span className="block text-[10px] text-slate-500 mt-1">Mật khẩu dài từ 8 kí tự trở lên.</span>
              </div>
              <div className="flex items-start text-xs pt-1">
                <label className="flex items-start gap-2.5 text-slate-300 font-medium cursor-pointer">
                  <input type="checkbox" required checked={agreeTerms} onChange={(e) => setAgreeTerms(e.target.checked)} className="w-4 h-4 border border-slate-700 rounded text-indigo-600 focus:ring-indigo-500 accent-indigo-600 cursor-pointer bg-[#131926] mt-0.5" />
                  <span>Tôi đồng ý với <a href="#terms" onClick={(e) => { e.preventDefault(); alert('Các điều khoản và chính sách đang được cập nhật.'); }} className="text-indigo-400 hover:text-indigo-300 font-semibold transition-colors">Terms of Service</a> và <a href="#privacy" onClick={(e) => { e.preventDefault(); alert('Các điều khoản và chính sách đang được cập nhật.'); }} className="text-indigo-400 hover:text-indigo-300 font-semibold transition-colors">Privacy Policy</a></span>
                </label>
              </div>
              {error && isSignUp && (
                <div className="flex items-center gap-2 text-red-400 bg-red-950/30 border border-red-900/50 rounded-xl px-3.5 py-2 text-xs">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{error}</span>
                </div>
              )}
              <button type="submit" disabled={loading} className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-sm font-semibold transition-all shadow-lg shadow-indigo-600/10 cursor-pointer flex items-center justify-center gap-2 active:scale-[0.99]">{loading && isSignUp ? 'Creating account...' : 'Create account'}<ArrowRight className="w-4 h-4" /></button>
            </form>
            <div className="text-[10px] text-slate-500 text-center select-none pt-4 shrink-0">Bằng cách đăng ký, bạn xác nhận đồng ý với mọi chính sách của chúng tôi.</div>
          </div>
        </motion.div>

        {/* MIDDLE SLIDING 3D OVERLAY PANEL */}
        <motion.div
          custom={mode}
          variants={overlayVariants}
          animate={isSignUp ? 'signUp' : 'signIn'}
          exit="exit"
          className="absolute top-0 left-0 w-1/2 h-full bg-gradient-to-br from-indigo-600 via-indigo-700 to-blue-700 text-white z-20 origin-center flex flex-col justify-between p-12 select-none"
          style={{ transformStyle: 'preserve-3d', willChange: 'transform, opacity' }}
        >
          <div></div>

            <AnimatePresence mode="wait">
              {!isSignUp ? (
                <motion.div key="new-here" initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -30 }} transition={{ duration: 0.5, ease: 'easeInOut' }} className="flex flex-col items-center text-center space-y-6 my-auto">
                  <motion.div animate={{ y: [-8, 8] }} transition={{ repeat: Infinity, repeatType: 'reverse', duration: 3, ease: 'easeInOut' }} className="relative w-40 h-40 bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 shadow-2xl flex items-center justify-center flex-col p-4">
                    <div className="w-20 h-20 bg-white/20 rounded-full flex items-center justify-center text-white"><User className="w-10 h-10" /></div>
                    <div className="absolute -top-2.5 -left-2.5 w-8 h-8 bg-white text-indigo-600 rounded-xl shadow-lg flex items-center justify-center"><Check className="w-4 h-4 font-bold" /></div>
                    <div className="absolute -bottom-2.5 -right-2.5 px-2.5 py-1 bg-white text-slate-800 rounded-xl shadow-lg flex items-center justify-center font-bold text-[10px] gap-0.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>ID: ENGR
                    </div>
                  </motion.div>
                  <div className="space-y-2">
                    <span className="text-[10px] font-bold text-indigo-200 uppercase tracking-widest">MAKE IT YOURS</span>
                    <h2 className="text-3xl font-extrabold text-white tracking-tight">New here?</h2>
                    <p className="text-xs text-indigo-100/80 max-w-[280px] leading-relaxed mx-auto">Tạo không gian làm việc mới, lưu trữ dự án và quản lý dòng chảy dữ liệu tự động.</p>
                  </div>
                  <button type="button" onClick={() => { setMode('register'); setError(''); }} className="px-6 py-2.5 border border-white/40 hover:border-white rounded-xl text-xs font-semibold text-white bg-transparent hover:bg-white/10 transition-all cursor-pointer flex items-center gap-1.5 active:scale-95 duration-150">Create account<ArrowRight className="w-3.5 h-3.5" /></button>
                </motion.div>
              ) : (
                <motion.div key="already-account" initial={{ opacity: 0, x: -30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 30 }} transition={{ duration: 0.5, ease: 'easeInOut' }} className="flex flex-col items-center text-center space-y-6 my-auto">
                  <motion.div animate={{ y: [-8, 8] }} transition={{ repeat: Infinity, repeatType: 'reverse', duration: 3, ease: 'easeInOut' }} className="relative w-40 h-40 bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 shadow-2xl flex items-center justify-center flex-col p-4">
                    <div className="w-20 h-20 bg-white/25 rounded-full flex items-center justify-center text-white"><User className="w-10 h-10" /></div>
                    <div className="absolute -top-2.5 -left-2.5 w-8 h-8 bg-white text-emerald-500 rounded-xl shadow-lg flex items-center justify-center"><ArrowRight className="w-4 h-4" /></div>
                    <div className="absolute -bottom-2.5 -right-2.5 w-8 h-8 bg-white text-slate-800 rounded-xl shadow-lg flex items-center justify-center font-bold text-base">+</div>
                  </motion.div>
                  <div className="space-y-2">
                    <span className="text-[10px] font-bold text-indigo-200 uppercase tracking-widest">GOOD TO SEE YOU</span>
                    <h2 className="text-3xl font-extrabold text-white tracking-tight">Already have an account?</h2>
                    <p className="text-xs text-indigo-100/80 max-w-[280px] leading-relaxed mx-auto">Dự án và dữ liệu của bạn vẫn an toàn. Đăng nhập để tiếp tục công việc.</p>
                  </div>
                  <button type="button" onClick={() => { setMode('login'); setError(''); }} className="px-6 py-2.5 border border-white/40 hover:border-white rounded-xl text-xs font-semibold text-white bg-transparent hover:bg-white/10 transition-all cursor-pointer flex items-center gap-1.5 active:scale-95 duration-150"><ArrowLeft className="w-3.5 h-3.5" />Back to sign in</button>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="text-center mt-auto">
              <span className="text-[10px] text-indigo-200/60 uppercase tracking-wider font-semibold">{mode === 'login' ? 'Free to start - No card needed' : 'Secure access | Always in sync'}</span>
            </div>
          </motion.div>
        </div>
      </div>
    </motion.div>
  );
};
