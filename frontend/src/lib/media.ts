/** Frames extracted from the scenario videos (see DESIGN.md, media pipeline). Keyed by scenario id.
 *  Real footage only; used as posters and thumbnails, never as evidence on their own. */
export const SCENARIO_FRAMES: Record<string, string> = {
  scn1_clean: "/media/scn1_clean_f2.webp",
  scn2_short: "/media/scn2_short_f2.webp",
  scn3_damage: "/media/scn3_damage_f1.webp",
  scn4_mixed: "/media/scn4_mixed_f2.webp",
};

export const frameFor = (scenario: string | null | undefined): string | undefined => (scenario ? SCENARIO_FRAMES[scenario] : undefined);
