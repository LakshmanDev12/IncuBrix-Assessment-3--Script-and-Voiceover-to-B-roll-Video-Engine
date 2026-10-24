import React, { useState, useEffect } from 'react';
import {
  Search,
  Film,
  CheckCircle2,
  Clock,
} from 'lucide-react';
import type { CandidateMediaItem, ProviderItemResponse } from '../types';
import { api } from '../api/client';

export const MediaExplorerView: React.FC = () => {
  const [query, setQuery] = useState('ocean');
  const [candidates, setCandidates] = useState<CandidateMediaItem[]>([]);
  const [providers, setProviders] = useState<ProviderItemResponse[]>([]);
  const [selectedProvider, setSelectedProvider] = useState('local_cc0');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Load registered providers
    api
      .listProviders()
      .then((data) => setProviders(data))
      .catch(() => {});

    // Initial search
    performSearch('ocean', 'local_cc0');
  }, []);

  const performSearch = async (searchQuery: string, provider: string) => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.searchMedia(searchQuery.trim(), provider, 20);
      setCandidates(res.candidates || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Media search failed';
      setError(msg);
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    performSearch(query, selectedProvider);
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <Film className="w-5 h-5 text-indigo-400" />
          <span>B-Roll Media Library & Provenance Explorer</span>
        </h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Search and audit verified, lawful CC0/Public Domain B-roll clips indexed by the engine
        </p>
      </div>

      {/* Search Bar */}
      <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500">
            <Search className="w-4 h-4" />
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search clips by theme: ocean, clouds, code, drone, abstract..."
            className="w-full pl-10 pr-4 py-2.5 bg-slate-900 border border-slate-800 rounded-xl text-xs sm:text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <select
          value={selectedProvider}
          onChange={(e) => {
            setSelectedProvider(e.target.value);
            performSearch(query, e.target.value);
          }}
          className="p-2.5 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-indigo-500 cursor-pointer"
        >
          {providers.map((p) => (
            <option key={p.name} value={p.name}>
              {p.display_name} {p.is_healthy ? '(Healthy)' : '(Offline)'}
            </option>
          ))}
          {providers.length === 0 && <option value="local_cc0">Local CC0 Library</option>}
        </select>

        <button
          type="submit"
          disabled={loading}
          className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold transition cursor-pointer flex items-center justify-center gap-2 shadow-md shadow-indigo-600/20"
        >
          {loading ? (
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <Search className="w-4 h-4" />
          )}
          <span>Search Media</span>
        </button>
      </form>

      {error && (
        <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs">
          {error}
        </div>
      )}

      {/* Results Grid */}
      {loading ? (
        <div className="p-12 text-center text-slate-500 text-sm">Searching candidate B-roll clips...</div>
      ) : candidates.length === 0 ? (
        <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-12 text-center space-y-2">
          <Film className="w-8 h-8 text-slate-600 mx-auto" />
          <h3 className="font-semibold text-slate-300 text-sm">No Candidates Found</h3>
          <p className="text-xs text-slate-500">Try searching for generic terms like "ocean", "nature", or "city".</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {candidates.map((cand) => (
            <div
              key={cand.id}
              className="bg-slate-900/70 border border-slate-800 rounded-2xl p-4.5 space-y-3 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950/80 border border-emerald-800 text-emerald-400 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    <span>Verified {cand.license_name}</span>
                  </span>
                  <span className="text-xs font-mono text-indigo-400 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    <span>{cand.duration_seconds.toFixed(1)}s</span>
                  </span>
                </div>

                <h4 className="font-bold text-sm text-white">{cand.title}</h4>
                <p className="text-xs text-slate-400 mt-1 line-clamp-2">{cand.description}</p>
              </div>

              <div className="pt-3 border-t border-slate-800/80 space-y-2 text-[11px]">
                {cand.tags && cand.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {cand.tags.map((t) => (
                      <span key={t} className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px]">
                        #{t}
                      </span>
                    ))}
                  </div>
                )}

                <div className="flex items-center justify-between text-slate-400 pt-1">
                  <span className="truncate max-w-[160px]" title={cand.attribution}>
                    By: {cand.creator || 'Open Media Contributor'}
                  </span>
                  <span className="font-mono text-slate-500">{cand.aspect_ratio}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
