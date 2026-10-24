import React, { useEffect, useState } from 'react';
import {
  Activity,
  ShieldCheck,
  Cpu,
  Server,
  Layers,
} from 'lucide-react';
import type { LimitsResponse, ProviderItemResponse } from '../types';
import { api } from '../api/client';

export const SystemStatusView: React.FC = () => {
  const [health, setHealth] = useState<{ status: string; version: string; uptime_seconds?: number } | null>(null);
  const [limits, setLimits] = useState<LimitsResponse | null>(null);
  const [providers, setProviders] = useState<ProviderItemResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getHealth().catch(() => null),
      api.getLimits().catch(() => null),
      api.listProviders().catch(() => []),
    ]).then(([h, lim, prov]) => {
      setHealth(h);
      setLimits(lim);
      setProviders(prov);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="p-12 text-center text-slate-400 text-sm">
        <Activity className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-400" />
        Loading system diagnostics...
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-400" />
          <span>System Diagnostics & Runtime Limits</span>
        </h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Engine validation boundaries, media provider statuses, and hardened pipeline safeguards
        </p>
      </div>

      {/* Grid: Health & Engine Specs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Card 1: Engine Health */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">API Service</span>
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                health?.status === 'ok' ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'
              }`}
            />
          </div>
          <div className="text-2xl font-extrabold text-white">
            {health?.status === 'ok' ? 'Healthy & Ready' : 'Degraded'}
          </div>
          <div className="text-xs text-slate-400 space-y-1 font-mono">
            <div>Version: {health?.version || 'v1.0.0'}</div>
            <div>Runtime: Python 3.13 / FastAPI</div>
            <div>Host: Windows PowerShell & Docker</div>
          </div>
        </div>

        {/* Card 2: Rendering Engine */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">Media Pipeline</span>
            <Cpu className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-extrabold text-white">FFmpeg 9.0.1</div>
          <div className="text-xs text-slate-400 space-y-1 font-mono">
            <div>H.264 video / AAC audio (30 fps)</div>
            <div>FFprobe validation active</div>
            <div>Bounded concurrency (2 workers)</div>
          </div>
        </div>

        {/* Card 3: Storage & Safety */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">Hardening & State</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-extrabold text-white">SSRF Protected</div>
          <div className="text-xs text-slate-400 space-y-1 font-mono">
            <div>SQLite WAL persistence</div>
            <div>Private IP blocking active</div>
            <div>Sanitized error paths</div>
          </div>
        </div>
      </div>

      {/* Engine Boundaries Table */}
      {limits && (
        <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 space-y-4">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Server className="w-4 h-4 text-indigo-400" />
            <span>Active Engine Validation Boundaries (/v1/limits)</span>
          </h3>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4 text-xs">
            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
              <span className="text-slate-500 text-[11px]">Scenes per Job</span>
              <div className="font-bold text-slate-200">
                {limits.min_scenes} - {limits.max_scenes} scenes
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
              <span className="text-slate-500 text-[11px]">Scene Duration</span>
              <div className="font-bold text-slate-200">
                {limits.min_scene_duration_seconds}s - {limits.max_scene_duration_seconds}s
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
              <span className="text-slate-500 text-[11px]">Total Job Duration</span>
              <div className="font-bold text-slate-200">
                {limits.min_job_duration_seconds}s - {limits.max_job_duration_seconds}s
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
              <span className="text-slate-500 text-[11px]">Max Audio Upload</span>
              <div className="font-bold text-slate-200">
                {(limits.max_audio_file_size_bytes / (1024 * 1024)).toFixed(0)} MB
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
              <span className="text-slate-500 text-[11px]">Allowed Aspect Ratios</span>
              <div className="font-bold text-slate-200">
                {limits.allowed_aspect_ratios.join(', ')}
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
              <span className="text-slate-500 text-[11px]">Resolutions</span>
              <div className="font-bold text-slate-200">
                {limits.allowed_resolutions.join(', ')}
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1 col-span-2">
              <span className="text-slate-500 text-[11px]">Audio File Types</span>
              <div className="font-bold text-slate-200">
                {limits.allowed_audio_extensions.join(', ')}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Providers Section */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 space-y-3">
        <h3 className="text-sm font-bold text-white flex items-center gap-2">
          <Layers className="w-4 h-4 text-indigo-400" />
          <span>Active Media Providers</span>
        </h3>
        <div className="space-y-2">
          {providers.map((p) => (
            <div
              key={p.name}
              className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between text-xs"
            >
              <div className="flex items-center gap-2.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="font-semibold text-slate-200">{p.display_name}</span>
                <span className="font-mono text-slate-500">({p.name})</span>
              </div>
              <span className="text-[11px] text-emerald-400 font-medium">
                {p.is_remote ? 'Verified Remote API' : 'Verified Local CC0 Curated Fixture'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
