/**
 * Completion signals for the guided onboarding tour.
 *
 * The tour is mounted once at the App root, but the actions it waits for
 * happen deep inside NewProject and ProjectMgmt. Rather than thread a context
 * through those (ProjectMgmt alone is ~2,700 lines), product code fires a
 * one-line signal at the success site it already has, exactly the way
 * `utils/toast.ts` lets any component reach the root ToastContainer.
 *
 * Signals report what the user really did. The tour never performs a step for
 * them — each one is a real action against their own GitHub account.
 */

import { readStoredPreference, writeStoredPreference } from './projectFilesPanelPrefs';

export type TourStepId =
  | 'open-wizard'
  | 'project-basics'
  | 'pick-repos'
  | 'naming-mode'
  | 'add-workflow'
  | 'choose-workflow-type'
  | 'start-workflow'
  | 'commit-workflow'
  | 'create-campaign'
  | 'confirm-campaign'
  | 'open-campaigns'
  | 'resolve-pr'
  | 'finished';


type Listener = (stepId: TourStepId) => void;

const DEMO_PROJECT_KEY = 'onboarding.demoProject';

export class TourSignals {
  private readonly listeners: Set<Listener> = new Set();
  private readonly restartListeners: Set<() => void> = new Set();

  /**
   * The step currently on screen, or null when no tour is running.
   *
   * Published here rather than passed down so a screen can ask "is a tour
   * running?" without being wired to the tour. NewProject uses it to decide
   * whether to seed demo values; a URL parameter would race its own mount.
   */
  activeStep: TourStepId | null = null;

  /**
   * Name of the project the tour created, so a user who navigates back to the
   * dashboard mid-tour can be pointed at it and sent back in.
   *
   * Mirrored to localStorage because it must survive a reload, and kept out of
   * the database because it is throwaway UI state — losing it only degrades
   * the callout to a generic message.
   */
  get demoProjectName(): string | null {
    return readStoredPreference(DEMO_PROJECT_KEY) || null;
  }

  set demoProjectName(name: string | null) {
    writeStoredPreference(DEMO_PROJECT_KEY, name ?? '');
  }

  isActive(): boolean {
    return this.activeStep !== null;
  }

  /**
   * Ask for onboarding to start over.
   *
   * Routed through here for the same reason completions are: the control that
   * offers it lives in the user menu, several components below the App state
   * that owns onboarding, and threading a callback down would touch every
   * screen that renders an avatar.
   */
  onRestartRequested(fn: () => void): () => void {
    this.restartListeners.add(fn);
    return () => {
      this.restartListeners.delete(fn);
    };
  }

  requestRestart(): void {
    // The recorded project belongs to the run that just ended.
    this.demoProjectName = null;
    this.restartListeners.forEach((fn) => fn());
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  }

  /**
   * Report that the user completed a step. Safe to call whether or not a tour
   * is running — with no listeners it does nothing, so call sites never need
   * to know about tour state.
   */
  completed(stepId: TourStepId): void {
    this.listeners.forEach((fn) => fn(stepId));
  }
}

export const tour = new TourSignals();
