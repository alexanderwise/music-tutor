# Stem Visualization Specification

**Status**: Draft
**Author**: [Your Name]
**Date**: 2025-12-30
**Target**: Music Tutor Tauri/React Client

## Overview

This specification describes the implementation of per-stem visualizations in the Music Tutor application. The goal is to provide learners with visual representations of musical content synchronized with audio playback.

### Visualization Types

| Stem Type | Visualization | Data Source |
|-----------|---------------|-------------|
| Drum components (kick, snare, hh, etc.) | Pseudo-tablature grid | `drumStrikes` |
| Piano | Piano roll | `notes[piano]` |
| Guitar | Piano roll (v1), Tablature (future) | `notes[guitar]` |
| Bass | Piano roll (v1), Tablature (future) | `notes[bass]` |
| Vocals | Karaoke lyrics + pitch contour | `lyrics` + `notes[vocals]` |
| Other/fallback | Waveform | Audio file |

---

## Architecture

### Component Hierarchy

```
PlayerPage
├── PlaybackControls (existing)
├── StemMixer (existing)
│   └── StemRow
│       ├── VolumeSlider (existing)
│       ├── MuteButton (existing)
│       └── VisualizationToggle (NEW)
└── VisualizationPanel (NEW)
    ├── VisualizationHeader
    │   ├── StemLabel
    │   ├── ViewToggle (visualization | waveform)
    │   └── ZoomControls (optional)
    ├── TimeRuler
    │   └── BeatGrid
    └── VisualizationContent
        ├── DrumTabView
        ├── PianoRollView
        ├── LyricsView
        └── WaveformView
```

### State Management

```typescript
interface VisualizationState {
  activeStem: string | null;        // Which stem's visualization is shown
  viewMode: 'visualization' | 'waveform';
  viewport: {
    startTime: number;              // Left edge in seconds (at current speed)
    endTime: number;                // Right edge in seconds
    pixelsPerSecond: number;        // Zoom level
  };
  followPlayhead: boolean;          // Auto-scroll with playback
}
```

---

## Phase 0: Infrastructure

**Goal**: Build the visualization framework that all stem types will use.

### 0.1 Visualization Toggle Button

Add a button to each stem row that opens/closes the visualization panel for that stem.

**Location**: `StemRow` component, next to existing mute/solo controls

**Behavior**:
- Click toggles visualization panel visibility
- If panel is showing a different stem, switch to clicked stem
- If panel is showing same stem, close panel
- Button indicates whether visualization data is available for this stem

**Visual states**:
- Disabled/grayed: No visualization data available
- Inactive: Visualization available but panel closed
- Active: This stem's visualization is currently displayed

### 0.2 Visualization Panel Container

A collapsible panel below the playback controls that displays the active visualization.

**Requirements**:
- Fixed height (configurable, ~200-300px default)
- Horizontal scrolling for timeline
- Resizable (drag handle on bottom edge) - optional v1
- Close button in header

### 0.3 Time Synchronization

All visualizations must stay synchronized with audio playback.

**Time Scaling**:
```typescript
// All analysis data is stored at 1.0x speed
// Convert to display time based on current playback speed
function toDisplayTime(analysisTime: number, speed: number): number {
  return analysisTime / speed;
}

function toAnalysisTime(displayTime: number, speed: number): number {
  return displayTime * speed;
}
```

**Playhead Following**:
- Visualization viewport auto-scrolls to keep playhead visible
- Playhead position indicator (vertical line) shows current time
- User can disable auto-follow to manually scroll

### 0.4 Loop-Aware Viewport

When a loop is active, the visualization should focus on the loop region.

**Behavior**:
- If loop is active, constrain viewport to show loop region
- Optionally dim/hide content outside loop bounds
- When loop is disabled, restore previous viewport

### 0.5 Beat Grid Overlay

Display beat markers aligned to the `beats` data from analysis.

**Visual design**:
- Downbeats (beat 1): Bold vertical line
- Other beats: Light vertical line
- Measure numbers above ruler
- Time signature indicator

**Data source**: `analysis.beats[]`

```typescript
interface BeatEvent {
  time: number;           // seconds at 1.0x
  type: 'beat' | 'downbeat';
  beatInMeasure: number;  // 1, 2, 3, 4 for 4/4
}
```

### 0.6 Waveform Fallback View

Always available as an alternative to specialized visualizations.

**Use cases**:
- Stems without visualization data
- User wants to see audio shape
- Debugging/identifying ghost notes vs real hits

**Implementation options**:
- Pre-rendered waveform image (generated in pipeline)
- Real-time waveform rendering (more flexible, higher CPU)
- Recommendation: Pre-render in pipeline, store as PNG or JSON peaks

---

## Phase 1: Drum Tablature

**Goal**: Display drum strikes as a grid showing when each drum component is hit.

### 1.1 Data Source

```typescript
// From analysis.json
interface DrumStrikes {
  [component: string]: DrumStrike[];  // kick, snare, hh, ride, crash, toms
}

interface DrumStrike {
  time: number;      // seconds at 1.0x
  velocity: number;  // 0.0-1.0
}
```

### 1.2 Visual Design

```
Time →   0:00    0:01    0:02    0:03    0:04
         |       |       |       |       |
Crash    ·───────·───────·───X───·───────·
Ride     ·─x─x─x─·─x─x─x─·───────·─x─x─x─·
HH       ·─x─x─x─·─x─x─x─·─x─x─x─·─x─x─x─·
Snare    ·───O───·───O───·───O───·───O───·
Toms     ·───────·───────·─o─────·───────·
Kick     ·─o─────·─o─────·─o─o───·─o─────·
         ▲
         Playhead
```

**Row order** (top to bottom): crash, ride, hh, snare, toms, kick
- Cymbals at top, kick at bottom (standard drum notation convention)

**Hit markers**:
- Size/opacity proportional to velocity
- Style options: filled circle, X, vertical line
- Color per drum component (for accessibility)

### 1.3 Interaction

- Hover on hit: Show timestamp and velocity
- Click on hit: Seek playback to that time
- Scroll horizontally: Navigate timeline
- Zoom: Adjust pixelsPerSecond

### 1.4 Component Visibility

Not all songs have all drum components. Only show rows for components that have strikes.

```typescript
const visibleComponents = Object.entries(drumStrikes)
  .filter(([_, strikes]) => strikes.length > 0)
  .map(([name, _]) => name);
```

---

## Phase 2: Piano Roll

**Goal**: Display pitched notes as rectangles on a piano roll grid.

### 2.1 Data Source

```typescript
// From analysis.json
interface Note {
  start: number;     // seconds at 1.0x
  end: number;       // seconds at 1.0x
  pitch: number;     // MIDI note number (0-127)
  velocity: number;  // 0.0-1.0
  pitchBend?: PitchBendPoint[];
}

interface PitchBendPoint {
  time: number;   // seconds relative to note start
  cents: number;  // deviation from base pitch
}
```

### 2.2 Visual Design

```
     Time →
C5   ████░░░░░░░░░████████░░░░░░░░░░░░░
B4   ░░░░░░░░░░░░░░░░░░░░░░████░░░░░░░░
A#4  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
A4   ░░░████████░░░░░░░░░░░░░░░░████░░░
G#4  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
...
     ▲
     Playhead
```

**Layout**:
- Y-axis: Pitch (MIDI note numbers, labeled with note names)
- X-axis: Time
- Note rectangles: X position = start, width = duration, Y = pitch row

**Pitch range**:
- Auto-detect from note data: show from (min pitch - 2) to (max pitch + 2)
- Piano keyboard reference on left edge (optional)

**Note coloring**:
- Opacity or color intensity based on velocity
- Different color for currently-playing notes

**Pitch bend visualization** (optional for v1):
- Slight vertical wobble following pitchBend curve
- Or color gradient indicating bend direction

### 2.3 Applicable Stems

Piano roll works for any stem with note data:
- `piano` - Primary use case
- `guitar` - Until tablature is implemented
- `bass` - Until tablature is implemented
- `vocals` - Shows sung pitches
- `other` - May contain pitched content

### 2.4 Interaction

- Hover on note: Show pitch name, start/end time, velocity
- Click on note: Seek to note start time
- Scroll vertically: Navigate pitch range
- Scroll horizontally: Navigate timeline

---

## Phase 3: Lyrics Display

**Goal**: Karaoke-style word-by-word highlighting synchronized with playback, plus vocal pitch contour.

### 3.1 Data Sources

```typescript
// Lyrics from analysis.json
interface LyricsData {
  source: 'lrc' | 'txt' | 'transcribed';
  lines: LyricLine[];
}

interface LyricLine {
  text: string;
  start: number;  // seconds
  end: number;
  words: LyricWord[];
}

interface LyricWord {
  text: string;
  start: number;
  end: number;
  confidence: number;
}

// Pitch from notes[vocals]
// Same Note interface as piano roll
```

### 3.2 Visual Design

```
┌─────────────────────────────────────────────────┐
│                  ♪ ~~~ pitch contour ~~~ ♪      │  ← Optional pitch viz
├─────────────────────────────────────────────────┤
│                                                 │
│   "I'm going to the store to buy some milk"    │  ← Current line
│    ▓▓▓ ▓▓▓▓▓▓                                   │  ← Highlight progress
│                                                 │
│   "And maybe get some bread"                   │  ← Next line (dimmed)
│                                                 │
└─────────────────────────────────────────────────┘
```

**Layout**:
- Center current line
- Show 1 previous line (dimmed) above
- Show 1-2 upcoming lines (dimmed) below
- Pitch contour above or behind lyrics (optional)

**Word highlighting**:
- Words before current time: Highlighted color
- Current word: Highlighted + emphasis (bold/underline)
- Words after current time: Default color

### 3.3 Pitch Contour (Optional Enhancement)

Display `notes[vocals]` as a melodic line above lyrics:
- Horizontal axis: Time (aligned with lyrics)
- Vertical axis: Pitch
- Line or connected dots showing pitch trajectory

**Alignment consideration**:
- Don't try to align specific notes to specific words (melisma makes this complex)
- Just show pitch as a parallel track
- User can correlate visually

### 3.4 Edge Cases

- **No lyrics**: Show "No lyrics available" message, offer pitch-only view
- **Sparse lyrics**: May have long gaps between lines (instrumental sections)
- **Low confidence words**: Consider visual indicator (lighter color?)

### 3.5 Interaction

- Click on word: Seek to word start time
- Click on line: Seek to line start time

---

## Future Enhancement: Guitar/Bass Tablature

**Status**: Deferred to future version

**Challenge**: Converting MIDI note numbers to (string, fret) positions requires:
1. Detecting or assuming the instrument tuning
2. Choosing optimal fret positions to minimize hand movement
3. Handling chords (multiple simultaneous notes)

**Potential approaches**:
1. **Simple heuristic**: Always use lowest fret position
   - Pro: Easy to implement
   - Con: May produce unplayable fingerings

2. **Hand position tracking**: Minimize jumps between positions
   - Pro: More playable results
   - Con: Still may miss stylistic conventions

3. **ML-based**: Train a model on real guitar tabs
   - Pro: Can learn stylistic conventions, detect tuning
   - Con: Requires training data, more complex pipeline
   - Note: Research models exist (e.g., MIDI-to-Tab transformers on HuggingFace)

**Recommendation**: Start with piano roll for guitar/bass. Investigate ML approaches as a separate research spike.

---

## Data Requirements Summary

### Required in analysis.json

| Field | Used By | Status |
|-------|---------|--------|
| `beats` | All (beat grid) | ✅ Available |
| `drumStrikes` | Drum tab | ✅ Available |
| `notes[piano]` | Piano roll | ✅ Available |
| `notes[guitar]` | Piano roll | ✅ Available |
| `notes[bass]` | Piano roll | ✅ Available |
| `notes[vocals]` | Lyrics pitch | ✅ Available |
| `lyrics` | Lyrics display | ✅ Available |
| `tempo_bpm` | Beat grid | ✅ Available |
| `time_signature` | Beat grid | ✅ Available |

### Optional Enhancements

| Field | Purpose | Status |
|-------|---------|--------|
| Waveform peaks | Waveform fallback | ❌ Not yet generated |
| Tuning detection | Guitar tab | ❌ Future |
| Speaker diarization | Multi-voice lyrics | ❌ Future |

---

## Implementation Checklist

### Phase 0: Infrastructure
- [ ] Add visualization toggle button to StemRow
- [ ] Create VisualizationPanel container component
- [ ] Implement time scaling utilities (1.0x ↔ current speed)
- [ ] Implement viewport state management
- [ ] Add playhead position indicator
- [ ] Implement auto-scroll following playhead
- [ ] Add loop-aware viewport constraints
- [ ] Implement beat grid component using `beats` data
- [ ] Create TimeRuler component with measure numbers
- [ ] Implement waveform fallback view

### Phase 1: Drum Tablature
- [ ] Create DrumTabView component
- [ ] Implement row layout for drum components
- [ ] Render strike markers with velocity-based sizing
- [ ] Align strikes to beat grid
- [ ] Add hover tooltips
- [ ] Add click-to-seek functionality
- [ ] Handle missing drum components gracefully

### Phase 2: Piano Roll
- [ ] Create PianoRollView component
- [ ] Implement pitch axis with note labels
- [ ] Render note rectangles
- [ ] Implement velocity-based coloring
- [ ] Auto-detect and set pitch range from data
- [ ] Add keyboard reference on left edge
- [ ] Highlight currently-playing notes
- [ ] Add hover tooltips
- [ ] Add click-to-seek functionality
- [ ] (Optional) Implement pitch bend visualization

### Phase 3: Lyrics Display
- [ ] Create LyricsView component
- [ ] Implement line-by-line display
- [ ] Implement word-by-word highlighting
- [ ] Style previous/current/next lines differently
- [ ] Add click-to-seek on words
- [ ] Handle missing lyrics gracefully
- [ ] (Optional) Add pitch contour overlay

### Integration
- [ ] Wire visualization toggle to panel visibility
- [ ] Connect playback state to visualization updates
- [ ] Handle speed changes (re-scale all times)
- [ ] Test with multiple songs of varying content
- [ ] Performance optimization for long songs

---

## Testing Strategy

### Unit Tests

```typescript
// Time scaling
test('toDisplayTime scales correctly', () => {
  expect(toDisplayTime(10, 0.5)).toBe(20);   // Half speed = double display time
  expect(toDisplayTime(10, 1.0)).toBe(10);   // Normal speed
  expect(toDisplayTime(10, 2.0)).toBe(5);    // Double speed = half display time
});

// Viewport calculations
test('viewport contains time', () => {
  const viewport = { startTime: 10, endTime: 20, pixelsPerSecond: 100 };
  expect(viewportContains(viewport, 15)).toBe(true);
  expect(viewportContains(viewport, 5)).toBe(false);
});

// Pitch utilities
test('midiToPitchName converts correctly', () => {
  expect(midiToPitchName(60)).toBe('C4');   // Middle C
  expect(midiToPitchName(69)).toBe('A4');   // A440
  expect(midiToPitchName(45)).toBe('A2');   // Bass range
});
```

### Visual Regression Tests

Use a tool like Percy, Chromatic, or Playwright screenshots:

- Drum tab with known strike pattern
- Piano roll with known chord progression
- Lyrics display at various playback positions
- All views at different zoom levels
- All views with loop active

### Integration Tests

- Visualization updates when playback starts/stops
- Viewport scrolls to follow playhead
- Speed change re-renders correctly
- Loop enable/disable updates viewport
- Stem switching updates panel content

### Manual Test Checklist

- [ ] All drum components display when present
- [ ] Drum hits align with audible sounds
- [ ] Piano roll notes align with audible notes
- [ ] Lyrics highlight at correct times
- [ ] Playhead stays visible during playback
- [ ] Loop region displays correctly
- [ ] Speed changes don't break sync
- [ ] Waveform toggle works for all stems
- [ ] Performance acceptable with 5+ minute songs
- [ ] Works with songs missing some data (no lyrics, no drums, etc.)

---

## Open Questions

1. **Waveform generation**: Should we pre-render waveform images in the pipeline, or render on-demand in the client?

2. **Zoom controls**: Should users be able to adjust zoom, or auto-fit based on content density?

3. **Mobile support**: Is this desktop-only for v1?

4. **Keyboard shortcuts**: Should we add shortcuts for common actions (toggle visualization, zoom, etc.)?

5. **Color themes**: Should visualization colors adapt to a light/dark theme?

---

## Appendix: Reference Implementations

- **Drum notation**: Guitar Pro, Noteflight
- **Piano roll**: Ableton Live, FL Studio, MIDI editors
- **Lyrics display**: Karaoke apps, Spotify lyrics, Apple Music lyrics
- **Waveform**: Audacity, SoundCloud, any DAW

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-30 | 0.1 | Initial draft |
