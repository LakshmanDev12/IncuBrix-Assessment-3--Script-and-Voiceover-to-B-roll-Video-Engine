import React, { useState, useRef } from 'react';
import {
  Upload,
  Volume2,
  Globe,
  Clock,
  CheckCircle2,
  AlertCircle,
  X,
  Play,
  Pause,
  Sliders,
} from 'lucide-react';
import type { AudioSourceType } from '../types';
import { api } from '../api/client';

interface AudioUploaderProps {
  audioSource: AudioSourceType;
  onAudioSourceChange: (source: AudioSourceType) => void;
  audioFile: File | null;
  onAudioFileChange: (file: File | null) => void;
  audioUrl: string;
  onAudioUrlChange: (url: string) => void;
  autoRebalance: boolean;
  onAutoRebalanceChange: (enabled: boolean) => void;
  detectedDuration: number | null;
  onDurationDetected: (duration: number | null) => void;
}

export const AudioUploader: React.FC<AudioUploaderProps> = ({
  audioSource,
  onAudioSourceChange,
  audioFile,
  onAudioFileChange,
  audioUrl,
  onAudioUrlChange,
  autoRebalance,
  onAutoRebalanceChange,
  detectedDuration,
  onDurationDetected,
}) => {
  const [probingUrl, setProbingUrl] = useState(false);
  const [probeResult, setProbeResult] = useState<{ valid: boolean; duration?: number; error?: string } | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioPreviewUrl, setAudioPreviewUrl] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleFileSelect = (file: File) => {
    onAudioFileChange(file);
    const objectUrl = URL.createObjectURL(file);
    setAudioPreviewUrl(objectUrl);

    // Read audio duration using browser Audio object
    const audioObj = new Audio(objectUrl);
    audioObj.onloadedmetadata = () => {
      if (audioObj.duration && !isNaN(audioObj.duration) && isFinite(audioObj.duration)) {
        onDurationDetected(audioObj.duration);
      }
    };
  };

  const handleClearFile = () => {
    if (audioPreviewUrl) {
      URL.revokeObjectURL(audioPreviewUrl);
    }
    setAudioPreviewUrl(null);
    onAudioFileChange(null);
    onDurationDetected(null);
    setIsPlaying(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleProbeUrl = async () => {
    if (!audioUrl.trim()) return;
    setProbingUrl(true);
    setProbeResult(null);
    try {
      const res = await api.probeAudioUrl(audioUrl.trim());
      if (res.valid) {
        setProbeResult({ valid: true, duration: res.duration_seconds });
        if (res.duration_seconds) {
          onDurationDetected(res.duration_seconds);
        }
      } else {
        setProbeResult({ valid: false, error: 'Audio URL could not be validated.' });
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Validation failed';
      setProbeResult({ valid: false, error: message });
    } finally {
      setProbingUrl(false);
    }
  };

  const togglePlayback = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current
        .play()
        .then(() => setIsPlaying(true))
        .catch(() => setIsPlaying(false));
    }
  };

  return (
    <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-400 flex items-center justify-center">
            <Volume2 className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">Voiceover & Audio Track</h3>
            <p className="text-xs text-slate-400">
              Provide narration audio or let scene timings determine playback length
            </p>
          </div>
        </div>

        {/* Source Selector Tabs */}
        <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
          <button
            type="button"
            onClick={() => onAudioSourceChange('none')}
            className={`px-2.5 py-1 rounded cursor-pointer transition ${
              audioSource === 'none' ? 'bg-slate-800 text-white font-medium' : 'text-slate-400 hover:text-white'
            }`}
          >
            None (Visuals only)
          </button>
          <button
            type="button"
            onClick={() => onAudioSourceChange('upload')}
            className={`px-2.5 py-1 rounded cursor-pointer transition ${
              audioSource === 'upload' ? 'bg-slate-800 text-white font-medium' : 'text-slate-400 hover:text-white'
            }`}
          >
            Upload File
          </button>
          <button
            type="button"
            onClick={() => onAudioSourceChange('url')}
            className={`px-2.5 py-1 rounded cursor-pointer transition ${
              audioSource === 'url' ? 'bg-slate-800 text-white font-medium' : 'text-slate-400 hover:text-white'
            }`}
          >
            Audio URL
          </button>
        </div>
      </div>

      {/* Mode A: None */}
      {audioSource === 'none' && (
        <div className="p-4 rounded-xl bg-slate-950/50 border border-slate-800/80 text-xs text-slate-400 flex items-center gap-3">
          <Clock className="w-5 h-5 text-indigo-400 flex-shrink-0" />
          <div>
            <p className="text-slate-300 font-medium">Silent Video / Custom Music Overlay</p>
            <p className="text-slate-500">
              Scene durations will determine the timing of visual B-roll cuts directly.
            </p>
          </div>
        </div>
      )}

      {/* Mode B: Upload Audio File */}
      {audioSource === 'upload' && (
        <div className="space-y-3">
          {!audioFile ? (
            <div
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                  handleFileSelect(e.dataTransfer.files[0]);
                }
              }}
              className="border-2 border-dashed border-slate-700 hover:border-indigo-500 rounded-xl p-6 text-center cursor-pointer transition bg-slate-950/40 hover:bg-slate-950/70"
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".wav,.mp3,.m4a,.aac"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    handleFileSelect(e.target.files[0]);
                  }
                }}
              />
              <Upload className="w-8 h-8 text-indigo-400 mx-auto mb-2 animate-bounce" />
              <p className="text-xs font-semibold text-slate-200">
                Click or drag & drop narration audio
              </p>
              <p className="text-[11px] text-slate-500 mt-1">
                Supported formats: WAV, MP3, M4A, AAC (Max 50MB, up to 5 minutes)
              </p>
            </div>
          ) : (
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={togglePlayback}
                  className="w-9 h-9 rounded-full bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center transition cursor-pointer shadow-md"
                >
                  {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
                </button>
                <div>
                  <p className="text-xs font-medium text-slate-200 truncate max-w-xs sm:max-w-md">
                    {audioFile.name}
                  </p>
                  <div className="flex items-center gap-2 text-[11px] text-slate-400">
                    <span>{(audioFile.size / (1024 * 1024)).toFixed(2)} MB</span>
                    {detectedDuration && (
                      <>
                        <span>•</span>
                        <span className="text-indigo-400 font-medium">
                          {detectedDuration.toFixed(1)}s duration
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {audioPreviewUrl && (
                  <audio
                    ref={audioRef}
                    src={audioPreviewUrl}
                    onEnded={() => setIsPlaying(false)}
                    className="hidden"
                  />
                )}
                <button
                  type="button"
                  onClick={handleClearFile}
                  className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition cursor-pointer"
                  title="Remove audio"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Mode C: Audio URL */}
      {audioSource === 'url' && (
        <div className="space-y-2">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
                <Globe className="w-4 h-4" />
              </div>
              <input
                type="url"
                value={audioUrl}
                onChange={(e) => {
                  onAudioUrlChange(e.target.value);
                  setProbeResult(null);
                }}
                placeholder="https://example.com/narration.mp3"
                className="w-full pl-9 pr-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-indigo-500 placeholder-slate-600"
              />
            </div>
            <button
              type="button"
              disabled={probingUrl || !audioUrl.trim()}
              onClick={handleProbeUrl}
              className="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-medium transition cursor-pointer flex items-center gap-1.5"
            >
              {probingUrl ? (
                <>
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Probing...</span>
                </>
              ) : (
                <span>Validate & Probe</span>
              )}
            </button>
          </div>

          {probeResult && (
            <div
              className={`p-3 rounded-lg text-xs flex items-center gap-2 ${
                probeResult.valid
                  ? 'bg-emerald-950/40 border border-emerald-800/60 text-emerald-300'
                  : 'bg-rose-950/40 border border-rose-800/60 text-rose-300'
              }`}
            >
              {probeResult.valid ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                  <span>
                    Valid audio verified via SSRF-safe probe: Duration {probeResult.duration?.toFixed(1)}s
                  </span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                  <span>{probeResult.error}</span>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Auto-rebalance Option */}
      {audioSource !== 'none' && (
        <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sliders className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-xs text-slate-300 font-medium">
              Auto-rebalance scene durations to voiceover length
            </span>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={autoRebalance}
              onChange={(e) => onAutoRebalanceChange(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600"></div>
          </label>
        </div>
      )}
    </div>
  );
};
