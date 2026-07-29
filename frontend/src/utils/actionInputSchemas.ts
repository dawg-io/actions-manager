import { WorkflowCallInput } from './workflowGuiConversion';
import { ActionsProject } from '../api/actionsProjects';

/**
 * Converts an imported ActionsProject's inputs into the WorkflowCallInput
 * shape StepCard renders typed `with:` fields from. Inputs default to
 * `type: 'string'` at import time (action.yml itself never declares one),
 * but a user can upgrade a specific input's type via the editor (#1693) -
 * whatever type is stored is passed straight through here.
 */
export function actionsProjectToSchema(project: ActionsProject): { [inputName: string]: WorkflowCallInput } {
  const schema: { [inputName: string]: WorkflowCallInput } = {};
  for (const input of project.inputs) {
    schema[input.name] = {
      type: input.type,
      description: input.description ?? undefined,
      required: input.required,
      default: input.default ?? undefined,
      options: input.options ?? undefined,
    };
  }
  return schema;
}

/**
 * Strips the `@version` pin off a `uses:` string and looks up a matching
 * imported Actions Project by `owner/repo` slug, converting its inputs to
 * the typed schema StepCard needs. Returns undefined if nothing matches.
 */
export function getActionInputSchema(
  uses: string,
  importedActions: ActionsProject[]
): { [inputName: string]: WorkflowCallInput } | undefined {
  const slug = uses.split('@')[0];
  const match = importedActions.find((project) => `${project.owner}/${project.repo}` === slug);
  return match ? actionsProjectToSchema(match) : undefined;
}
