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

export type ActionInputEntry = [string, WorkflowCallInput];

/**
 * Splits an action's inputs into the ones worth showing up front and the ones
 * that belong behind a disclosure. An action like `actions/checkout` declares
 * a dozen-odd inputs of which one or two matter, so rendering them all buries
 * the useful fields.
 *
 * Visible: required inputs, plus any optional input the user has actually set.
 * A set value is visible even when it equals the action's default - the key is
 * in `with:` either way, so it is going into the YAML.
 *
 * `sticky` holds optional inputs that must stay put even though they are no
 * longer in `with` - it keeps a field from unmounting under the cursor when
 * its value is cleared mid-edit.
 */
export function partitionActionInputs(
  schema: { [inputName: string]: WorkflowCallInput } | undefined,
  withValues: { [key: string]: string } | undefined,
  sticky: ReadonlySet<string>
): { visible: ActionInputEntry[]; hidden: ActionInputEntry[] } {
  const visible: ActionInputEntry[] = [];
  const hidden: ActionInputEntry[] = [];

  for (const entry of Object.entries(schema || {})) {
    const [name, inputDef] = entry;
    const isSet = withValues ? Object.hasOwn(withValues, name) : false;
    if (inputDef.required || isSet || sticky.has(name)) {
      visible.push(entry);
    } else {
      hidden.push(entry);
    }
  }

  return { visible, hidden };
}
