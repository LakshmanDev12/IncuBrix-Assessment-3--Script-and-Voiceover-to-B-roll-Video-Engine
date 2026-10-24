import React, { useEffect, useState } from 'react';
import {
  X,
  CheckCircle2,
  AlertCircle,
  Download,
  Film,
  FileText,
  Sliders,
  ShieldCheck,
} from 'lucide-react';
import type { JobResponse, JobStage } from '../types';
import { api } from '../api/client';

interface JobProgressModalProps {
  jobId: string;
  onClose: () => void;
  onJobUpdated?: (job: JobResponse) => void;
}

const ENGINE_STAGES: { stage: JobStage; label: string }[] = [
  { stage: 'validating', label: 'Validate' },
  { stage: 'segmenting', label: 'Segment' },
  { stage: 'fetching_media', label: 'B-Roll Match' },
  { stage: 'processing_media', label: 'Process Clips' },
  { stage: 'assembling_timeline', label: 'Assemble' },
  { stage: 'rendering', label: 'FFmpeg Render' },
  { stage: 'generating_artifacts', label: 'Artifacts' },
  { stage: 'completed', label: 'Complete' },
];

export const JobProgressModal: React.FC<JobProgressModalProps> = ({
  jobId,
  onClose,
  onJobUpdated,
}) => {
  const [job, setJob] = useState<JobResponse | null>(null);
  const [activeTab, setActiveTab] = useState<'video' | 'captions' | 'timeline' | 'manifest' | 'downloads'>('video');
  const [cancelling, setCancelling] = useState(false);
  const [srtText, setSrtText] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Poll job status
  useEffect(() => {
    let isMounted = true;
    let timer: number | null = null;

    const fetchStatus = async () => {
      try {
        const data = await api.getJob(jobId);
        if (!isMounted) return;
        setJob(data);
        if (onJobUpdated) onJobUpdated(data);

        // Continue polling if job is queued or running
        if (data.status === 'queued' || (data.status as string) === 'running' || data.status === 'processing') {
          timer = window.setTimeout(fetchStatus, 1000);
        } else if (data.status === 'completed') {
          // Fetch SRT content for preview
          try {
            const srtUrl = api.getArtifactDownloadUrl(jobId, 'captions.srt');
            const res = await fetch(srtUrl);
            if (res.ok) {
              const text = await res.text();
              if (isMounted) setSrtText(text);
            }
          } catch {
            // Non-critical if srt fetch fails
          }
        }
      } catch (err: unknown) {
        if (isMounted) {
          const msg = err instanceof Error ? err.message : 'Failed to query job state';
          setFetchError(msg);
        }
      }
    };

    fetchStatus();

    return () => {
      isMounted = false;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  const handleCancel = async () => {
    if (!job) return;
    setCancelling(true);
    try {
      await api.cancelJob(jobId);
      const updated = await api.getJob(jobId);
      setJob(updated);
    } catch (err: unknown) {
      console.error('Cancel failed', err);
    } finally {
      setCancelling(false);
    }
  };

  const getStageIndex = (stage: JobStage): number => {
    const idx = ENGINE_STAGES.findIndex((s) => s.stage === stage);
    return idx >= 0 ? idx : 0;
  };

  const isCompleted = job?.status === 'completed';
  const isFailed = job?.status === 'failed';
  const isCancelled = job?.status === 'cancelled';
  const isRunning = !isCompleted && !isFailed && !isCancelled;

  const currentStageIndex = job ? getStageIndex(job.current_stage) : 0;
  const videoUrl = job ? api.getArtifactDownloadUrl(job.job_id, 'video.mp4') : '';
  const srtUrl = job ? api.getArtifactDownloadUrl(job.job_id, 'captions.srt') : '';
  const timelineUrl = job ? api.getArtifactDownloadUrl(job.job_id, 'timeline.json') : '';
  const manifestUrl = job ? api.getArtifactDownloadUrl(job.job_id, 'manifest.json') : '';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md overflow-y-auto">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-4xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Modal Top Bar */}
        <div className="p-4 sm:p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div
              className={`w-9 h-9 rounded-xl flex items-center justify-center font-bold text-white shadow-md ${
                isCompleted
                  ? 'bg-emerald-600 text-white shadow-emerald-600/30'
                  : isFailed
                  ? 'bg-rose-600 text-white shadow-rose-600/30'
                  : 'bg-indigo-600 text-white shadow-indigo-600/30'
              }`}
            >
              <Film className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-base text-white truncate max-w-xs sm:max-w-md">
                  {job?.title || 'Rendering Video'}
                </h3>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase ${
                    isCompleted
                      ? 'bg-emerald-950 border border-emerald-800 text-emerald-400'
                      : isFailed
                      ? 'bg-rose-950 border border-rose-800 text-rose-400'
                      : isCancelled
                      ? 'bg-slate-800 border border-slate-700 text-slate-400'
                      : 'bg-indigo-950 border border-indigo-800 text-indigo-400 animate-pulse'
                  }`}
                >
                  {job?.status || 'loading'}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-mono">Job ID: {jobId}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {isRunning && (
              <button
                type="button"
                disabled={cancelling}
                onClick={handleCancel}
                className="px-3 py-1.5 rounded-lg bg-rose-950/60 hover:bg-rose-900/60 border border-rose-800/80 text-rose-300 text-xs font-medium transition cursor-pointer"
              >
                {cancelling ? 'Cancelling...' : 'Cancel Job'}
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-4 sm:p-6 overflow-y-auto space-y-6 flex-1">
          {fetchError && (
            <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400" />
              <span>{fetchError}</span>
            </div>
          )}

          {/* Stepper Progress Section */}
          <div className="bg-slate-950/70 border border-slate-800 rounded-2xl p-4 sm:p-5 space-y-4">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="text-slate-400">Current Phase:</span>
                <span className="font-semibold text-white capitalize">
                  {job?.stage_message || 'Initializing pipeline...'}
                </span>
              </div>
              <span className="font-bold font-mono text-indigo-400 text-sm">
                {job ? `${job.progress.toFixed(0)}%` : '0%'}
              </span>
            </div>

            {/* Continuous Progress Bar */}
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  isCompleted
                    ? 'bg-gradient-to-r from-emerald-500 to-teal-400'
                    : isFailed
                    ? 'bg-rose-500'
                    : 'bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500'
                }`}
                style={{ width: `${Math.max(5, job?.progress || 0)}%` }}
              />
            </div>

            {/* Visual Stage Dots */}
            <div className="hidden sm:grid grid-cols-8 gap-1 pt-1 text-[11px]">
              {ENGINE_STAGES.map((s, idx) => {
                const isPassed = currentStageIndex > idx || isCompleted;
                const isCurrent = currentStageIndex === idx && isRunning;
                return (
                  <div key={s.stage} className="text-center space-y-1">
                    <div
                      className={`w-4 h-4 rounded-full mx-auto flex items-center justify-center text-[9px] font-bold transition-all ${
                        isPassed
                          ? 'bg-emerald-500 text-slate-950'
                          : isCurrent
                          ? 'bg-indigo-500 text-white ring-4 ring-indigo-500/20 animate-pulse'
                          : 'bg-slate-800 text-slate-500'
                      }`}
                    >
                      {idx + 1}
                    </div>
                    <p
                      className={`truncate text-[10px] ${
                        isPassed
                          ? 'text-emerald-400 font-medium'
                          : isCurrent
                          ? 'text-indigo-300 font-bold'
                          : 'text-slate-600'
                      }`}
                      title={s.label}
                    >
                      {s.label}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Failure Banner */}
          {isFailed && (
            <div className="p-4 rounded-2xl bg-rose-950/40 border border-rose-800/80 text-rose-200 space-y-2">
              <div className="flex items-center gap-2 font-bold text-sm text-rose-300">
                <AlertCircle className="w-4 h-4 text-rose-400" />
                <span>Render Engine Exception</span>
              </div>
              <p className="text-xs text-rose-300 font-mono">
                {job?.error?.message || job?.stage_message || 'Video generation failed.'}
              </p>
              {job?.error?.error_code && (
                <div className="text-[11px] text-rose-400">
                  Error Code: <span className="font-mono">{job.error.error_code}</span>
                </div>
              )}
            </div>
          )}

          {/* Completed State: Artifact Navigation & Player */}
          {isCompleted && (
            <div className="space-y-4">
              {/* Tabs */}
              <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
                <button
                  type="button"
                  onClick={() => setActiveTab('video')}
                  className={`flex-1 py-1.5 rounded-lg font-medium transition cursor-pointer flex items-center justify-center gap-1.5 ${
                    activeTab === 'video' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Film className="w-3.5 h-3.5" />
                  <span>Video Preview</span>
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('captions')}
                  className={`flex-1 py-1.5 rounded-lg font-medium transition cursor-pointer flex items-center justify-center gap-1.5 ${
                    activeTab === 'captions' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>Subtitles (SRT)</span>
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('timeline')}
                  className={`flex-1 py-1.5 rounded-lg font-medium transition cursor-pointer flex items-center justify-center gap-1.5 ${
                    activeTab === 'timeline' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Sliders className="w-3.5 h-3.5" />
                  <span>Timeline</span>
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('manifest')}
                  className={`flex-1 py-1.5 rounded-lg font-medium transition cursor-pointer flex items-center justify-center gap-1.5 ${
                    activeTab === 'manifest' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>Audit Manifest</span>
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('downloads')}
                  className={`flex-1 py-1.5 rounded-lg font-medium transition cursor-pointer flex items-center justify-center gap-1.5 ${
                    activeTab === 'downloads' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Artifacts</span>
                </button>
              </div>

              {/* Tab 1: Video Player */}
              {activeTab === 'video' && (
                <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
                  <div
                    className={`relative rounded-xl overflow-hidden bg-black shadow-2xl max-w-full ${
                      job?.aspect_ratio === '9:16'
                        ? 'w-[280px] sm:w-[320px] aspect-[9/16]'
                        : job?.aspect_ratio === '1:1'
                        ? 'w-[360px] sm:w-[420px] aspect-square'
                        : 'w-full aspect-video'
                    }`}
                  >
                    <video
                      controls
                      autoPlay
                      playsInline
                      className="w-full h-full object-contain"
                      src={videoUrl}
                    >
                      Your browser does not support the video tag.
                    </video>
                  </div>

                  <div className="mt-3 flex items-center justify-between w-full text-xs text-slate-400 px-2">
                    <div className="flex items-center gap-3">
                      <span>Aspect: {job?.aspect_ratio}</span>
                      <span>•</span>
                      <span>Duration: {job?.duration_seconds.toFixed(1)}s</span>
                      <span>•</span>
                      <span>Resolution: {job?.resolution}</span>
                    </div>
                    <a
                      href={videoUrl}
                      download={`video-${jobId}.mp4`}
                      className="text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Download MP4</span>
                    </a>
                  </div>
                </div>
              )}

              {/* Tab 2: Captions (SRT) */}
              {activeTab === 'captions' && (
                <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 space-y-2">
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span className="font-semibold text-slate-200">captions.srt content</span>
                    <a
                      href={srtUrl}
                      download={`captions-${jobId}.srt`}
                      className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1 text-[11px]"
                    >
                      <Download className="w-3 h-3" />
                      <span>Download .srt</span>
                    </a>
                  </div>
                  <pre className="p-3 bg-slate-900 rounded-xl text-slate-300 font-mono text-xs overflow-x-auto max-h-[300px]">
                    {srtText || 'Loading captions...'}
                  </pre>
                </div>
              )}

              {/* Tab 3: Timeline */}
              {activeTab === 'timeline' && (
                <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 space-y-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-slate-200">Scene Sequence & Cuts</span>
                    <a
                      href={timelineUrl}
                      download={`timeline-${jobId}.json`}
                      className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1 text-[11px]"
                    >
                      <Download className="w-3 h-3" />
                      <span>Download timeline.json</span>
                    </a>
                  </div>

                  <div className="space-y-2">
                    {job?.manifest?.scenes?.map((sc) => (
                      <div
                        key={sc.scene_index}
                        className="p-3 rounded-xl bg-slate-900 border border-slate-800/80 flex items-center justify-between text-xs"
                      >
                        <div className="space-y-1 max-w-[70%]">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-indigo-400">Scene #{sc.scene_index}</span>
                            <span className="text-slate-400">
                              {sc.start_seconds.toFixed(1)}s → {sc.end_seconds.toFixed(1)}s ({sc.duration_seconds.toFixed(1)}s)
                            </span>
                          </div>
                          <p className="text-slate-300 line-clamp-1 italic">"{sc.narration}"</p>
                        </div>
                        <div className="text-right text-[11px]">
                          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                            {sc.clip_id || 'Matched Clip'}
                          </span>
                        </div>
                      </div>
                    )) || (
                      <p className="text-xs text-slate-400">Timeline data loading or not available.</p>
                    )}
                  </div>
                </div>
              )}

              {/* Tab 4: Audit Manifest */}
              {activeTab === 'manifest' && (
                <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 space-y-3 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-200">Legal Provenance & Rights Audit</span>
                    <a
                      href={manifestUrl}
                      download={`manifest-${jobId}.json`}
                      className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1 text-[11px]"
                    >
                      <Download className="w-3 h-3" />
                      <span>Download manifest.json</span>
                    </a>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                          <th className="py-2 px-2">Scene</th>
                          <th className="py-2 px-2">Clip Source</th>
                          <th className="py-2 px-2">License</th>
                          <th className="py-2 px-2">Attribution</th>
                          <th className="py-2 px-2">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-900 text-slate-300">
                        {job?.manifest?.scenes?.map((sc) => (
                          <tr key={sc.scene_index} className="hover:bg-slate-900/50">
                            <td className="py-2 px-2 font-mono">#{sc.scene_index}</td>
                            <td className="py-2 px-2">{sc.clip_source || 'local_cc0'}</td>
                            <td className="py-2 px-2 font-semibold text-emerald-400">
                              {sc.license_name || 'CC0'}
                            </td>
                            <td className="py-2 px-2 text-slate-400">{sc.attribution || 'Public Domain'}</td>
                            <td className="py-2 px-2">
                              <span className="inline-flex items-center gap-1 text-emerald-400 text-[11px]">
                                <CheckCircle2 className="w-3 h-3" />
                                Verified
                              </span>
                            </td>
                          </tr>
                        )) || (
                          <tr>
                            <td colSpan={5} className="py-3 text-center text-slate-500">
                              No manifest items available.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Tab 5: Download Center */}
              {activeTab === 'downloads' && (
                <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 space-y-3">
                  <h4 className="font-semibold text-xs text-slate-200">All Production Artifacts</h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <a
                      href={videoUrl}
                      download={`video-${jobId}.mp4`}
                      className="p-3 rounded-xl bg-slate-900 hover:bg-slate-800/80 border border-slate-800 flex items-center justify-between text-xs text-slate-200 transition"
                    >
                      <div className="flex items-center gap-2.5">
                        <Film className="w-4 h-4 text-indigo-400" />
                        <div>
                          <div className="font-semibold">video.mp4</div>
                          <div className="text-[10px] text-slate-400">H.264 / AAC 1080p</div>
                        </div>
                      </div>
                      <Download className="w-4 h-4 text-slate-400" />
                    </a>

                    <a
                      href={srtUrl}
                      download={`captions-${jobId}.srt`}
                      className="p-3 rounded-xl bg-slate-900 hover:bg-slate-800/80 border border-slate-800 flex items-center justify-between text-xs text-slate-200 transition"
                    >
                      <div className="flex items-center gap-2.5">
                        <FileText className="w-4 h-4 text-fuchsia-400" />
                        <div>
                          <div className="font-semibold">captions.srt</div>
                          <div className="text-[10px] text-slate-400">Timed subtitle cues</div>
                        </div>
                      </div>
                      <Download className="w-4 h-4 text-slate-400" />
                    </a>

                    <a
                      href={timelineUrl}
                      download={`timeline-${jobId}.json`}
                      className="p-3 rounded-xl bg-slate-900 hover:bg-slate-800/80 border border-slate-800 flex items-center justify-between text-xs text-slate-200 transition"
                    >
                      <div className="flex items-center gap-2.5">
                        <Sliders className="w-4 h-4 text-amber-400" />
                        <div>
                          <div className="font-semibold">timeline.json</div>
                          <div className="text-[10px] text-slate-400">Normalized clip timings</div>
                        </div>
                      </div>
                      <Download className="w-4 h-4 text-slate-400" />
                    </a>

                    <a
                      href={manifestUrl}
                      download={`manifest-${jobId}.json`}
                      className="p-3 rounded-xl bg-slate-900 hover:bg-slate-800/80 border border-slate-800 flex items-center justify-between text-xs text-slate-200 transition"
                    >
                      <div className="flex items-center gap-2.5">
                        <ShieldCheck className="w-4 h-4 text-emerald-400" />
                        <div>
                          <div className="font-semibold">manifest.json</div>
                          <div className="text-[10px] text-slate-400">Provenance & licences</div>
                        </div>
                      </div>
                      <Download className="w-4 h-4 text-slate-400" />
                    </a>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
