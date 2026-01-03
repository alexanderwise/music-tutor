import { useState, useCallback, useRef, useEffect } from "react";

export interface ViewportState {
  startTime: number; // Left edge in seconds (at current speed)
  endTime: number; // Right edge in seconds
  pixelsPerSecond: number; // Zoom level
}

export interface VisualizationState {
  activeStem: string | null; // Which stem's visualization is shown
  viewMode: "visualization" | "waveform";
  viewport: ViewportState;
  followPlayhead: boolean; // Auto-scroll with playback
  isExpanded: boolean; // Whether panel is visible
}

const DEFAULT_PIXELS_PER_SECOND = 100;
const VIEWPORT_PADDING_SECONDS = 0.5; // Padding before playhead hits edge

export function useVisualization(duration: number) {
  const [state, setState] = useState<VisualizationState>({
    activeStem: null,
    viewMode: "visualization",
    viewport: {
      startTime: 0,
      endTime: 10, // Default 10 second window
      pixelsPerSecond: DEFAULT_PIXELS_PER_SECOND,
    },
    followPlayhead: true,
    isExpanded: false,
  });

  const containerRef = useRef<HTMLDivElement>(null);

  // Update viewport to ensure playhead is visible
  const updateViewportForPlayhead = useCallback(
    (currentTime: number) => {
      if (!state.followPlayhead || !state.isExpanded) return;

      setState((prev) => {
        const { viewport } = prev;
        const viewportWidth = viewport.endTime - viewport.startTime;

        // Check if playhead is near the right edge
        const rightThreshold = viewport.endTime - VIEWPORT_PADDING_SECONDS;
        if (currentTime > rightThreshold) {
          // Scroll so playhead is at 25% from left
          const newStartTime = Math.max(0, currentTime - viewportWidth * 0.25);
          return {
            ...prev,
            viewport: {
              ...viewport,
              startTime: newStartTime,
              endTime: newStartTime + viewportWidth,
            },
          };
        }

        // Check if playhead is before the left edge (e.g., after loop)
        if (currentTime < viewport.startTime) {
          const newStartTime = Math.max(0, currentTime - VIEWPORT_PADDING_SECONDS);
          return {
            ...prev,
            viewport: {
              ...viewport,
              startTime: newStartTime,
              endTime: newStartTime + viewportWidth,
            },
          };
        }

        return prev;
      });
    },
    [state.followPlayhead, state.isExpanded]
  );

  // Set active stem and expand panel
  const setActiveStem = useCallback((stemName: string | null) => {
    setState((prev) => ({
      ...prev,
      activeStem: stemName,
      isExpanded: stemName !== null,
    }));
  }, []);

  // Toggle visualization for a stem
  const toggleStemVisualization = useCallback((stemName: string) => {
    setState((prev) => {
      if (prev.activeStem === stemName && prev.isExpanded) {
        // Clicking same stem - close panel
        return { ...prev, isExpanded: false };
      }
      // Open/switch to this stem
      return { ...prev, activeStem: stemName, isExpanded: true };
    });
  }, []);

  // Close the panel
  const closePanel = useCallback(() => {
    setState((prev) => ({ ...prev, isExpanded: false }));
  }, []);

  // Toggle view mode
  const toggleViewMode = useCallback(() => {
    setState((prev) => ({
      ...prev,
      viewMode: prev.viewMode === "visualization" ? "waveform" : "visualization",
    }));
  }, []);

  // Toggle follow playhead
  const toggleFollowPlayhead = useCallback(() => {
    setState((prev) => ({
      ...prev,
      followPlayhead: !prev.followPlayhead,
    }));
  }, []);

  // Zoom in/out
  const zoom = useCallback(
    (factor: number, centerTime?: number) => {
      setState((prev) => {
        const { viewport } = prev;
        const newPPS = Math.max(20, Math.min(400, viewport.pixelsPerSecond * factor));
        const center = centerTime ?? (viewport.startTime + viewport.endTime) / 2;

        // Calculate container width to determine viewport width
        const containerWidth = containerRef.current?.clientWidth ?? 1000;
        const viewportWidth = containerWidth / newPPS;

        // Center on the zoom point
        let newStartTime = center - viewportWidth / 2;
        let newEndTime = center + viewportWidth / 2;

        // Clamp to valid range
        if (newStartTime < 0) {
          newStartTime = 0;
          newEndTime = viewportWidth;
        }
        if (newEndTime > duration) {
          newEndTime = duration;
          newStartTime = Math.max(0, duration - viewportWidth);
        }

        return {
          ...prev,
          viewport: {
            pixelsPerSecond: newPPS,
            startTime: newStartTime,
            endTime: newEndTime,
          },
        };
      });
    },
    [duration]
  );

  // Scroll viewport
  const scrollTo = useCallback((startTime: number) => {
    setState((prev) => {
      const viewportWidth = prev.viewport.endTime - prev.viewport.startTime;
      const newStartTime = Math.max(0, startTime);
      return {
        ...prev,
        viewport: {
          ...prev.viewport,
          startTime: newStartTime,
          endTime: newStartTime + viewportWidth,
        },
        followPlayhead: false, // Disable auto-follow when manually scrolling
      };
    });
  }, []);

  // Update viewport dimensions when container resizes
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const updateViewportSize = () => {
      setState((prev) => {
        const containerWidth = container.clientWidth;
        const viewportWidth = containerWidth / prev.viewport.pixelsPerSecond;
        return {
          ...prev,
          viewport: {
            ...prev.viewport,
            endTime: prev.viewport.startTime + viewportWidth,
          },
        };
      });
    };

    const resizeObserver = new ResizeObserver(updateViewportSize);
    resizeObserver.observe(container);

    return () => resizeObserver.disconnect();
  }, []);

  return {
    ...state,
    containerRef,
    setActiveStem,
    toggleStemVisualization,
    closePanel,
    toggleViewMode,
    toggleFollowPlayhead,
    zoom,
    scrollTo,
    updateViewportForPlayhead,
  };
}
