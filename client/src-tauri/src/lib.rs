use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use std::process::Command;

/// Stem information from analysis.json
#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StemInfo {
    pub name: String,
    pub paths: std::collections::HashMap<String, String>,
    pub has_notes: bool,
    pub peak_db: f64,
}

/// Beat event from analysis.json
#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BeatEvent {
    pub time: f64,
    #[serde(rename = "type")]
    pub beat_type: String,
    pub beat_in_measure: Option<i32>,
}

/// Song analysis data
#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SongAnalysis {
    pub title: Option<String>,
    pub artist: Option<String>,
    pub album: Option<String>,
    pub original_duration: f64,
    pub sample_rate: i32,
    pub tempo_bpm: Option<f64>,
    pub time_signature: Option<(i32, i32)>,
    pub stems: std::collections::HashMap<String, StemInfo>,
    pub beats: Vec<BeatEvent>,
    pub source_file: String,
    pub processing_date: String,
    pub converter_version: String,
}

/// Summary info for song browser
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SongSummary {
    pub path: String,
    pub title: Option<String>,
    pub artist: Option<String>,
    pub duration: f64,
    pub stem_count: usize,
}

/// List songs in a directory that contain analysis.json
#[tauri::command]
fn list_songs(dir: &str) -> Result<Vec<SongSummary>, String> {
    let path = Path::new(dir);
    if !path.exists() {
        return Ok(vec![]);
    }

    let mut songs = Vec::new();

    let entries = fs::read_dir(path).map_err(|e| e.to_string())?;
    for entry in entries {
        let entry = entry.map_err(|e| e.to_string())?;
        let song_path = entry.path();
        let analysis_path = song_path.join("analysis.json");

        if analysis_path.exists() {
            if let Ok(content) = fs::read_to_string(&analysis_path) {
                if let Ok(analysis) = serde_json::from_str::<SongAnalysis>(&content) {
                    songs.push(SongSummary {
                        path: song_path.to_string_lossy().to_string(),
                        title: analysis.title,
                        artist: analysis.artist,
                        duration: analysis.original_duration,
                        stem_count: analysis.stems.len(),
                    });
                }
            }
        }
    }

    Ok(songs)
}

/// Load full analysis.json from a song directory
#[tauri::command]
fn load_analysis(song_dir: &str) -> Result<SongAnalysis, String> {
    let analysis_path = Path::new(song_dir).join("analysis.json");
    let content = fs::read_to_string(&analysis_path).map_err(|e| e.to_string())?;
    serde_json::from_str(&content).map_err(|e| e.to_string())
}

/// Get the absolute path to a stem file
#[tauri::command]
fn get_stem_path(song_dir: &str, relative_path: &str) -> Result<String, String> {
    let stem_path = Path::new(song_dir).join(relative_path);
    if stem_path.exists() {
        Ok(stem_path.to_string_lossy().to_string())
    } else {
        Err(format!("Stem file not found: {}", stem_path.display()))
    }
}

/// Process an audio file through the music-tutor pipeline
#[tauri::command]
fn process_song(audio_file: &str, output_dir: &str, separate_drums: bool) -> Result<String, String> {
    // Get the project root - go up from output_dir (e.g., ../output/song -> ..)
    let output_path = Path::new(output_dir);
    let project_root = output_path
        .parent() // ../output
        .and_then(|p| p.parent()) // ..
        .unwrap_or(Path::new("."));

    let mut args = vec![
        "run",
        "music-tutor",
        "convert",
        audio_file,
        "-o",
        output_dir,
    ];

    if separate_drums {
        args.push("--drum-sep");
    }

    let output = Command::new("uv")
        .args(&args)
        .current_dir(project_root)
        .output()
        .map_err(|e| format!("Failed to start process: {}", e))?;

    if output.status.success() {
        Ok(output_dir.to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stdout = String::from_utf8_lossy(&output.stdout);
        Err(format!(
            "Processing failed:\n{}\n{}",
            stdout.trim(),
            stderr.trim()
        ))
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            list_songs,
            load_analysis,
            get_stem_path,
            process_song
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
