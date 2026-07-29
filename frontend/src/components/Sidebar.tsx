/* eslint-disable no-restricted-syntax, no-restricted-imports -- Legacy: TODO migrate inline styles and CSS imports to Tailwind CSS classes */
import React, { useState, useEffect } from 'react';
import {
  GitPullRequest,
  FolderGit2,
  Rocket,
  Variable,
  KeyRound,
  ShieldCheck,
  Users,
  Settings,
  Info,
  Link2,
  AlertTriangle,
  Download,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  LucideIcon,
} from 'lucide-react';
import BrandLogo from './BrandLogo';
import EditableNameField from './EditableNameField';
import { getPrefixModeConfig } from '../utils/prefixModeConfig';
import { getProjectTypeConfig } from '../utils/projectTypeConfig';
import ProjectTypeBadge from './ProjectTypeBadge';
import PrefixModeBadge from './PrefixModeBadge';
import RepositoryVisibilityBadge from './RepositoryVisibilityBadge';
import ReadOnlyBadge from './ReadOnlyBadge';
import '../styles/Sidebar.css';

interface NavSection {
  key: string;
  label: string;
  Icon: LucideIcon;
}

interface SidebarProps {
  activeSection?: string;
  onSectionChange?: (section: string) => void;
  projectName?: string;
  onProjectNameSave?: (newValue: string) => void;
  projectCode?: string;
  projectType?: 'standard' | 'rwx';
  /** Saved backend `repository_visibility_scope` for the current project. */
  repositoryVisibilityScope?: 'public' | 'private';
  usePrefix?: boolean;
  isReadOnly?: boolean;
  onLinkReusableWorkflow?: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  isMobileOpen?: boolean;
  onMobileClose?: () => void;
}

const repoConfigSections: NavSection[] = [
  { key: 'repos-and-branches', label: 'Repositories & Branches', Icon: FolderGit2 },
  { key: 'environments', label: 'Deploy Environments', Icon: Rocket },
  { key: 'envvars', label: 'Environment Variables', Icon: Variable },
  { key: 'secrets', label: 'Environment Secrets', Icon: KeyRound },
  { key: 'rulesets', label: 'Environment Rulesets', Icon: ShieldCheck },
];

const standardProjectConfigSections: NavSection[] = [
  { key: 'project-info', label: 'Project Info', Icon: Info },
  { key: 'project-members', label: 'Project Members', Icon: Users },
  { key: 'backup-export', label: 'Backup & Export', Icon: Download },
  { key: 'danger-zone', label: 'Danger Zone', Icon: AlertTriangle },
];
const rwxProjectConfigSections: NavSection[] = [
  { key: 'project-info', label: 'Project Info', Icon: Info },
  { key: 'project-members', label: 'Project Members', Icon: Users },
  { key: 'linked-projects', label: 'Linked Projects', Icon: Link2 },
  { key: 'backup-export', label: 'Backup & Export', Icon: Download },
  { key: 'danger-zone', label: 'Danger Zone', Icon: AlertTriangle },
];
const allProjectConfigKeys = [
  ...standardProjectConfigSections.map(s => s.key),
  ...rwxProjectConfigSections.map(s => s.key),
];

const Sidebar: React.FC<SidebarProps> = ({ 
  activeSection, 
  onSectionChange, 
  projectName,
  projectCode,
  projectType = 'standard',
  repositoryVisibilityScope,
  usePrefix,
  isReadOnly,
  onLinkReusableWorkflow,
  isCollapsed,
  onToggleCollapse,
  onProjectNameSave,
  isMobileOpen,
  onMobileClose,
}) => {
  const [projectConfigOpen, setProjectConfigOpen] = useState<boolean>(
    allProjectConfigKeys.includes(activeSection || '')
  );

  // Auto-expand the group when the active section changes to a project-config child
  useEffect(() => {
    if (allProjectConfigKeys.includes(activeSection || '')) {
      setProjectConfigOpen(true);
    }
  }, [activeSection]);

  const toggleSidebar = () => {
    if (onToggleCollapse) {
      onToggleCollapse();
    }
  };

  const handleProjectConfigToggle = () => {
    // Only toggle when sidebar is expanded; collapsing is purely visual
    if (!isCollapsed) {
      setProjectConfigOpen(prev => !prev);
    }
  };

  const handleSectionChange = (key: string) => {
    if (onSectionChange) onSectionChange(key);
    if (onMobileClose) onMobileClose();
  };

  const isProjectConfigActive = allProjectConfigKeys.includes(activeSection || '');

  // Determine which project-config sections to display based on project type
  const currentProjectConfigSections = projectType === 'rwx' ? rwxProjectConfigSections : standardProjectConfigSections;

  return (
    <div className={`sidebar ${isCollapsed ? 'collapsed' : 'expanded'}${isMobileOpen ? ' mobile-open' : ''}`}>
      <div className="sidebar-header">
        <div className="sidebar-title-row">
          <div className="sidebar-title">
            {isCollapsed ? (
              <BrandLogo variant="icon" size="sm" />
            ) : (
              <BrandLogo variant="full" size="md" />
            )}
          </div>
          <button
            className="sidebar-collapse-button"
            onClick={toggleSidebar}
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? (
              <ChevronRight className="sidebar-collapse-icon" />
            ) : (
              <ChevronLeft className="sidebar-collapse-icon" />
            )}
          </button>
        </div>
        {(projectName || projectCode) && !isCollapsed && (
          <div className="sidebar-project">
            <span className="sidebar-project-label">Project</span>
            {projectName && onProjectNameSave ? (
              <EditableNameField
                value={projectName}
                onSave={onProjectNameSave}
                validate={(v) => (v.trim().length === 0 ? 'Project name cannot be empty.' : null)}
                ariaLabel="project name"
                inputId="sidebar-project-name"
                placeholder="Enter project name"
                disabled={isReadOnly}
                className="sidebar-project-name-editable"
                displayClassName="sidebar-project-name-display"
                editButtonClassName="sidebar-project-name-edit-button"
                inputClassName="sidebar-project-name-input"
              />
            ) : (
              projectName && (
                <span className="sidebar-project-name" title={projectName}>
                  {projectName}
                </span>
              )
            )}
            {projectCode && <span className="sidebar-project-key">Project Key: {projectCode}</span>}
            <div className="sidebar-project-badges">
              <ProjectTypeBadge projectType={projectType} size="sm" />
              {repositoryVisibilityScope && (
                <RepositoryVisibilityBadge visibilityScope={repositoryVisibilityScope} size="sm" data-testid="sidebar-project-visibility-badge" />
              )}
              {usePrefix !== undefined && (
                <PrefixModeBadge usePrefix={usePrefix} size="sm" />
              )}
              {isReadOnly && <ReadOnlyBadge size="sm" />}
            </div>
          </div>
        )}
        {projectCode && isCollapsed && (
          <div className="sidebar-project-collapsed" title={`Project Key: ${projectCode} · ${getProjectTypeConfig(projectType).label}${repositoryVisibilityScope ? ` · ${repositoryVisibilityScope === 'private' ? 'Private Repos' : 'Public Repos'}` : ''}${usePrefix !== undefined ? ` · ${getPrefixModeConfig(usePrefix).shortLabel} Mode` : ''}${isReadOnly ? ' · 🔒 Read Only' : ''}`}>
            <span className="sidebar-project-code">{projectCode}</span>
          </div>
        )}
      </div>
      
      <nav className="sidebar-nav">
        {/* Top section: primary navigation */}
        <div className="space-y-1">
          {/* FILES Section Label */}
          {!isCollapsed && <div className="sidebar-section-label">Files</div>}

          {/* Project Files – unified workspace: workflows, custom files, CODEOWNERS */}
          <button
            className={`sidebar-item ${activeSection === 'workflows' || activeSection === 'custom-files' || activeSection === 'codeowners' ? 'active' : ''}`}
            aria-label="Project Files"
            onClick={() => handleSectionChange('workflows')}
            title={isCollapsed ? 'Project Files' : ''}
          >
            <span className="sidebar-icon" aria-hidden="true"><FileText size={18} strokeWidth={1.75} /></span>
            {!isCollapsed && <span className="sidebar-label">Project Files</span>}
          </button>

          {/* PR Campaigns – rollout management and audit */}
          <button
            className={`sidebar-item ${activeSection === 'pr-history' ? 'active' : ''}`}
            aria-label="PR Campaigns"
            onClick={() => handleSectionChange('pr-history')}
            title={isCollapsed ? 'PR Campaigns' : ''}
          >
            <span className="sidebar-icon" aria-hidden="true"><GitPullRequest size={18} strokeWidth={1.75} /></span>
            {!isCollapsed && <span className="sidebar-label">PR Campaigns</span>}
          </button>

          {/* CONFIGURATION Section Label */}
          {!isCollapsed && <div className="sidebar-section-label">Configuration</div>}

          {/* Repository Configs – flat first-class items (no parent grouping) */}
          {repoConfigSections.map(section => {
            const Icon = section.Icon;
            return (
              <button
                key={section.key}
                className={`sidebar-item ${activeSection === section.key ? 'active' : ''}`}
                aria-label={section.label}
                onClick={() => handleSectionChange(section.key)}
                title={isCollapsed ? section.label : ''}
              >
                <span className="sidebar-icon" aria-hidden="true"><Icon size={18} strokeWidth={1.75} /></span>
                {!isCollapsed && <span className="sidebar-label">{section.label}</span>}
              </button>
            );
          })}
        </div>

        {/* Bottom section: Project Configs – pinned to bottom, Jira-style */}
        {(projectType === 'standard' || projectType === 'rwx') && (
          <div className="mt-auto border-t border-slate-200 dark:border-slate-700 pt-4 space-y-1">
            <button
              className={`sidebar-item sidebar-group-header ${isProjectConfigActive ? 'active' : ''}`}
              aria-expanded={projectConfigOpen}
              aria-label="Project Configs"
              onClick={handleProjectConfigToggle}
              title={isCollapsed ? 'Project Configs' : ''}
            >
              <span className="sidebar-icon" aria-hidden="true"><Settings size={18} strokeWidth={1.75} /></span>
              {!isCollapsed && (
                <>
                  <span className="sidebar-label">Project Configs</span>
                  <span className="sidebar-group-arrow" aria-hidden="true">
                    {projectConfigOpen ? <ChevronDown size={16} strokeWidth={1.75} /> : <ChevronRight size={16} strokeWidth={1.75} />}
                  </span>
                </>
              )}
            </button>

            {/* Sub-items – shown when group is open */}
            {projectConfigOpen && (
              <div className={`sidebar-group-children${isCollapsed ? ' sidebar-group-children-collapsed' : ''}`}>
                {currentProjectConfigSections.map(section => {
                  const Icon = section.Icon;
                  return (
                    <button
                      key={section.key}
                      className={`sidebar-item sidebar-child-item ${activeSection === section.key ? 'active' : ''}`}
                      aria-label={section.label}
                      onClick={() => handleSectionChange(section.key)}
                      title={isCollapsed ? section.label : ''}
                    >
                      <span className="sidebar-icon" aria-hidden="true"><Icon size={16} strokeWidth={1.75} /></span>
                      {!isCollapsed && <span className="sidebar-label">{section.label}</span>}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </nav>
    </div>
  );
};

export default Sidebar;
