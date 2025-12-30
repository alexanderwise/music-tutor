import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format time in MM:SS format */
export function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

/** Scale time based on playback speed
 * All times in analysis.json are at 1.0x speed
 * For 0.5x: time takes twice as long (time / 0.5 = time * 2)
 * For 1.25x: time is shorter (time / 1.25 = time * 0.8)
 */
export function scaleTime(originalTime: number, speed: string): number {
  const speedValue = parseFloat(speed.replace("x", ""));
  return originalTime / speedValue;
}

/** Get the speed multiplier from speed string */
export function getSpeedMultiplier(speed: string): number {
  return parseFloat(speed.replace("x", ""));
}
