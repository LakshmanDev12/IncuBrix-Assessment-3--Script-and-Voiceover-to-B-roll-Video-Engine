import React from 'react';
import {
  Monitor,
  Smartphone,
  Square,
  Sparkles,
  Palette,
  Type,
  Layout,
  Subtitles,
  Building2,
} from 'lucide-react';
import type { AspectRatio, Resolution, StudioMode, BrandingConfig } from '../types';

interface StudioControlsProps {
  studioMode: StudioMode;
  aspectRatio: AspectRatio;
  onAspectRatioChange: (ar: AspectRatio) => void;
  resolution: Resolution;
  onResolutionChange: (res: Resolution) => void;
  stylePreset: string;
  onStylePresetChange: (preset: string) => void;
  pacing: string;
  onPacingChange: (pacing: string) => void;
  captionPreset: string;
  onCaptionPresetChange: (preset: string) => void;
  branding: BrandingConfig;
  onBrandingChange: (branding: BrandingConfig) => void;
}

export const StudioControls: React.FC<StudioControlsProps> = ({
  studioMode,
  aspectRatio,
  onAspectRatioChange,
  resolution,
  onResolutionChange,
  stylePreset,
  onStylePresetChange,
  pacing,
  onPacingChange,
  captionPreset,
  onCaptionPresetChange,
  branding,
  onBrandingChange,
}) => {
  const isCreative = studioMode === 'creative';

  return (
    <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 space-y-5">
      <div className="flex items-center gap-2">
        <div
          className={`w-8 h-8 rounded-lg flex items-center justify-center ${
            isCreative ? 'bg-fuchsia-500/10 text-fuchsia-400' : 'bg-blue-500/10 text-blue-400'
          }`}
        >
          {isCreative ? <Sparkles className="w-4 h-4" /> : <Building2 className="w-4 h-4" />}
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">
            {isCreative ? 'Creative Studio Configuration' : 'Professional Brand & Format Engine'}
          </h3>
          <p className="text-xs text-slate-400">
            {isCreative
              ? 'Aspect ratio, visual pacing, dynamic subtitles, and cinematic presets'
              : 'Enterprise layouts, corporate color schemes, logo attribution, and structured styling'}
          </p>
        </div>
      </div>

      {/* Row 1: Aspect Ratio & Resolution */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Aspect Ratio Cards */}
        <div>
          <label className="block text-xs font-semibold text-slate-300 mb-2">
            Output Aspect Ratio
          </label>
          <div className="grid grid-cols-3 gap-2">
            {/* 16:9 */}
            <button
              type="button"
              onClick={() => onAspectRatioChange('16:9')}
              className={`p-3 rounded-xl border text-center transition cursor-pointer ${
                aspectRatio === '16:9'
                  ? isCreative
                    ? 'bg-fuchsia-950/40 border-fuchsia-500 text-white shadow-md shadow-fuchsia-950'
                    : 'bg-blue-950/40 border-blue-500 text-white shadow-md shadow-blue-950'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              <Monitor className="w-5 h-5 mx-auto mb-1" />
              <div className="text-xs font-bold">16:9</div>
              <div className="text-[10px] text-slate-500">Landscape</div>
            </button>

            {/* 9:16 */}
            <button
              type="button"
              onClick={() => onAspectRatioChange('9:16')}
              className={`p-3 rounded-xl border text-center transition cursor-pointer ${
                aspectRatio === '9:16'
                  ? isCreative
                    ? 'bg-fuchsia-950/40 border-fuchsia-500 text-white shadow-md shadow-fuchsia-950'
                    : 'bg-blue-950/40 border-blue-500 text-white shadow-md shadow-blue-950'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              <Smartphone className="w-5 h-5 mx-auto mb-1" />
              <div className="text-xs font-bold">9:16</div>
              <div className="text-[10px] text-slate-500">Shorts / Reels</div>
            </button>

            {/* 1:1 */}
            <button
              type="button"
              onClick={() => onAspectRatioChange('1:1')}
              className={`p-3 rounded-xl border text-center transition cursor-pointer ${
                aspectRatio === '1:1'
                  ? isCreative
                    ? 'bg-fuchsia-950/40 border-fuchsia-500 text-white shadow-md shadow-fuchsia-950'
                    : 'bg-blue-950/40 border-blue-500 text-white shadow-md shadow-blue-950'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              <Square className="w-5 h-5 mx-auto mb-1" />
              <div className="text-xs font-bold">1:1</div>
              <div className="text-[10px] text-slate-500">Square / Feed</div>
            </button>
          </div>
        </div>

        {/* Resolution & Pacing */}
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              Render Quality
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => onResolutionChange('1080p')}
                className={`py-2 px-3 rounded-xl border text-xs font-semibold cursor-pointer transition ${
                  resolution === '1080p'
                    ? isCreative
                      ? 'bg-fuchsia-950/40 border-fuchsia-500 text-white'
                      : 'bg-blue-950/40 border-blue-500 text-white'
                    : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                1080p Full HD (30 fps)
              </button>
              <button
                type="button"
                onClick={() => onResolutionChange('720p')}
                className={`py-2 px-3 rounded-xl border text-xs font-semibold cursor-pointer transition ${
                  resolution === '720p'
                    ? isCreative
                      ? 'bg-fuchsia-950/40 border-fuchsia-500 text-white'
                      : 'bg-blue-950/40 border-blue-500 text-white'
                    : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                720p Fast HD (30 fps)
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              Visual Pacing
            </label>
            <div className="flex bg-slate-950 border border-slate-800 rounded-xl p-1 text-xs">
              {(['fast', 'balanced', 'slow'] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => onPacingChange(p)}
                  className={`flex-1 py-1 rounded-lg capitalize font-medium transition cursor-pointer ${
                    pacing === p ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: Mode Specific Settings */}
      {isCreative ? (
        /* Creative Studio Presets */
        <div className="pt-3 border-t border-slate-800 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
              <Layout className="w-3.5 h-3.5 text-fuchsia-400" />
              Creative Style Preset
            </label>
            <select
              value={stylePreset}
              onChange={(e) => onStylePresetChange(e.target.value)}
              className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-fuchsia-500 cursor-pointer"
            >
              <option value="cinematic">Cinematic Drama (Color graded, high contrast)</option>
              <option value="explainer">Explainer & Educational (Fast visual hooks)</option>
              <option value="documentary">Documentary Film (Naturalistic, subtle)</option>
              <option value="travel_vlog">Travel & Lifestyle (Vibrant, high energy)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
              <Subtitles className="w-3.5 h-3.5 text-fuchsia-400" />
              Caption Formatting
            </label>
            <select
              value={captionPreset}
              onChange={(e) => onCaptionPresetChange(e.target.value)}
              className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-fuchsia-500 cursor-pointer"
            >
              <option value="karaoke">Dynamic Word-Highlighted Subtitles</option>
              <option value="clean_subtitles">Clean Bottom White Subtitles</option>
              <option value="banner">High-Contrast Solid Banner</option>
              <option value="none">No Rendered Captions (SRT Only)</option>
            </select>
          </div>
        </div>
      ) : (
        /* Professional Studio Brand Controls */
        <div className="pt-3 border-t border-slate-800 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1 flex items-center gap-1.5">
                <Building2 className="w-3.5 h-3.5 text-blue-400" />
                Brand / Organization Name
              </label>
              <input
                type="text"
                value={branding.brand_name || ''}
                onChange={(e) => onBrandingChange({ ...branding, brand_name: e.target.value })}
                placeholder="e.g. IncuBrix Corp"
                className="w-full p-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1 flex items-center gap-1.5">
                <Palette className="w-3.5 h-3.5 text-blue-400" />
                Brand Primary Color
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={branding.primary_color || '#1e40af'}
                  onChange={(e) => onBrandingChange({ ...branding, primary_color: e.target.value })}
                  className="w-8 h-8 rounded-lg border border-slate-700 bg-transparent cursor-pointer"
                />
                <input
                  type="text"
                  value={branding.primary_color || '#1e40af'}
                  onChange={(e) => onBrandingChange({ ...branding, primary_color: e.target.value })}
                  className="flex-1 p-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-blue-500 font-mono"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1 flex items-center gap-1.5">
                <Type className="w-3.5 h-3.5 text-blue-400" />
                Typography Standard
              </label>
              <select
                value={branding.font_family || 'Inter'}
                onChange={(e) => onBrandingChange({ ...branding, font_family: e.target.value })}
                className="w-full p-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-blue-500 cursor-pointer"
              >
                <option value="Inter">Inter (Clean modern executive)</option>
                <option value="Helvetica">Helvetica / Arial (Standard corporate)</option>
                <option value="Roboto">Roboto (Technical documentation)</option>
                <option value="Georgia">Georgia (Editorial & reports)</option>
              </select>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
