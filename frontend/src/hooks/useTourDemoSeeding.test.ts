import { pickDemoProjectName, DEMO_PROJECT_NAME } from './useTourDemoSeeding';

describe('pickDemoProjectName', () => {
  test('uses the plain name when nothing is taken', () => {
    expect(pickDemoProjectName([])).toBe(DEMO_PROJECT_NAME);
  });

  test('skips past names already in use, so the tour cannot dead-end', () => {
    // A duplicate name is rejected on create, which would strand the user on
    // the step that promised the form was filled in for them.
    expect(pickDemoProjectName(['Demo-Project'])).toBe('Demo-Project-2');
    expect(pickDemoProjectName(['Demo-Project', 'Demo-Project-2'])).toBe('Demo-Project-3');
  });

  test('matches case-insensitively, as the backend does', () => {
    expect(pickDemoProjectName(['demo-project'])).toBe('Demo-Project-2');
  });

  test('tolerates missing names in the project list', () => {
    expect(pickDemoProjectName([undefined, ''])).toBe(DEMO_PROJECT_NAME);
  });
});
