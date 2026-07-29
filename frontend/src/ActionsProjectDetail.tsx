import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";
import ActionsProjectInputsEditor from "./components/ActionsProjectInputsEditor";
import {
  ActionInput,
  ActionsProject,
  getActionsProject,
  updateActionsProject,
  deleteActionsProject,
} from "./api/actionsProjects";
import { toast } from "./utils/toast";

interface ActionsProjectDetailProps {
  readonly user: string;
  readonly actionsProjectId: number;
}

export default function ActionsProjectDetail({
  user,
  actionsProjectId,
}: ActionsProjectDetailProps): React.ReactElement {
  const navigate = useNavigate();
  const [project, setProject] = useState<ActionsProject | null>(null);
  const [name, setName] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [inputs, setInputs] = useState<ActionInput[]>([]);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    getActionsProject(user, actionsProjectId)
      .then((data) => {
        if (cancelled) return;
        setProject(data);
        setName(data.name);
        setDescription(data.description ?? "");
        setInputs(data.inputs);
      })
      .catch((err) => {
        if (!cancelled) toast.error(err instanceof Error ? err.message : "Failed to load Managed Action");
      });
    return () => {
      cancelled = true;
    };
  }, [user, actionsProjectId]);

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    try {
      const updated = await updateActionsProject(user, actionsProjectId, name.trim(), description.trim() || null, inputs);
      setProject(updated);
      toast.success("Managed Action updated");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update Managed Action");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (): Promise<void> => {
    setIsDeleting(true);
    try {
      await deleteActionsProject(user, actionsProjectId);
      toast.success("Managed Action deleted");
      navigate(`/project/${user}/actions-projects`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete Managed Action");
      setIsDeleting(false);
    }
  };

  if (!project) {
    return <div className="w-full max-w-3xl mx-auto px-6 lg:px-8" data-testid="actions-project-detail-loading" />;
  }

  return (
    <div className="w-full max-w-3xl mx-auto px-6 lg:px-8" data-testid="actions-project-detail">
      <div className="mb-6">
        <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">
          {project.owner}/{project.repo} · {project.yaml_path}
        </p>
        <h2 className="text-3xl font-bold text-gray-900 dark:text-white">{project.name}</h2>
      </div>

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
          <Button
            type="button"
            variant="destructive"
            onClick={handleDelete}
            disabled={isDeleting || isSaving}
            data-testid="delete-actions-project-button"
          >
            {isDeleting ? "Deleting..." : "Delete"}
          </Button>
          <Button
            type="button"
            onClick={handleSave}
            disabled={!name.trim() || isSaving || isDeleting}
            data-testid="save-actions-project-detail-button"
          >
            {isSaving ? "Saving..." : "Save"}
          </Button>
        </div>
      </div>
    </div>
  );
}
