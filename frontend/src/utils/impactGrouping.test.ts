import { describe, expect, it } from 'vitest';

import { ROLE_LABEL, roleRank, stripSchemaNote } from './impactGrouping';

describe('stripSchemaNote', () => {
  const note = 'Cột `patient_id` đã là PRIMARY KEY (ngầm NOT NULL) — thêm NOT NULL là no-op.';

  it('removes the schema prefix + separator', () => {
    const risk = `${note} — Rủi ro trung bình: đổi constraint không đổi giá trị.`;
    expect(stripSchemaNote(risk, note)).toBe('Rủi ro trung bình: đổi constraint không đổi giá trị.');
  });

  it('leaves risk untouched when it does not start with the note', () => {
    expect(stripSchemaNote('Rủi ro cao: khoá JOIN.', note)).toBe('Rủi ro cao: khoá JOIN.');
  });

  it('handles null risk and null/undefined note', () => {
    expect(stripSchemaNote(null, note)).toBeNull();
    expect(stripSchemaNote('abc', null)).toBe('abc');
    expect(stripSchemaNote('abc', undefined)).toBe('abc');
  });

  it('does not split on an em-dash that lives inside the note itself', () => {
    // note chứa " — " bên trong; chỉ được cắt ở ranh giới note + " — "
    const risk = `${note} — Phần riêng.`;
    expect(stripSchemaNote(risk, note)).toBe('Phần riêng.');
  });
});

describe('roleRank', () => {
  it('orders output before control kinds', () => {
    expect(roleRank({ dependency_kind: 'output' })).toBeLessThan(roleRank({ dependency_kind: 'join_key' }));
    expect(roleRank({ dependency_kind: 'join_key' })).toBeLessThan(roleRank({ dependency_kind: 'group_key' }));
  });
  it('unknown kind sorts last', () => {
    expect(roleRank({ dependency_kind: 'weird' as never })).toBe(9);
  });
});

describe('ROLE_LABEL', () => {
  it('covers every control dependency_kind', () => {
    for (const k of ['filter', 'join_key', 'group_key', 'window_partition', 'window_order']) {
      expect(ROLE_LABEL[k]).toBeTruthy();
    }
  });
});
