/**
 * UX timing constants — display durations, debounce delays, etc.
 * These are NOT motion tokens; they control how long UI feedback stays visible.
 */

/** Brief feedback flash: copy confirmation, save indicator */
export const FEEDBACK_BRIEF = 1500;

/** Normal feedback display: toast, status message */
export const FEEDBACK_NORMAL = 2000;

/** Delay before closing a dropdown on blur (prevents click-through) */
export const BLUR_CLOSE_DELAY = 150;
