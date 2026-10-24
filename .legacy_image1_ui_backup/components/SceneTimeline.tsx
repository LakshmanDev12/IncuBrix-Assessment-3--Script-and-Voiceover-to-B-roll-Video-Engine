import React, { useState } from 'react';
import {
  Layers,
  Plus,
  Trash2,
  Clock,
  Sparkles,
  Search,
} from 'lucide-react';
import type { Scene, CandidateMediaItem } from '../types';
import { api } from '../api/client';

interface SceneTimelineProps {
  scenes: Scene[];
  onScenesChange: (scenes: Scene[]) => void;
  minDuration: number;
  maxDuration: number;
}

export const SceneTimeline: React.FC<SceneTimelineProps> = ({
  scenes,
  onScenesChange,
  minDuration,
  maxDuration,
}) => {
  const [activeMediaDrawerSceneIndex, setActiveMediaDrawerSceneIndex] = useState<number | null>(null);
  const [brollCandidates, setBrollCandidates] = useState<CandidateMediaItem[]>([]);
  const [searchingMedia, setSearchingMedia] = useState(false);

  const totalDuration = scenes.reduce((acc, s) => acc + (Number(s.duration_seconds) || 0), 0);
  const isDurationValid = totalDuration >= minDuration && totalDuration <= maxDuration;

  const handleUpdateScene = (index: number, updates: Partial<Scene>) => {
    const updated = [...scenes];
    updated[index] = { ...updated[index], ...updates };
    onScenesChange(updated);
  };

  const handleAddScene = () => {
    const newScene: Scene = {
      narration: 'New scene narration text spoken in this scene.',
      duration_seconds: 4.0,
      visual_description: 'Cinematic visual sequence relevant to narration.',
      keywords: ['cinematic', 'high quality'],
      transition: 'cut',
    };
    onScenesChange([...scenes, newScene]);
  };

  const handleDeleteScene = (index: number) => {
    if (scenes.length <= 1) return;
    const updated = scenes.filter((_, i) => i !== index);
    onScenesChange(updated);
  };

  const handleSearchBroll = async (index: number) => {
    const scene = scenes[index];
    setActiveMediaDrawerSceneIndex(index);
    setSearchingMedia(true);
    try {
      const query = scene.visual_description || scene.narration;
      const res = await api.searchMedia(query, 'pixabay', 6);
      setBrollCandidates(res.candidates || []);
    } catch {
      setBrollCandidates([]);
    } finally {
      setSearchingMedia(false);
    }
  };

  const handleSelectCandidate = (sceneIndex: number, candidate: CandidateMediaItem) => {
    handleUpdateScene(sceneIndex, {
      visual_description: candidate.description || candidate.title,
      source_url: candidate.source_url || candidate.download_url,
      license_name: candidate.license_name,
      attribution: candidate.attribution,
    });
    setActiveMediaDrawerSceneIndex(null);
  };

  return (
    <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 space-y-4">
      {/* Header & Stats */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-pink-500/10 text-pink-400 flex items-center justify-center">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">Scene List & Visual Prompts</h3>
            <p className="text-xs text-slate-400">
              Each scene defines a narration line, duration timing, and target B-roll visual description
            </p>
          </div>
        </div>

        {/* Runtime & Count Badge */}
        <div className="flex items-center gap-2 text-xs">
          <span className="px-3 py-1 rounded-full bg-slate-950 border border-slate-800 text-slate-300 font-medium">
            {scenes.length} {scenes.length === 1 ? 'Scene' : 'Scenes'}
          </span>
          <span
            className={`px-3 py-1 rounded-full border font-semibold flex items-center gap-1.5 ${
              isDurationValid
                ? 'bg-emerald-950/50 border-emerald-800/80 text-emerald-300'
                : 'bg-amber-950/50 border-amber-800/80 text-amber-300'
            }`}
          >
            <Clock className="w-3 h-3" />
            <span>{totalDuration.toFixed(1)}s total</span>
          </span>
          <button
            type="button"
            onClick={handleAddScene}
            className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-medium transition cursor-pointer flex items-center gap-1"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Scene</span>
          </button>
        </div>
      </div>

      {!isDurationValid && (
        <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-800/60 text-amber-300 text-xs">
          Total video duration is {totalDuration.toFixed(1)}s. Engine constraints require between {minDuration}s and {maxDuration}s.
        </div>
      )}

      {/* Scene Cards */}
      <div className="space-y-3">
        {scenes.map((scene, idx) => (
          <div
            key={idx}
            className="bg-slate-950 border border-slate-800 hover:border-slate-700/80 rounded-xl p-4 transition-all duration-200 space-y-3"
          >
            {/* Card Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <span className="w-6 h-6 rounded-md bg-slate-800 text-indigo-300 font-bold text-xs flex items-center justify-center">
                  #{idx + 1}
                </span>
                <span className="text-xs font-semibold text-slate-300">
                  Scene {idx + 1}
                </span>
                {scene.license_name && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950/60 border border-emerald-800/50 text-emerald-300 font-medium">
                    Verified {scene.license_name}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {/* Duration Stepper */}
                <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg px-2 py-1 text-xs">
                  <Clock className="w-3.5 h-3.5 text-slate-400 mr-1.5" />
                  <input
                    type="number"
                    step="any"
                    min="0.5"
                    max="60"
                    value={scene.duration_seconds}
                    onChange={(e) =>
                      handleUpdateScene(idx, {
                        duration_seconds: Math.max(0.5, Math.min(60, parseFloat(e.target.value) || 0.5)),
                      })
                    }
                    className="w-12 bg-transparent text-right text-white font-medium focus:outline-none"
                  />
                  <span className="text-slate-400 ml-1">s</span>
                </div>

                {/* B-roll Search Button */}
                <button
                  type="button"
                  onClick={() => handleSearchBroll(idx)}
                  className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-indigo-300 transition cursor-pointer"
                  title="Search B-Roll Candidates"
                >
                  <Search className="w-3.5 h-3.5" />
                </button>

                {/* Delete button */}
                <button
                  type="button"
                  disabled={scenes.length <= 1}
                  onClick={() => handleDeleteScene(idx)}
                  className="p-1.5 rounded-lg hover:bg-rose-950/50 text-slate-500 hover:text-rose-400 disabled:opacity-30 transition cursor-pointer"
                  title="Delete Scene"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Inputs: Narration & Visual Description */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1">
                  Narration Text (Spoken)
                </label>
                <textarea
                  rows={2}
                  value={scene.narration}
                  onChange={(e) => handleUpdateScene(idx, { narration: e.target.value })}
                  placeholder="Spoken narration for this scene..."
                  className="w-full p-2.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500 resize-none"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1">
                  Visual Prompt (B-roll description for ranking)
                </label>
                <textarea
                  rows={2}
                  value={scene.visual_description}
                  onChange={(e) => handleUpdateScene(idx, { visual_description: e.target.value })}
                  placeholder="Describe visuals: lighting, subject, motion..."
                  className="w-full p-2.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500 resize-none"
                />
              </div>
            </div>

            {/* Quick Metadata: Transition & Style */}
            <div className="flex flex-wrap items-center justify-between text-xs pt-1 border-t border-slate-900 gap-2">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] text-slate-500">Transition:</span>
                  <select
                    value={scene.transition || 'cut'}
                    onChange={(e) => handleUpdateScene(idx, { transition: e.target.value })}
                    className="bg-slate-900 border border-slate-800 text-slate-300 rounded px-2 py-0.5 text-[11px] focus:outline-none"
                  >
                    <option value="cut">Direct Cut</option>
                    <option value="fade">Cross Fade</option>
                    <option value="dissolve">Dissolve</option>
                  </select>
                </div>

                {scene.visual_style && (
                  <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                    Style: {scene.visual_style}
                  </span>
                )}
              </div>

              {scene.attribution && (
                <div className="text-[10px] text-slate-500 truncate max-w-xs" title={scene.attribution}>
                  Attribution: {scene.attribution}
                </div>
              )}
            </div>

            {/* B-Roll Search Drawer (if active for this scene) */}
            {activeMediaDrawerSceneIndex === idx && (
              <div className="mt-3 p-3 bg-slate-900/90 border border-indigo-900/50 rounded-xl space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-indigo-300 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5" />
                    B-Roll Match Recommendations (CC0 Library)
                  </span>
                  <button
                    type="button"
                    onClick={() => setActiveMediaDrawerSceneIndex(null)}
                    className="text-[11px] text-slate-400 hover:text-white"
                  >
                    Close
                  </button>
                </div>

                {searchingMedia ? (
                  <div className="p-4 text-center text-xs text-slate-400">
                    <span className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin inline-block mr-2" />
                    Finding matching B-roll candidates...
                  </div>
                ) : brollCandidates.length === 0 ? (
                  <div className="p-3 text-center text-xs text-slate-500">
                    No candidate clips found for this query in the local library.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                    {brollCandidates.map((cand) => (
                      <div
                        key={cand.id}
                        onClick={() => handleSelectCandidate(idx, cand)}
                        className="p-2.5 rounded-lg bg-slate-950 hover:bg-indigo-950/40 border border-slate-800 hover:border-indigo-600/50 transition cursor-pointer text-left space-y-1"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-xs text-slate-200 truncate">
                            {cand.title}
                          </span>
                          <span className="text-[10px] text-slate-400">{cand.duration_seconds}s</span>
                        </div>
                        <p className="text-[11px] text-slate-400 line-clamp-2">{cand.description}</p>
                        <div className="flex items-center gap-1.5 text-[10px] text-indigo-400 pt-1">
                          <span>{cand.license_name}</span>
                          <span>•</span>
                          <span>{cand.creator}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
