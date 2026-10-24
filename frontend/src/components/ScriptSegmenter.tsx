import React, { useState } from 'react';
import {
  FileText,
  Clock,
  BookOpen,
  ArrowRight,
  AlertCircle,
  Wand2,
} from 'lucide-react';
import type { Scene, StudioMode } from '../types';
import { api } from '../api/client';

interface ScriptSegmenterProps {
  scriptText: string;
  onScriptChange: (text: string) => void;
  onScenesGenerated: (scenes: Scene[]) => void;
  audioDuration: number | null;
  studioMode: StudioMode;
}

const SAMPLE_SCRIPTS = {
  creative: {
    title: 'Cinematic Ocean Wildlife',
    script:
      'Beneath the sunlit surface of the open sea lies an extraordinary world of movement and light. Majestic marine creatures glide effortlessly across pristine turquoise currents, navigating underwater coral canyons. As dusk descends across the horizon, vibrant bioluminescence awakens, painting the deep water in radiant emerald and sapphire hues.',
  },
  professional: {
    title: 'Enterprise Cloud Architecture',
    script:
      'IncuBrix Enterprise Cloud provides real-time distributed media processing pipelines for corporate communications. Our hardened container architecture scales dynamically, delivering deterministic video assembly with full provenance tracking and compliance verification. Streamline high-volume asset production with audited security and predictable latency.',
  },
};

export const ScriptSegmenter: React.FC<ScriptSegmenterProps> = ({
  scriptText,
  onScriptChange,
  onScenesGenerated,
  audioDuration,
  studioMode,
}) => {
  const [isSegmenting, setIsSegmenting] = useState(false);
  const [segmentError, setSegmentError] = useState<string | null>(null);

  // Calculate approximate speaking duration (150 words per minute baseline)
  const wordCount = scriptText.trim() ? scriptText.trim().split(/\s+/).length : 0;
  const estimatedSeconds = wordCount > 0 ? (wordCount / 150) * 60 : 0;

  const handleAutoSegment = async () => {
    if (!scriptText.trim()) return;
    setIsSegmenting(true);
    setSegmentError(null);
    try {
      const res = await api.segmentScript({
        script: scriptText.trim(),
        total_duration_seconds: audioDuration && audioDuration > 0 ? audioDuration : undefined,
        words_per_minute: 150,
      });

      if (res && res.scenes && res.scenes.length > 0) {
        onScenesGenerated(res.scenes);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Segmentation failed';
      setSegmentError(msg);
    } finally {
      setIsSegmenting(false);
    }
  };

  const loadSample = (type: 'creative' | 'professional') => {
    const sample = SAMPLE_SCRIPTS[type];
    onScriptChange(sample.script);
  };

  return (
    <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-fuchsia-500/10 text-fuchsia-400 flex items-center justify-center">
            <FileText className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">Full Script & Narration</h3>
            <p className="text-xs text-slate-400">
              Type or paste your narrative script, or auto-segment into synchronized scene cards
            </p>
          </div>
        </div>

        {/* Quick Demo Script Loaders */}
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-slate-500 text-[11px] hidden sm:inline">Sample:</span>
          <button
            type="button"
            onClick={() => loadSample(studioMode)}
            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition cursor-pointer flex items-center gap-1 text-[11px]"
          >
            <BookOpen className="w-3 h-3 text-amber-400" />
            <span>Load {studioMode === 'creative' ? 'Cinematic' : 'Corporate'} Preset</span>
          </button>
        </div>
      </div>

      {/* Script Textarea */}
      <div className="relative">
        <textarea
          rows={4}
          value={scriptText}
          onChange={(e) => onScriptChange(e.target.value)}
          placeholder="Enter narration script here. Punctuation (periods, exclamation marks) will guide intelligent scene boundaries..."
          className="w-full p-3.5 bg-slate-950 border border-slate-800 rounded-xl text-xs sm:text-sm text-slate-200 focus:outline-none focus:border-fuchsia-500 placeholder-slate-600 transition resize-y min-h-[100px]"
        />

        {/* Word count & cadence duration badge */}
        <div className="flex items-center justify-between mt-1 text-[11px] text-slate-400 px-1">
          <div className="flex items-center gap-3">
            <span>{wordCount} words</span>
            <span>•</span>
            <div className="flex items-center gap-1 text-slate-300">
              <Clock className="w-3 h-3 text-indigo-400" />
              <span>~{estimatedSeconds.toFixed(1)}s speech cadence</span>
            </div>
            {audioDuration && (
              <>
                <span>•</span>
                <span className="text-emerald-400">Audio track: {audioDuration.toFixed(1)}s</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Auto Segment CTA */}
      <div className="flex items-center justify-between pt-1">
        <div className="text-[11px] text-slate-500">
          Scene boundaries obey sentence punctuation and timing limits.
        </div>
        <button
          type="button"
          disabled={isSegmenting || !scriptText.trim()}
          onClick={handleAutoSegment}
          className="px-4 py-2 bg-gradient-to-r from-fuchsia-600 via-pink-600 to-indigo-600 hover:from-fuchsia-500 hover:to-indigo-500 disabled:opacity-40 text-white font-medium rounded-xl text-xs transition-all shadow-md shadow-fuchsia-600/20 cursor-pointer flex items-center gap-2"
        >
          {isSegmenting ? (
            <>
              <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              <span>Segmenting Scenes...</span>
            </>
          ) : (
            <>
              <Wand2 className="w-3.5 h-3.5" />
              <span>AI Auto-Segment into Scenes</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </>
          )}
        </button>
      </div>

      {segmentError && (
        <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
          <span>{segmentError}</span>
        </div>
      )}
    </div>
  );
};
