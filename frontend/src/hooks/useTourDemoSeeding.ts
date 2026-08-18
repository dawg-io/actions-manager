import { useEffect } from 'react';
import { fetchProjects } from '../api/projects';
import { tour } from '../utils/tour';
import type { ProjectColorKey } from '../utils/projectColors';

export const DEMO_PROJECT_NAME = 'Demo-Project';
export const DEMO_PROJECT_COLOR: ProjectColorKey = 'blue';

/** First `Demo-Project` name not already taken, so the tour cannot dead-end. */
export function pickDemoProjectName(existingNames: (string | undefined)[]): string {
  const taken = new Set(existingNames.map((name) => (name || '').toLowerCase()));
  let suffix = 1;
  let name = DEMO_PROJECT_NAME;
  while (taken.has(name.toLowerCase())) {
    suffix += 1;
    name = `${DEMO_PROJECT_NAME}-${suffix}`;
  }
  return name;
}

interface TourSeedingOptions {
  user: string;
  /** Current guided-tour step, or null when no tour is running. */
  tourStep: string | null;
  setProjectName: (update: (current: string) => string) => void;
  setProjectColor: (color: ProjectColorKey) => void;
  setUsePrefix: (update: (current: boolean | null) => boolean | null) => void;
}

/**
 * Pre-fill the Create Project wizard while the guided tour is running.
 *
 * Lives outside the component both because NewProject is already past the
 * cognitive-complexity budget, and because the ordering rule here is subtle:
 * keyed on `tourStep` rather than `user`, since on a reload at /new the
 * component mounts before user details resolve, and the tour would otherwise
 * promise a pre-filled form over an empty one.
 *
 * Every setter is a functional update that keeps an existing value, so a late
 * run cannot overwrite what the user has since typed.
 */
export function useTourDemoSeeding({
  user,
  tourStep,
  setProjectName,
  setProjectColor,
  setUsePrefix,
}: TourSeedingOptions): void {
  useEffect(() => {
    if (!tourStep || !user) return;
    let cancelled = false;

    const seed = async (): Promise<void> => {
      const existing = await fetchProjects(user);
      if (cancelled) return;
      const name = pickDemoProjectName(existing.map((p) => p.project_name));
      setProjectName((current) => current || name);
      setProjectColor(DEMO_PROJECT_COLOR);
      setUsePrefix((current) => current ?? true);
      tour.demoProjectName = name;
    };

    void seed();
    return () => {
      cancelled = true;
    };
    // Setters come from useState and are stable, so the tour identity is the
    // only thing that should retrigger this.
  }, [user, tourStep]);
}
