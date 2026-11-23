// Inline stroke icons (no emoji, no icon font). Decorative: hidden from screen readers.
const base = { fill: 'none', stroke: 'currentColor', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true }

export const Plus = ({ s = 18 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="2" {...base}><path d="M12 5v14M5 12h14" /></svg>
export const ArrowUp = ({ s = 18 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="2.2" {...base}><path d="M12 19V5" /><path d="M5 12l7-7 7 7" /></svg>
export const Sliders = ({ s = 16 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="1.8" {...base}><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></svg>
export const StopSq = ({ s = 11 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="currentColor" aria-hidden><rect x="4" y="4" width="16" height="16" rx="3" /></svg>
export const FileIc = ({ s = 15 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="1.8" {...base}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>
export const Folder = ({ s = 15 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="1.8" {...base}><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
export const Moon = ({ s = 16 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="1.8" {...base}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
export const Sun = ({ s = 16 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="1.8" {...base}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
export const Menu = ({ s = 20 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="1.8" {...base}><path d="M4 7h16M4 12h16M4 17h10" /></svg>
export const Back = ({ s = 18 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="2" {...base}><path d="M15 18l-6-6 6-6" /></svg>
export const Search = ({ s = 16 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="1.8" {...base}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
export const More = ({ s = 18 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="currentColor" aria-hidden><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /></svg>
export const Team = ({ s = 18 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="1.8" {...base}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6" /></svg>
export const Book = ({ s = 15 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="1.8" {...base}><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" /><path d="M4 21V5M9 7h6" /></svg>
export const Close = ({ s = 18 }) => <svg width={s} height={s} viewBox="0 0 24 24" strokeWidth="2" {...base}><path d="M6 6l12 12M18 6L6 18" /></svg>
