import { describe, expect, test } from "vitest";

import { projectKeyFixedNote } from "./prefixModeConfig";

/**
 * The project key is generated at creation and never changes. After a rename
 * the display name and the key no longer match, which reads as a bug, so this
 * sentence explains it wherever a project is renamed.
 *
 * It has to be accurate in both naming modes, because they put the key in
 * different places: Prefix Mode stamps it onto secrets, variables and delivered
 * workflow filenames, while No Prefix Mode puts it on none of them — there, the
 * only place it appears is the pull-request branch name.
 */
describe("projectKeyFixedNote", () => {
  test("says the rename does not change the key, in both modes", () => {
    for (const usePrefix of [true, false]) {
      expect(projectKeyFixedNote(usePrefix, "ACME")).toContain(
        "does not change the project key",
      );
    }
  });

  test("prefix mode names the resources that keep the prefix", () => {
    const note = projectKeyFixedNote(true, "acme");
    expect(note).toContain("AM_ACME_");
    expect(note).toContain("secrets");
    expect(note).toContain("variables");
    expect(note).toContain("workflow files");
  });

  test("no-prefix mode does not claim resources carry the prefix", () => {
    const note = projectKeyFixedNote(false, "ACME");
    // In this mode nothing in GitHub carries the key except the branch name,
    // so promising that secrets or workflow files "keep their prefix" would be
    // false.
    expect(note).not.toContain("AM_ACME_");
    expect(note).toContain("without the key prefix");
    expect(note).toContain("branch names");
  });

  test("never mentions deployment environments, which are never prefixed", () => {
    // Deployment environments are used verbatim in both modes — a prefix there
    // would break every workflow `environment:` key and branch-protection rule
    // naming it. Claiming otherwise in the UI would be wrong.
    for (const usePrefix of [true, false]) {
      expect(projectKeyFixedNote(usePrefix, "ACME").toLowerCase()).not.toContain(
        "environment",
      );
    }
  });

  test("falls back to a generic prefix when no code is supplied", () => {
    expect(projectKeyFixedNote(true)).toContain("AM_PROJECT_CODE_");
  });
});
