import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { FolderOpen, Music, Clock, Layers, Plus, Loader2 } from "lucide-react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { type SongSummary } from "../types/analysis";
import { formatTime, cn } from "../lib/utils";

export function SongBrowser() {
  const [songs, setSongs] = useState<SongSummary[]>([]);
  const [outputDir, setOutputDir] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingError, setProcessingError] = useState<string | null>(null);
  const [separateDrums, setSeparateDrums] = useState(false);
  const navigate = useNavigate();

  // Try to load songs from default output directory on mount
  useEffect(() => {
    const defaultDir = "../output"; // Relative to client/
    loadSongs(defaultDir);
  }, []);

  async function loadSongs(dir: string) {
    setIsLoading(true);
    try {
      const songList = await invoke<SongSummary[]>("list_songs", { dir });
      setSongs(songList);
      setOutputDir(dir);
    } catch (error) {
      console.error("Failed to load songs:", error);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleOpenFolder() {
    const selected = await open({
      directory: true,
      multiple: false,
      title: "Select output folder containing processed songs",
    });

    if (selected) {
      loadSongs(selected);
    }
  }

  function handleSelectSong(song: SongSummary) {
    navigate("/player", { state: { songPath: song.path } });
  }

  async function handleProcessNewSong() {
    const selected = await open({
      directory: false,
      multiple: false,
      title: "Select an audio file to process",
      filters: [
        {
          name: "Audio Files",
          extensions: ["mp3", "wav", "flac", "m4a", "ogg", "aac"],
        },
      ],
    });

    if (!selected) return;

    setIsProcessing(true);
    setProcessingError(null);

    try {
      // Derive output path from filename
      const fileName = selected.split(/[/\\]/).pop() || "song";
      const songName = fileName.replace(/\.[^.]+$/, "");
      const songOutputDir = `${outputDir || "../output"}/${songName}`;

      await invoke("process_song", {
        audioFile: selected,
        outputDir: songOutputDir,
        separateDrums,
      });

      // Refresh song list
      await loadSongs(outputDir || "../output");
    } catch (error) {
      console.error("Failed to process song:", error);
      setProcessingError(String(error));
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-900 flex items-center justify-center p-8">
      <div className="w-full max-w-3xl">
        <h1
          className="text-6xl text-amber-400 mb-12 text-center uppercase tracking-wider"
          style={{ textShadow: "4px 4px 0px rgba(0,0,0,0.8)" }}
        >
          Music Tutor
        </h1>

        {/* Action Buttons */}
        <div className="flex gap-4 mb-8">
          <button
            onClick={handleOpenFolder}
            className={cn(
              "flex-1 py-6 px-8 rounded-xl",
              "border-4 border-zinc-700 bg-zinc-800/50",
              "flex items-center justify-center gap-4",
              "text-xl text-zinc-300 uppercase tracking-wider",
              "hover:border-amber-500 hover:text-amber-400 transition-all"
            )}
            style={{
              boxShadow:
                "inset 0 4px 8px rgba(0,0,0,0.3), 0 8px 16px rgba(0,0,0,0.5)",
            }}
          >
            <FolderOpen className="w-8 h-8" />
            Open Folder
          </button>

          <button
            onClick={handleProcessNewSong}
            disabled={isProcessing}
            className={cn(
              "flex-1 py-6 px-8 rounded-xl",
              "border-4 border-amber-600 bg-amber-600/20",
              "flex items-center justify-center gap-4",
              "text-xl text-amber-400 uppercase tracking-wider",
              "hover:border-amber-500 hover:bg-amber-600/30 transition-all",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
            style={{
              boxShadow:
                "inset 0 4px 8px rgba(0,0,0,0.3), 0 8px 16px rgba(0,0,0,0.5)",
            }}
          >
            {isProcessing ? (
              <>
                <Loader2 className="w-8 h-8 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <Plus className="w-8 h-8" />
                Process New Song
              </>
            )}
          </button>
        </div>

        {/* Processing Options */}
        <label className="flex items-center gap-3 mb-8 cursor-pointer group">
          <input
            type="checkbox"
            checked={separateDrums}
            onChange={(e) => setSeparateDrums(e.target.checked)}
            className="w-5 h-5 rounded border-2 border-zinc-600 bg-zinc-800 checked:bg-amber-500 checked:border-amber-500 cursor-pointer"
          />
          <span className="text-zinc-400 group-hover:text-zinc-300 transition-colors">
            Separate drum tracks
          </span>
        </label>

        {/* Processing Error */}
        {processingError && (
          <div className="mb-8 p-4 rounded-xl border-4 border-red-600 bg-red-900/20 text-red-400">
            <p className="font-bold mb-2">Processing Error</p>
            <p className="text-sm whitespace-pre-wrap">{processingError}</p>
          </div>
        )}

        {/* Song List */}
        <div
          className="border-8 border-zinc-700 rounded-2xl p-6 bg-zinc-800/50"
          style={{
            boxShadow:
              "inset 0 4px 8px rgba(0,0,0,0.3), 0 8px 16px rgba(0,0,0,0.5)",
          }}
        >
          <h2 className="text-lg text-zinc-400 mb-4 uppercase tracking-wider">
            Processed Songs
          </h2>

          {isLoading ? (
            <div className="py-12 text-center text-zinc-500">Loading...</div>
          ) : songs.length === 0 ? (
            <div className="py-12 text-center text-zinc-500">
              <Music className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>No processed songs found</p>
              <p className="text-sm mt-2">
                Run the music-tutor pipeline to process songs
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {songs.map((song) => (
                <button
                  key={song.path}
                  onClick={() => handleSelectSong(song)}
                  className={cn(
                    "w-full p-4 rounded-xl border-4 border-zinc-700 bg-zinc-900",
                    "flex items-center gap-4 text-left",
                    "hover:border-amber-500 active:translate-y-1 transition-all"
                  )}
                  style={{
                    boxShadow:
                      "0 4px 0 0 rgb(63, 63, 70), 0 6px 12px rgba(0,0,0,0.5)",
                  }}
                >
                  <div className="p-3 rounded-lg bg-amber-500/20 border-2 border-amber-500/30">
                    <Music className="w-6 h-6 text-amber-400" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <h3 className="text-xl text-zinc-200 truncate">
                      {song.title || "Unknown Title"}
                    </h3>
                    <p className="text-zinc-500 truncate">
                      {song.artist || "Unknown Artist"}
                    </p>
                  </div>

                  <div className="flex items-center gap-4 text-zinc-400">
                    <div className="flex items-center gap-1">
                      <Clock className="w-4 h-4" />
                      <span>{formatTime(song.duration)}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Layers className="w-4 h-4" />
                      <span>{song.stemCount}</span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Current directory indicator */}
        {outputDir && (
          <p className="mt-4 text-sm text-zinc-500 text-center truncate">
            {outputDir}
          </p>
        )}
      </div>
    </div>
  );
}
