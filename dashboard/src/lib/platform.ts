// The app ships as a Windows .exe (also Linux), so the ⌘ symbol is wrong off
// macOS. Use the platform's real modifier name for the ⌘K affordance (IC1).
const isMac = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform);

export const cmdKBadge = isMac ? '⌘K' : 'Ctrl K';
