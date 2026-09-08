// These names/bits match both Native and DADG Main_map scene definitions.
export const NATIVE_CAMPAIGN_MASK = -109;
export const CAMPAIGN_REQUIRED_LEVELS = 1 | 2 | 16;
const CAMPAIGN_LEVELS = ['base', 'level_1', 'level_2', 'level_3', 'civilian', 'siege', 'looted'];

export function visibleInLevels(mask: number, required: number): boolean {
  return (mask & required) === required;
}

export function sceneLevelLabel(mask: number, isCampaign: boolean): string {
  if (mask === -1) return '-1 (all levels)';
  const hex = `0x${(mask >>> 0).toString(16).padStart(8, '0')}`;
  if (!isCampaign) return `${mask} (${hex})`;
  const names = CAMPAIGN_LEVELS.filter((_, index) => (mask & (1 << index)) !== 0);
  return `${mask} (${names.join(', ') || 'no defined levels'})`;
}
