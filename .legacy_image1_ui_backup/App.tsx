import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  ArrowRight,
  AlertCircle,
} from 'lucide-react';
import type {
  AspectRatio,
  AudioSourceType,
  BrandingConfig,
  Resolution,
  Scene,
  StudioMode,
} from './types';
import { api } from './api/client';
import { Header } from './components/Header';
import { ScriptSegmenter } from './components/ScriptSegmenter';
import { AudioUploader } from './components/AudioUploader';
import { SceneTimeline } from './components/SceneTimeline';
import { StudioControls } from './components/StudioControls';
import { JobProgressModal } from './components/JobProgressModal';
import { JobHistoryView } from './components/JobHistoryView';
import { MediaExplorerView } from './components/MediaExplorerView';
import { SystemStatusView } from './components/SystemStatusView';

const DEFAULT_SCENES: Scene[] = [
  {
    narration: 'Beneath the sunlit surface of the open sea lies an extraordinary world of movement and light.',
    duration_seconds: 4.0,
    visual_description: 'Underwater sunbeams penetrating clear turquoise sea with graceful ocean current.',
    keywords: ['ocean', 'underwater', 'sunlight'],
    transition: 'cut',
  },
  {
    narration: 'Majestic marine creatures glide effortlessly across pristine turquoise currents.',
    duration_seconds: 4.0,
    visual_description: 'Graceful sea turtle or marine life swimming peacefully through coral reef.',
    keywords: ['marine life', 'turtle', 'coral'],
    transition: 'cut',
  },
  {
    narration: 'As dusk descends across the horizon, vibrant bioluminescence awakens in radiant emerald hues.',
    duration_seconds: 4.0,
    visual_description: 'Deep ocean glow with shimmering bioluminescent particles and midnight currents.',
    keywords: ['bioluminescence', 'deep sea', 'glow'],
    transition: 'cut',
  },
];

export function App() {
  // Navigation & Mode
  const [studioMode, setStudioMode] = useState<StudioMode>('creative');
  const [activeTab, setActiveTab] = useState<'studio' | 'history' | 'explorer' | 'status'>('studio');
  const [isBackendHealthy, setIsBackendHealthy] = useState<boolean | null>(null);

  // Form State
  const [title, setTitle] = useState('Cinematic Ocean Journey');
  const [scriptText, setScriptText] = useState(
    'Beneath the sunlit surface of the open sea lies an extraordinary world of movement and light. Majestic marine creatures glide effortlessly across pristine turquoise currents. As dusk descends across the horizon, vibrant bioluminescence awakens in radiant emerald hues.'
  );
  const [scenes, setScenes] = useState<Scene[]>(DEFAULT_SCENES);
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>('16:9');
  const [resolution, setResolution] = useState<Resolution>('1080p');
  const [stylePreset, setStylePreset] = useState('cinematic');
  const [pacing, setPacing] = useState('balanced');
  const [captionPreset, setCaptionPreset] = useState('karaoke');
  const [branding, setBranding] = useState<BrandingConfig>({
    brand_name: 'IncuBrix Corp',
    primary_color: '#1e40af',
    font_family: 'Inter',
  });

  // Audio State
  const [audioSource, setAudioSource] = useState<AudioSourceType>('none');
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState('');
  const [autoRebalance, setAutoRebalance] = useState(false);
  const [detectedDuration, setDetectedDuration] = useState<number | null>(null);

  // Active Job & Submission
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Health ping
  useEffect(() => {
    const checkHealth = () => {
      api
        .getHealth()
        .then(() => setIsBackendHealthy(true))
        .catch(() => setIsBackendHealthy(false));
    };
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  // Update default title and presets when studio mode changes
  const handleModeChange = (newMode: StudioMode) => {
    setStudioMode(newMode);
    if (newMode === 'professional') {
      setTitle('IncuBrix Enterprise Architecture Briefing');
      setStylePreset('corporate_clean');
    } else {
      setTitle('Cinematic Ocean Journey');
      setStylePreset('cinematic');
    }
  };

  const handleSubmitJob = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    // Validation
    if (!title.trim()) {
      setSubmitError('Please provide a video title.');
      return;
    }
    if (scenes.length === 0) {
      setSubmitError('At least one scene is required.');
      return;
    }
    const totalDuration = scenes.reduce((acc, s) => acc + (Number(s.duration_seconds) || 0), 0);
    if (totalDuration < 1.0 || totalDuration > 300.0) {
      setSubmitError(`Total video duration (${totalDuration.toFixed(1)}s) must be between 1.0s and 300.0s.`);
      return;
    }

    setSubmitting(true);
    try {
      let createdJob;
      if (audioSource === 'upload' && audioFile) {
        // Multipart submission
        const formData = new FormData();
        formData.append('title', title.trim());
        formData.append('aspect_ratio', aspectRatio);
        formData.append('resolution', resolution);
        formData.append('scenes', JSON.stringify(scenes));
        formData.append('script', scriptText);
        formData.append('auto_rebalance_scenes', String(autoRebalance));
        formData.append('studio_mode', studioMode);
        formData.append('style_preset', stylePreset);
        formData.append('pacing', pacing);
        formData.append('caption_preset', captionPreset);
        formData.append('media_provider', 'pixabay');
        if (branding && studioMode === 'professional') {
          formData.append('branding', JSON.stringify(branding));
        }
        formData.append('audio_file', audioFile);

        createdJob = await api.createJobMultipart(formData);
      } else {
        // JSON submission
        const payload: Record<string, unknown> = {
          title: title.trim(),
          aspect_ratio: aspectRatio,
          resolution: resolution,
          scenes,
          script: scriptText.trim() ? scriptText.trim() : undefined,
          auto_rebalance_scenes: autoRebalance,
          studio_mode: studioMode,
          style_preset: stylePreset,
          pacing,
          caption_preset: captionPreset,
          branding: studioMode === 'professional' ? branding : undefined,
          media_provider: 'pixabay',
        };

        if (audioSource === 'url' && audioUrl.trim()) {
          payload.audio_url = audioUrl.trim();
        }

        createdJob = await api.createJobJson(payload);
      }

      if (createdJob && createdJob.job_id) {
        setActiveJobId(createdJob.job_id);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Job submission failed';
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#070b14] text-slate-100 flex flex-col font-sans selection:bg-indigo-500/30">
      {/* Top Header */}
      <Header
        studioMode={studioMode}
        onModeChange={handleModeChange}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        isBackendHealthy={isBackendHealthy}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* TAB 1: STUDIO WORKSPACE */}
        {activeTab === 'studio' && (
          <form onSubmit={handleSubmitJob} className="space-y-6">
            {/* Title & Mode Banner */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900/40 border border-slate-800/80 rounded-2xl p-5">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`text-[11px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                      studioMode === 'creative'
                        ? 'bg-fuchsia-950 text-fuchsia-300 border border-fuchsia-800'
                        : 'bg-blue-950 text-blue-300 border border-blue-800'
                    }`}
                  >
                    {studioMode === 'creative' ? 'Creative Studio' : 'Professional Studio'}
                  </span>
                </div>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Enter video project title..."
                  className="w-full bg-transparent font-extrabold text-xl sm:text-2xl text-white focus:outline-none focus:border-b focus:border-indigo-500 transition pb-1"
                />
              </div>

              {/* Generate Video Action Button */}
              <div>
                <button
                  type="submit"
                  disabled={submitting}
                  className={`w-full sm:w-auto px-6 py-3 text-white font-bold rounded-xl text-sm transition-all duration-300 shadow-xl cursor-pointer flex items-center justify-center gap-2 ${
                    studioMode === 'creative'
                      ? 'bg-gradient-to-r from-fuchsia-600 via-pink-600 to-indigo-600 hover:from-fuchsia-500 hover:to-indigo-500 shadow-pink-600/25'
                      : 'bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 shadow-indigo-600/25'
                  } ${submitting ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  {submitting ? (
                    <>
                      <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      <span>Submitting Pipeline...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      <span>Render Video</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            </div>

            {submitError && (
              <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/80 text-rose-300 text-xs flex items-center gap-2.5">
                <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                <span>{submitError}</span>
              </div>
            )}

            {/* Step 1: Script & Narration */}
            <ScriptSegmenter
              scriptText={scriptText}
              onScriptChange={setScriptText}
              onScenesGenerated={setScenes}
              audioDuration={detectedDuration}
              studioMode={studioMode}
            />

            {/* Step 2: Audio & Voiceover Track */}
            <AudioUploader
              audioSource={audioSource}
              onAudioSourceChange={setAudioSource}
              audioFile={audioFile}
              onAudioFileChange={setAudioFile}
              audioUrl={audioUrl}
              onAudioUrlChange={setAudioUrl}
              autoRebalance={autoRebalance}
              onAutoRebalanceChange={setAutoRebalance}
              detectedDuration={detectedDuration}
              onDurationDetected={setDetectedDuration}
            />

            {/* Step 3: Scene Timeline & B-Roll Matcher */}
            <SceneTimeline
              scenes={scenes}
              onScenesChange={setScenes}
              minDuration={1.0}
              maxDuration={300.0}
            />

            {/* Step 4: Studio Presets & Production Settings */}
            <StudioControls
              studioMode={studioMode}
              aspectRatio={aspectRatio}
              onAspectRatioChange={setAspectRatio}
              resolution={resolution}
              onResolutionChange={setResolution}
              stylePreset={stylePreset}
              onStylePresetChange={setStylePreset}
              pacing={pacing}
              onPacingChange={setPacing}
              captionPreset={captionPreset}
              onCaptionPresetChange={setCaptionPreset}
              branding={branding}
              onBrandingChange={setBranding}
            />
          </form>
        )}

        {/* TAB 2: JOB PRODUCTION HISTORY */}
        {activeTab === 'history' && <JobHistoryView onSelectJob={(id) => setActiveJobId(id)} />}

        {/* TAB 3: B-ROLL MEDIA EXPLORER */}
        {activeTab === 'explorer' && <MediaExplorerView />}

        {/* TAB 4: SYSTEM STATUS & LIMITS */}
        {activeTab === 'status' && <SystemStatusView />}
      </main>

      {/* Real-time Job Progress & Player Modal */}
      {activeJobId && (
        <JobProgressModal
          jobId={activeJobId}
          onClose={() => setActiveJobId(null)}
        />
      )}

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/60 py-4 px-4 sm:px-8 text-center text-xs text-slate-500">
        IncuBrix AI Video Studio • Dual-Mode Production Platform • Fully Verifiable CC0 B-Roll & FFmpeg Rendering
      </footer>
    </div>
  );
}

export default App;
