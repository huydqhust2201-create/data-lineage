import React, { useState, useEffect } from 'react';
import { X, User, Mail, ShieldAlert, KeyRound, Check, Image } from 'lucide-react';

interface AccountSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaveSuccess: () => void;
}

const AVATAR_COLORS = [
  { name: 'Indigo-Purple', gradient: 'from-indigo-500 to-purple-650', value: 'indigo' },
  { name: 'Emerald-Teal', gradient: 'from-emerald-500 to-teal-600', value: 'emerald' },
  { name: 'Rose-Red', gradient: 'from-rose-500 to-red-650', value: 'rose' },
  { name: 'Amber-Orange', gradient: 'from-amber-500 to-orange-600', value: 'amber' },
  { name: 'Sky-Blue', gradient: 'from-sky-500 to-sky-655', value: 'sky' }
];

export const AccountSettingsModal: React.FC<AccountSettingsModalProps> = ({ isOpen, onClose, onSaveSuccess }) => {
  const [displayName, setDisplayName] = useState('Admin Account');
  const [email, setEmail] = useState('admin@lineage.ai');
  const [avatarColor, setAvatarColor] = useState('indigo');
  const [avatarFile, setAvatarFile] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [isSaved, setIsSaved] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setDisplayName(localStorage.getItem('user_display_name') || 'Admin Account');
      setEmail(localStorage.getItem('user_email') || 'admin@lineage.ai');
      setAvatarColor(localStorage.getItem('user_avatar_color') || 'indigo');
      setAvatarFile(localStorage.getItem('user_avatar_file'));
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword(''); setPasswordError(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleAvatarFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const r = new FileReader();
      r.onloadend = () => setAvatarFile(r.result as string);
      r.readAsDataURL(file);
    }
  };

  const handleSave = () => {
    if (currentPassword || newPassword || confirmPassword) {
      if (!currentPassword) return setPasswordError('Vui lòng nhập mật khẩu hiện tại.');
      if (newPassword.length < 6) return setPasswordError('Mật khẩu phải chứa ít nhất 6 ký tự.');
      if (newPassword !== confirmPassword) return setPasswordError('Mật khẩu xác nhận không trùng khớp.');
    }
    localStorage.setItem('user_display_name', displayName);
    localStorage.setItem('user_email', email);
    localStorage.setItem('user_avatar_color', avatarColor);
    if (avatarFile) localStorage.setItem('user_avatar_file', avatarFile);
    else localStorage.removeItem('user_avatar_file');

    setIsSaved(true);
    setTimeout(() => {
      setIsSaved(false);
      onSaveSuccess();
      onClose();
    }, 600);
  };

  const curColor = AVATAR_COLORS.find(c => c.value === avatarColor) || AVATAR_COLORS[0];
  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 dark:bg-black/60 backdrop-blur-md font-sans"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-sm bg-white/80 dark:bg-[#131A26]/80 backdrop-blur-xl border border-slate-200/50 dark:border-slate-800/40 rounded-[24px] shadow-2xl overflow-hidden flex flex-col">
        {/* Render header */}
        <div className="p-4 border-b border-slate-200/50 dark:border-slate-800/40 flex items-center justify-between bg-slate-50/50 dark:bg-slate-900/20">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 dark:bg-indigo-500/15 text-indigo-655 dark:text-indigo-400 flex items-center justify-center border border-indigo-500/20">
              <User className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-xs font-bold text-slate-900 dark:text-white">Account Settings</h2>
              <p className="text-[10px] text-slate-550 dark:text-slate-400 mt-0.5">Quản lý thông tin hồ sơ và thông tin bảo mật</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-slate-400 hover:text-slate-655 dark:hover:text-white hover:bg-slate-500/10 cursor-pointer transition-colors"><X className="w-4 h-4" /></button>
        </div>
        {/* body */}
        <div className="p-5 overflow-y-auto max-h-[65vh] space-y-4 text-xs text-slate-700 dark:text-slate-300 custom-scrollbar">
          {/* Avatar Section */}
          <div className="flex flex-col items-center pb-3 border-b border-slate-200/50 dark:border-slate-800/40">
            <div className="relative">
              {avatarFile ? (
                <img src={avatarFile} alt="Avatar" className="w-14 h-14 rounded-full object-cover border border-indigo-500/30" />
              ) : (
                <div className={`w-14 h-14 rounded-[18px] bg-gradient-to-br ${curColor.gradient} flex items-center justify-center text-white text-base font-bold shadow`}>
                  {displayName.charAt(0).toUpperCase() || 'A'}
                </div>
              )}
              <label className="absolute -bottom-1 -right-1 w-5.5 h-5.5 bg-indigo-600 hover:bg-indigo-500 rounded-full flex items-center justify-center text-white cursor-pointer border border-white dark:border-[#0B0F19] transition-transform hover:scale-105">
                <Image className="w-3 h-3" />
                <input type="file" accept="image/*" className="hidden" onChange={handleAvatarFileChange} />
              </label>
            </div>
            {avatarFile && <button onClick={() => setAvatarFile(null)} className="mt-1.5 text-[9px] text-rose-500 hover:underline cursor-pointer font-bold">Remove Image</button>}
            {!avatarFile && (
              <div className="mt-2 w-full flex flex-col items-center">
                <span className="text-[9px] font-bold text-slate-450 dark:text-slate-500 uppercase tracking-wider mb-1">Avatar Color</span>
                <div className="flex gap-1.5">
                  {AVATAR_COLORS.map(c => (
                    <button key={c.value} onClick={() => setAvatarColor(c.value)} className={`w-5 h-5 rounded-full bg-gradient-to-br ${c.gradient} cursor-pointer relative transition-transform hover:scale-110`}>
                      {avatarColor === c.value && <div className="absolute inset-0 flex items-center justify-center bg-black/25 rounded-full"><Check className="w-2.5 h-2.5 text-white" /></div>}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Text Fields */}
          <div className="space-y-3">
            <div>
              <label className="text-[9px] font-bold text-slate-450 dark:text-slate-500 uppercase tracking-widest block mb-0.5">Display Name</label>
              <div className="relative">
                <input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)} className="w-full pl-7.5 pr-2.5 py-1.5 rounded-lg bg-slate-50/50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800/50 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-550 focus:outline-none focus:border-indigo-500 font-semibold transition-all" />
                <User className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-slate-400" />
              </div>
            </div>
            <div>
              <label className="text-[9px] font-bold text-slate-450 dark:text-slate-500 uppercase tracking-widest block mb-0.5">Email</label>
              <div className="relative">
                <input type="email" value={email} onChange={e => setEmail(e.target.value)} className="w-full pl-7.5 pr-2.5 py-1.5 rounded-lg bg-slate-50/50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800/50 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-550 focus:outline-none focus:border-indigo-500 font-semibold transition-all" />
                <Mail className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-slate-400" />
              </div>
            </div>
          </div>

          {/* Password update section */}
          <div className="pt-3.5 border-t border-slate-200/50 dark:border-slate-800/40 space-y-2">
            <div className="flex items-center gap-1 text-slate-900 dark:text-white font-bold text-[10px]">
              <KeyRound className="w-3 h-3 text-indigo-500" />
              <span>Update Password</span>
            </div>
            {passwordError && (
              <div className="p-1.5 rounded-lg bg-rose-500/10 text-rose-650 dark:text-rose-400 text-[10px] flex items-center gap-1 border border-rose-500/20 font-semibold">
                <ShieldAlert className="w-3.5 h-3.5 shrink-0 text-rose-500" />
                <span>{passwordError}</span>
              </div>
            )}
            <div className="space-y-1.5">
              <input type="password" value={currentPassword} onChange={e => { setCurrentPassword(e.target.value); setPasswordError(null); }} placeholder="Mật khẩu hiện tại" className="w-full px-2.5 py-1.5 rounded-lg bg-slate-50/50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800/50 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-550 focus:outline-none focus:border-indigo-500 font-semibold transition-all" />
              <div className="grid grid-cols-2 gap-2">
                <input type="password" value={newPassword} onChange={e => { setNewPassword(e.target.value); setPasswordError(null); }} placeholder="Mật khẩu mới" className="w-full px-2.5 py-1.5 rounded-lg bg-slate-50/50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800/50 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-550 focus:outline-none focus:border-indigo-500 font-semibold transition-all" />
                <input type="password" value={confirmPassword} onChange={e => { setConfirmPassword(e.target.value); setPasswordError(null); }} placeholder="Xác nhận mật khẩu" className="w-full px-2.5 py-1.5 rounded-lg bg-slate-50/50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800/50 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-550 focus:outline-none focus:border-indigo-500 font-semibold transition-all" />
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-slate-200/50 dark:border-slate-800/40 bg-slate-50/50 dark:bg-slate-900/20 flex items-center justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg text-xs font-bold text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900/60 cursor-pointer transition-colors">Cancel</button>
          <button onClick={handleSave} disabled={isSaved} className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white flex items-center gap-1 transition-all cursor-pointer disabled:opacity-75 shadow-md">
            {isSaved ? <><Check className="w-3.5 h-3.5 text-white" /><span>Đã lưu</span></> : <span>Save Changes</span>}
          </button>
        </div>
      </div>
    </div>
  );
};
