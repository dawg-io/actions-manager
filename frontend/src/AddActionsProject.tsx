import React, { useState } from "react";
import { useNavigate } from "react-router";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";
import ActionsProjectInputsEditor from "./components/ActionsProjectInputsEditor";
import { previewActionsProject, createActionsProject, ActionInput, PreviewResponse } from "./api/actionsProjects";
import { toast } from "./utils/toast";

interface AddActionsProjectProps {
  readonly user: string;
}

type WizardStep = 1 | 2;

export default function AddActionsProject({ user }: AddActionsProjectProps): React.ReactElement {
  const navigate = useNavigate();
  const [step, setStep] = useState<WizardStep>(1);
  const [url, setUrl] = useState<string>("");
  const [isPreviewing, setIsPreviewing] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [name, setName] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [inputs, setInputs] = useState<ActionInput[]>([]);

  const handlePreview = async (): Promise<void> => {
    setIsPreviewing(true);
    try {
      const result = await previewActionsProject(user, url.trim());
      setPreview(result);
      setName(result.name);
      setDescription(result.description ?? "");
      setInputs(result.inputs);
      setStep(2);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to fetch action metadata");
    } finally {
      setIsPreviewing(false);
    }
  };

  const handleSave = async (): Promise<void> => {
    if (!preview) return;
    setIsSaving(true);
    try {
      await createActionsProject(user, preview, name.trim(), description.trim() || null, inputs);
      toast.success("Managed Action saved");
      navigate(`/project/${user}/actions-projects`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save Managed Action");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="w-full max-w-3xl mx-auto px-6 lg:px-8" data-testid="add-actions-project">
      <div className="mb-6">
        <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">
          Add Managed Action
        </p>
        <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
          {step === 1 ? "Paste a repo, action file, or Marketplace URL" : "Review defaults"}
        </h2>
      </div>

      {step === 1 && (
        <div className="flex flex-col gap-4">
          <div>
            <Label htmlFor="actions-yaml-url">GitHub URL</Label>
            <Input
              id="actions-yaml-url"
              placeholder="https://github.com/owner/repo"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-slate-400">
              Paste a repo URL, a GitHub Marketplace action URL, or (if the action's metadata
              file isn't at the repo root) the direct file URL, e.g. .../blob/main/path/action.yml.
            </p>
          </div>
          <Button
            type="button"
            onClick={handlePreview}
            disabled={!url.trim() || isPreviewing}
            className="self-start"
            data-testid="fetch-preview-button"
          >
            {isPreviewing ? "Fetching..." : "Fetch"}
          </Button>
        </div>
      )}

      {step === 2 && preview && (
        <div className="flex flex-col gap-5">
          <div>
            <Label htmlFor="actions-project-name">Name</Label>
            <Input id="actions-project-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="actions-project-description">Description</Label>
            <Input
              id="actions-project-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div>
            <Label>Inputs</Label>
            <ActionsProjectInputsEditor inputs={inputs} onChange={setInputs} />
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-between">
            <Button type="button" variant="outline" onClick={() => setStep(1)} disabled={isSaving}>
              Back
            </Button>
            <Button
              type="button"
              onClick={handleSave}
              disabled={!name.trim() || isSaving}
              data-testid="save-actions-project-button"
            >
              {isSaving ? "Saving..." : "Save"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
