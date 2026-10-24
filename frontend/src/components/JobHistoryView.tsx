import React, { useEffect, useState } from 'react';
import {
  History,
  RefreshCw,
  Film,
  AlertCircle,
  Sparkles,
  Building2,
  ChevronRight,
} from 'lucide-react';
import type { JobResponse } from '../types';
import { api } from '../api/client';

interface JobHistoryViewProps {
  onSelectJob: (jobId: string) => void;
}

export const JobHistoryView: React.FC<JobHistoryViewProps> = ({ onSelectJob }) => {
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [error, setError] = useState<string | null>(null);

  const fetchJobs = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listJobs(statusFilter, 50, 0);
      setJobs(data.jobs || []);
      setTotal(data.total || 0);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch jobs';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, [statusFilter]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <History className="w-5 h-5 text-indigo-400" />
            <span>Job Production History</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Audit logs and generated video artifacts for all previous production jobs ({total} total)
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Status Filter */}
          <div className="flex bg-slate-900 border border-slate-800 rounded-xl p-1 text-xs">
            {['all', 'completed', 'running', 'failed'].map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => setStatusFilter(st)}
                className={`px-3 py-1 rounded-lg capitalize font-medium transition cursor-pointer ${
                  statusFilter === st ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={fetchJobs}
            disabled={loading}
            className="p-2 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-xl text-slate-300 hover:text-white transition cursor-pointer"
            title="Refresh jobs"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-indigo-400' : ''}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Jobs Grid */}
      {loading && jobs.length === 0 ? (
        <div className="p-12 text-center text-slate-500 text-sm">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-400" />
          Loading job history...
        </div>
      ) : jobs.length === 0 ? (
        <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-12 text-center space-y-3">
          <Film className="w-10 h-10 text-slate-600 mx-auto" />
          <h3 className="font-semibold text-slate-300 text-sm">No Jobs Found</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            No video generation jobs match the selected filter. Submit a video from the Studio tab to see it here.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {jobs.map((job) => {
            const isCompleted = job.status === 'completed';
            const isFailed = job.status === 'failed';
            const isCreative = job.studio_mode !== 'professional';

            return (
              <div
                key={job.job_id}
                onClick={() => onSelectJob(job.job_id)}
                className="bg-slate-900/70 hover:bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-2xl p-4.5 transition cursor-pointer flex flex-col justify-between space-y-3 group"
              >
                <div>
                  {/* Top Badges */}
                  <div className="flex items-center justify-between mb-2">
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase ${
                        isCompleted
                          ? 'bg-emerald-950/80 border border-emerald-800 text-emerald-400'
                          : isFailed
                          ? 'bg-rose-950/80 border border-rose-800 text-rose-400'
                          : 'bg-indigo-950/80 border border-indigo-800 text-indigo-400 animate-pulse'
                      }`}
                    >
                      {job.status}
                    </span>

                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-md font-medium flex items-center gap-1 ${
                        isCreative
                          ? 'bg-fuchsia-950/50 text-fuchsia-300 border border-fuchsia-800/40'
                          : 'bg-blue-950/50 text-blue-300 border border-blue-800/40'
                      }`}
                    >
                      {isCreative ? <Sparkles className="w-2.5 h-2.5" /> : <Building2 className="w-2.5 h-2.5" />}
                      <span className="capitalize">{job.studio_mode || 'creative'}</span>
                    </span>
                  </div>

                  {/* Title */}
                  <h4 className="font-bold text-sm text-white group-hover:text-indigo-300 transition line-clamp-1">
                    {job.title}
                  </h4>
                  <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                    {job.job_id.slice(0, 8)}...{job.job_id.slice(-4)}
                  </p>
                </div>

                {/* Specs */}
                <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
                  <div className="flex items-center gap-2">
                    <span>{job.aspect_ratio}</span>
                    <span>•</span>
                    <span>{job.duration_seconds.toFixed(1)}s</span>
                    <span>•</span>
                    <span>{job.scenes_count} scenes</span>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-500 group-hover:translate-x-1 transition" />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
