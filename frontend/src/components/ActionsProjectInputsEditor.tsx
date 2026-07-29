import React from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Checkbox } from "./ui/checkbox";
import type { ActionInput } from "../api/actionsProjects";

interface ActionsProjectInputsEditorProps {
  readonly inputs: ActionInput[];
  readonly onChange: (inputs: ActionInput[]) => void;
}

const INPUT_TYPES: { value: ActionInput["type"]; label: string }[] = [
  { value: "string", label: "String" },
  { value: "number", label: "Number" },
  { value: "boolean", label: "Boolean" },
  { value: "choice", label: "Choice" },
];

// Matches components/ui/input.tsx's styling so the native <select>/<textarea>
// below look consistent with the rest of the form - no shadcn Select exists
// in this repo yet, so plain elements are the established pattern here
// (StepCard.tsx's TypedWithInput does the same for typed `with:` fields).
const FIELD_CLASSNAME =
  "flex h-9 w-full rounded-md border px-3 py-1 text-sm shadow-sm transition-colors " +
  "border-input-border bg-input-background-color text-text-primary placeholder:text-text-muted " +
  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-input-focus " +
  "dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:placeholder:text-gray-400";

function updateAt(inputs: ActionInput[], index: number, patch: Partial<ActionInput>): ActionInput[] {
  return inputs.map((input, i) => (i === index ? { ...input, ...patch } : input));
}

function DefaultValueField({
  input,
  index,
  onChange,
  inputs,
}: {
  readonly input: ActionInput;
  readonly index: number;
  readonly inputs: ActionInput[];
  readonly onChange: (inputs: ActionInput[]) => void;
}): React.ReactElement {
  const fieldId = `input-default-${index}`;
  const setDefault = (value: string | null): void => onChange(updateAt(inputs, index, { default: value }));

  if (input.type === "boolean") {
    return (
      <div className="flex items-center gap-2 pt-6">
        <Checkbox
          id={fieldId}
          checked={input.default === "true"}
          onCheckedChange={(checked) => setDefault(checked === true ? "true" : "false")}
        />
        <Label htmlFor={fieldId}>Default: true</Label>
      </div>
    );
  }

  if (input.type === "choice") {
    return (
      <select
        id={fieldId}
        value={input.default ?? ""}
        onChange={(e) => setDefault(e.target.value || null)}
        className={FIELD_CLASSNAME}
      >
        <option value="">Not set</option>
        {(input.options ?? []).map((opt) => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    );
  }

  return (
    <Input
      id={fieldId}
      type={input.type === "number" ? "number" : "text"}
      value={input.default ?? ""}
      onChange={(e) => setDefault(e.target.value || null)}
    />
  );
}

export default function ActionsProjectInputsEditor({
  inputs,
  onChange,
}: ActionsProjectInputsEditorProps): React.ReactElement {
  const [inputKeys, setInputKeys] = React.useState<string[]>(
    () => inputs.map(() => crypto.randomUUID())
  );

  React.useEffect(() => {
    setInputKeys((prev) => {
      if (prev.length === inputs.length) return prev;
      if (inputs.length > prev.length) {
        return [...prev, ...Array.from({ length: inputs.length - prev.length }, () => crypto.randomUUID())];
      }
      return prev.slice(0, inputs.length);
    });
  }, [inputs.length]);

  const addInput = (): void => {
    setInputKeys((prev) => [...prev, crypto.randomUUID()]);
    onChange([...inputs, { name: "", description: null, required: false, default: null, type: "string", options: null }]);
  };

  const removeInput = (index: number): void => {
    setInputKeys((prev) => prev.filter((_, i) => i !== index));
    onChange(inputs.filter((_, i) => i !== index));
  };

  const setType = (index: number, type: ActionInput["type"]): void => {
    onChange(updateAt(inputs, index, {
      type,
      // Clear options and any now-mismatched default when leaving choice.
      ...(type !== "choice" ? { options: null } : {}),
      ...(type !== inputs[index].type ? { default: null } : {}),
    }));
  };

  return (
    <div className="flex flex-col gap-3" data-testid="actions-project-inputs-editor">
      {inputs.length === 0 && (
        <p className="text-sm text-text-muted dark:text-text-muted-dark">
          No inputs defined. Add one below if this action needs configurable values.
        </p>
      )}
      {inputs.map((input, index) => (
        <div
          key={inputKeys[index]}
          data-testid={`actions-input-row-${index}`}
          className="flex flex-col gap-2 rounded-lg border border-border p-3 dark:border-border-dark"
        >
          <div className="flex items-start gap-2">
            <div className="grid flex-1 gap-2 sm:grid-cols-2">
              <div>
                <Label htmlFor={`input-name-${index}`}>Name</Label>
                <Input
                  id={`input-name-${index}`}
                  value={input.name}
                  onChange={(e) => onChange(updateAt(inputs, index, { name: e.target.value }))}
                />
              </div>
              <div>
                <Label htmlFor={`input-type-${index}`}>Type</Label>
                <select
                  id={`input-type-${index}`}
                  value={input.type}
                  onChange={(e) => setType(index, e.target.value as ActionInput["type"])}
                  className={FIELD_CLASSNAME}
                >
                  {INPUT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              {input.type === "choice" && (
                <div className="sm:col-span-2">
                  <Label htmlFor={`input-options-${index}`}>Options (one per line)</Label>
                  <textarea
                    id={`input-options-${index}`}
                    value={(input.options ?? []).join("\n")}
                    onChange={(e) => onChange(updateAt(inputs, index, {
                      options: e.target.value.split("\n").filter((opt) => opt.trim()),
                    }))}
                    placeholder={"option1\noption2\noption3"}
                    rows={3}
                    className={FIELD_CLASSNAME}
                  />
                </div>
              )}
              <div>
                <Label htmlFor={`input-default-${index}`}>Default</Label>
                <DefaultValueField input={input} index={index} inputs={inputs} onChange={onChange} />
              </div>
              <div className="sm:col-span-2">
                <Label htmlFor={`input-description-${index}`}>Description</Label>
                <Input
                  id={`input-description-${index}`}
                  value={input.description ?? ""}
                  onChange={(e) => onChange(updateAt(inputs, index, { description: e.target.value || null }))}
                />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id={`input-required-${index}`}
                  checked={input.required}
                  onCheckedChange={(checked) => onChange(updateAt(inputs, index, { required: checked === true }))}
                />
                <Label htmlFor={`input-required-${index}`}>Required</Label>
              </div>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Remove input ${input.name || index + 1}`}
              onClick={() => removeInput(index)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      ))}
      <Button type="button" variant="outline" onClick={addInput} className="self-start">
        <Plus className="h-4 w-4" /> Add input
      </Button>
    </div>
  );
}
