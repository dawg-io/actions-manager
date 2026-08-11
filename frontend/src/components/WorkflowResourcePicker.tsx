import React, { useMemo, useState } from 'react';
import { KeyRound, Search } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Input } from './ui/input';
import { useWorkflowResources } from './WorkflowResourcesContext';
import {
  WorkflowResource,
  WorkflowResourceKind,
  buildResourceExpression,
  groupResourceScopes,
} from '../utils/workflowResources';

type ScopedResource = WorkflowResource & { repos: string[] };

const GROUPS: Array<{ kind: WorkflowResourceKind; label: string; slug: string }> = [
  { kind: 'secret', label: 'Secrets', slug: 'secrets' },
  { kind: 'variable', label: 'Variables', slug: 'variables' },
  { kind: 'environment', label: 'Environments', slug: 'environments' },
];

interface ResourceGroupProps {
  label: string;
  slug: string;
  resources: ScopedResource[];
  onSelect: (resource: ScopedResource) => void;
}

const ResourceGroup: React.FC<ResourceGroupProps> = ({ label, slug, resources, onSelect }) => {
  if (resources.length === 0) return null;

  return (
    <div className="mb-3" data-testid={`resource-group-${slug}`}>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-text-muted dark:text-text-muted-dark">
        {label} ({resources.length})
      </h4>
      <ul className="divide-y divide-border rounded-md border border-border dark:divide-border-dark dark:border-border-dark">
        {resources.map((resource) => (
          <li key={`${resource.kind}:${resource.name}`}>
            <button
              type="button"
              onClick={() => onSelect(resource)}
              data-testid={`resource-item-${resource.name}`}
              title={buildResourceExpression(resource)}
              className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-hover-bg dark:hover:bg-hover-dark-bg"
            >
              <span className="font-mono text-text-primary dark:text-text-primary-dark">
                {resource.name}
              </span>
              {resource.repos.length > 0 && (
                <span className="shrink-0 text-xs text-text-muted dark:text-text-muted-dark">
                  {resource.repos.join(', ')}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
};

interface WorkflowResourcePickerProps {
  /** Receives the ready-to-paste GitHub Actions expression. */
  onInsert: (text: string) => void;
  variant?: 'toolbar' | 'field';
  disabled?: boolean;
}

/**
 * Lets the user insert a reference to an existing project secret, variable or
 * deployment environment without retyping its name.
 *
 * Only names and their repository scope are ever rendered - values are stripped
 * upstream in `toResources`, so no secret or variable value reaches this tree.
 */
const WorkflowResourcePicker: React.FC<WorkflowResourcePickerProps> = ({
  onInsert,
  variant = 'toolbar',
  disabled = false,
}) => {
  const { resources, loadingEnvironments, environmentsError, requestEnvironments } =
    useWorkflowResources();
  const [open, setOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  // `environment: NAME` is a job-level key, so it is only insertable into the
  // YAML document. Inside a run script or a `with:` value it would be pasted in
  // as literal text, which is never valid there - the same reason the editor's
  // inline completions exclude environments.
  const insertable = useMemo(
    () => (variant === 'field' ? resources.filter((r) => r.kind !== 'environment') : resources),
    [resources, variant]
  );

  const scoped = useMemo(() => groupResourceScopes(insertable), [insertable]);
  const filtered = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return scoped;
    return scoped.filter((resource) => resource.name.toLowerCase().includes(term));
  }, [scoped, searchTerm]);

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (next) {
      setSearchTerm('');
      requestEnvironments();
    }
  };

  const handleSelect = (resource: ScopedResource) => {
    onInsert(buildResourceExpression(resource));
    setOpen(false);
  };

  const triggerClass =
    variant === 'toolbar'
      ? 'inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-text-secondary hover:bg-hover-bg disabled:opacity-50 dark:border-border-dark dark:text-text-secondary-dark dark:hover:bg-hover-dark-bg'
      : 'inline-flex shrink-0 items-center rounded-md border border-border p-1 text-text-secondary hover:bg-hover-bg disabled:opacity-50 dark:border-border-dark dark:text-text-secondary-dark dark:hover:bg-hover-dark-bg';

  return (
    <>
      <button
        type="button"
        onClick={() => handleOpenChange(true)}
        disabled={disabled}
        data-testid="resource-picker-trigger"
        aria-label="Insert project resource"
        title="Insert a project secret, variable or environment at the cursor"
        className={triggerClass}
      >
        <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
        {variant === 'toolbar' && <span>Insert Resource</span>}
      </button>

      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent
          className="max-w-lg"
          data-testid="resource-picker"
          // The caller refocuses the editor or field it just inserted into;
          // letting Radix pull focus back to the trigger would undo that.
          onCloseAutoFocus={(event) => event.preventDefault()}
        >
          <DialogHeader>
            <DialogTitle>Insert Project Resource</DialogTitle>
            <DialogDescription>
              Inserts a reference at the cursor. Secret values are never shown or used - only names.
            </DialogDescription>
          </DialogHeader>

          <div className="relative">
            <Search
              className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
              aria-hidden="true"
            />
            <Input
              type="search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search resources…"
              aria-label="Search project resources"
              data-testid="resource-picker-search"
              className="pl-8"
            />
          </div>

          {environmentsError && (
            <div
              role="alert"
              data-testid="resource-picker-error"
              className="rounded-md border border-danger px-3 py-2 text-sm text-danger"
            >
              {environmentsError}
            </div>
          )}

          <div className="max-h-80 overflow-y-auto">
            {GROUPS.map((group) => (
              <ResourceGroup
                key={group.kind}
                label={group.label}
                slug={group.slug}
                resources={filtered.filter((resource) => resource.kind === group.kind)}
                onSelect={handleSelect}
              />
            ))}

            {loadingEnvironments && (
              <p
                data-testid="resource-picker-loading"
                className="py-2 text-center text-sm text-text-muted dark:text-text-muted-dark"
              >
                Loading deployment environments…
              </p>
            )}

            {scoped.length === 0 && !loadingEnvironments && (
              <div
                data-testid="resource-picker-empty"
                className="rounded-md border border-dashed border-border px-3 py-6 text-center dark:border-border-dark"
              >
                <p className="text-sm font-medium text-text-primary dark:text-text-primary-dark">
                  No secrets or variables yet
                </p>
                <p className="mt-1 text-xs text-text-muted dark:text-text-muted-dark">
                  Add them under Repository Configs, then reopen this picker.
                </p>
              </div>
            )}

            {scoped.length > 0 && filtered.length === 0 && (
              <p
                data-testid="resource-picker-no-match"
                className="py-6 text-center text-sm text-text-muted dark:text-text-muted-dark"
              >
                No resources match &quot;{searchTerm}&quot;
              </p>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default WorkflowResourcePicker;
