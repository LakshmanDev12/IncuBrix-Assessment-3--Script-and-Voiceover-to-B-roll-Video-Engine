import React from 'react';
import {
  Film,
  Briefcase,
  Activity,
  History,
  Search,
  Sparkles,
  ExternalLink,
} from 'lucide-react';
import type { StudioMode } from '../types';

interface HeaderProps {
  studioMode: StudioMode;
  onModeChange: (mode: StudioMode) => void;
  activeTab: 'studio' | 'history' | 'explorer' | 'status';
  onTabChange: (tab: 'studio' | 'history' | 'explorer' | 'status') => void;
  isBackendHealthy: boolean | null;
}

export const Header: React.FC<HeaderProps> = ({
  studioMode,
  onModeChange,
  activeTab,
  onTabChange,
  isBackendHealthy,
}) => {
  const isCreative = studioMode === 'creative';

  return (
    <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand / Logo */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 cursor-pointer" onClick={() => onTabChange('studio')}>
            <div
              className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold text-white shadow-lg transition-all duration-300 ${
                isCreative
                  ? 'bg-gradient-to-tr from-fuchsia-600 via-pink-600 to-amber-500 shadow-pink-500/20'
                  : 'bg-gradient-to-tr from-blue-700 via-indigo-600 to-cyan-500 shadow-indigo-500/20'
              }`}
            >
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-lg tracking-tight text-white">IncuBrix</span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium transition-colors ${
                    isCreative
                      ? 'bg-fuchsia-950/80 text-fuchsia-300 border border-fuchsia-700/50'
                      : 'bg-indigo-950/80 text-indigo-300 border border-indigo-700/50'
                  }`}
                >
                  AI Video Studio
                </span>
              </div>
              <p className="text-[11px] text-slate-400 hidden sm:block">
                Dual-Mode Video Engine & Provenance Pipeline
              </p>
            </div>
          </div>
        </div>

        {/* Center: Dual-Mode Toggle */}
        <div className="flex items-center bg-slate-900/90 p-1 rounded-xl border border-slate-800">
          <button
            type="button"
            onClick={() => onModeChange('creative')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200 cursor-pointer ${
              isCreative
                ? 'bg-gradient-to-r from-fuchsia-600 to-pink-600 text-white shadow-md shadow-pink-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Film className="w-3.5 h-3.5" />
            <span>Creative Studio</span>
          </button>

          <button
            type="button"
            onClick={() => onModeChange('professional')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200 cursor-pointer ${
              !isCreative
                ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md shadow-indigo-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Briefcase className="w-3.5 h-3.5" />
            <span>Professional Studio</span>
          </button>
        </div>

        {/* Navigation Tabs & Health Indicator */}
        <div className="flex items-center gap-2 sm:gap-4">
          <nav className="flex items-center gap-1 bg-slate-900/50 p-1 rounded-lg border border-slate-800/80">
            <button
              type="button"
              onClick={() => onTabChange('studio')}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition cursor-pointer ${
                activeTab === 'studio'
                  ? 'bg-slate-800 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Studio
            </button>
            <button
              type="button"
              onClick={() => onTabChange('history')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition cursor-pointer ${
                activeTab === 'history'
                  ? 'bg-slate-800 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <History className="w-3.5 h-3.5" />
              <span>Jobs</span>
            </button>
            <button
              type="button"
              onClick={() => onTabChange('explorer')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition cursor-pointer ${
                activeTab === 'explorer'
                  ? 'bg-slate-800 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Search className="w-3.5 h-3.5" />
              <span className="hidden md:inline">B-Roll</span>
            </button>
            <button
              type="button"
              onClick={() => onTabChange('status')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition cursor-pointer ${
                activeTab === 'status'
                  ? 'bg-slate-800 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              <span className="hidden md:inline">Health</span>
            </button>
          </nav>

          {/* Engine Health Pulse */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border ${
              isBackendHealthy === true
                ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/60'
                : isBackendHealthy === false
                ? 'bg-rose-950/60 text-rose-400 border-rose-800/60'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}
            title={
              isBackendHealthy === true
                ? 'Backend Engine Online & Ready (127.0.0.1:8000)'
                : 'Engine Disconnected — Check backend service'
            }
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isBackendHealthy === true
                  ? 'bg-emerald-400 animate-pulse'
                  : isBackendHealthy === false
                  ? 'bg-rose-400'
                  : 'bg-slate-400'
              }`}
            />
            <span className="hidden lg:inline">
              {isBackendHealthy === true ? 'Engine Online' : isBackendHealthy === false ? 'Offline' : 'Connecting'}
            </span>
          </div>

          {/* OpenAPI Docs Link */}
          <a
            href="/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="p-1.5 text-slate-400 hover:text-white transition rounded-lg hover:bg-slate-800"
            title="OpenAPI Docs"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      </div>
    </header>
  );
};
