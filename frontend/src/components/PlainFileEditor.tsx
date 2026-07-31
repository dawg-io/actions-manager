/* eslint-disable no-restricted-syntax, no-restricted-imports -- Legacy: TODO migrate inline styles and CSS imports to Tailwind CSS classes */
import React, { useEffect, useRef, useCallback } from 'react';
import { EditorView, basicSetup } from 'codemirror';
import { EditorState, Extension } from '@codemirror/state';
import { yaml } from '@codemirror/lang-yaml';
import { StreamLanguage } from '@codemirror/language';
import { shell } from '@codemirror/legacy-modes/mode/shell';
import { properties } from '@codemirror/legacy-modes/mode/properties';
import { toml } from '@codemirror/legacy-modes/mode/toml';
import { oneDark } from '@codemirror/theme-one-dark';
import { searchKeymap } from '@codemirror/search';
import { indentWithTab } from '@codemirror/commands';
import { keymap } from '@codemirror/view';
import { foldKeymap } from '@codemirror/language';
import '../styles/YAMLEditor.css';

export type PlainFileEditorLanguage = 'yaml' | 'shell' | 'properties' | 'toml' | 'plain';

export interface PlainFileEditorProps {
  value: string;
  onChange?: (value: string) => void;
  language?: PlainFileEditorLanguage;
  readOnly?: boolean;
  height?: string;
  theme?: 'dark' | 'light';
  /** Accessible name for the editor's content element (it has no native label target). */
  ariaLabel?: string;
}

function getLanguageExtension(lang?: PlainFileEditorLanguage): Extension[] {
  switch (lang) {
    case 'yaml':       return [yaml()];
    case 'shell':      return [StreamLanguage.define(shell)];
    case 'properties': return [StreamLanguage.define(properties)];
    case 'toml':       return [StreamLanguage.define(toml)];
    default:           return [];
  }
}

const PlainFileEditor: React.FC<PlainFileEditorProps> = ({
  value,
  onChange,
  language,
  readOnly = false,
  height = '300px',
  theme = 'dark',
  ariaLabel,
}) => {
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const valueRef = useRef<string>(value);
  const isInternalChangeRef = useRef<boolean>(false);
  const isProgrammaticUpdateRef = useRef<boolean>(false);

  useEffect(() => {
    valueRef.current = value;
  }, [value]);

  const handleChange = useCallback((newValue: string) => {
    if (isProgrammaticUpdateRef.current) return;
    if (onChange && newValue !== valueRef.current) {
      valueRef.current = newValue;
      isInternalChangeRef.current = true;
      onChange(newValue);
    }
  }, [onChange]);

  useEffect(() => {
    if (!editorRef.current) return;

    isInternalChangeRef.current = false;

    const extensions: Extension[] = [
      basicSetup,
      ...getLanguageExtension(language),
      EditorView.theme({
        '&': {
          fontSize: '14px',
          fontFamily: 'Consolas, "Courier New", monospace',
          height: '100%',
        },
        '.cm-content': {
          padding: '16px',
          minHeight: height,
        },
        '.cm-focused': { outline: 'none' },
        '.cm-editor': { borderRadius: '8px', height: '100%' },
        '.cm-scroller': { lineHeight: '1.5', height: '100%', overflow: 'auto' },
      }),
      EditorView.updateListener.of(update => {
        if (update.docChanged) handleChange(update.state.doc.toString());
      }),
      EditorState.readOnly.of(readOnly),
      keymap.of([indentWithTab, ...searchKeymap, ...foldKeymap]),
      EditorView.lineWrapping,
      EditorState.tabSize.of(2),
    ];

    if (ariaLabel) {
      extensions.push(EditorView.contentAttributes.of({ 'aria-label': ariaLabel }));
    }

    if (theme === 'dark') extensions.push(oneDark);

    const state = EditorState.create({ doc: value, extensions });
    const view = new EditorView({ state, parent: editorRef.current });
    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [height, readOnly, theme, ariaLabel]); // Intentionally excluding value/onChange/language — see value-sync effect below

  useEffect(() => {
    if (!viewRef.current || value === viewRef.current.state.doc.toString()) return;
    if (isInternalChangeRef.current) {
      isInternalChangeRef.current = false;
      return;
    }
    isProgrammaticUpdateRef.current = true;
    viewRef.current.dispatch({
      changes: { from: 0, to: viewRef.current.state.doc.length, insert: value },
      selection: { anchor: 0, head: 0 },
    });
    isProgrammaticUpdateRef.current = false;
    requestAnimationFrame(() => {
      if (viewRef.current) {
        viewRef.current.scrollDOM.scrollTop = 0;
        viewRef.current.scrollDOM.scrollLeft = 0;
      }
    });
  }, [value]);

  return (
    <div className="yaml-editor-container" style={{ height }} data-testid="plain-file-editor">
      <div ref={editorRef} className="yaml-editor" style={{ height: '100%' }} />
    </div>
  );
};

export default PlainFileEditor;
