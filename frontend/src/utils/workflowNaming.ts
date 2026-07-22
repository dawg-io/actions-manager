export interface WorkflowAnalysis {
  technology: string | null;
  triggers: string[];
  actions: string[];
  branches: string[];
  isReusable: boolean;
}

export interface WorkflowNames {
  reusable: string;
  caller: string;
  technology: string | null;
}

export interface ReusableWorkflowNamesOptions {
  includeActions?: boolean;
  includeProjectPrefix?: boolean;
}

const extractBranches = (content: string): string[] => {
  const branchMatches =
    /branches:\s*\[(.*?)\]/.exec(content) ||
    /branches:\s*\n([\s\S]*?)(?=(?:\n\s*[a-z]|\n[a-z]|$))/.exec(content);
  if (!branchMatches) return [];
  const section = branchMatches[1];
  const branches: string[] = [];
  if (section.includes('main')) branches.push('main');
  if (section.includes('develop')) branches.push('develop');
  if (section.includes('feat')) branches.push('feature');
  if (section.includes('master')) branches.push('main');
  return branches;
};

export const analyzeWorkflowContent = (yamlContent: string): WorkflowAnalysis => {
  if (!yamlContent || typeof yamlContent !== 'string') {
    return { technology: null, triggers: [], actions: [], branches: [], isReusable: false };
  }

  const content = yamlContent.toLowerCase();
  const result: WorkflowAnalysis = {
    technology: null,
    triggers: [],
    actions: [],
    branches: [],
    isReusable: false,
  };

  result.isReusable = content.includes('workflow_call');

  const triggerPatterns: Record<string, RegExp> = {
    push: /on:[\s\S]*?push:/,
    pull_request: /on:[\s\S]*?pull_request:/,
    workflow_dispatch: /on:[\s\S]*?workflow_dispatch:/,
    schedule: /on:[\s\S]*?schedule:/,
    workflow_call: /on:[\s\S]*?workflow_call:/,
  };

  for (const [trigger, pattern] of Object.entries(triggerPatterns)) {
    if (pattern.test(content)) result.triggers.push(trigger);
  }

  result.branches = extractBranches(content);

  const techPatterns: Record<string, string[]> = {
    java: ['setup-java', 'maven', 'mvn ', 'gradle', './gradlew', 'pom.xml', 'build.gradle'],
    node: ['setup-node', 'npm', 'yarn', 'package.json', 'node.js'],
    python: ['setup-python', 'pip install', 'requirements.txt', 'python -m', 'pytest'],
    dotnet: ['setup-dotnet', 'dotnet ', '.csproj', 'nuget'],
    go: ['setup-go', 'go build', 'go test', 'go.mod'],
    rust: ['rust', 'cargo', 'cargo.toml'],
    docker: ['docker build', 'docker push', 'dockerfile', 'docker/build-push-action'],
    kubernetes: ['kubectl', 'kubernetes', 'k8s', 'helm'],
  };

  for (const [tech, patterns] of Object.entries(techPatterns)) {
    if (patterns.some(p => content.includes(p))) {
      result.technology = tech;
      break;
    }
  }

  const actionPatterns: Record<string, string[]> = {
    build: ['build', 'compile', 'mvn compile', 'npm run build', 'go build'],
    test: ['test', 'mvn test', 'npm test', 'pytest', 'go test', 'dotnet test'],
    deploy: ['deploy', 'deployment', 'kubectl apply', 'docker push'],
    package: ['package', 'mvn package', 'npm pack'],
    lint: ['lint', 'eslint', 'flake8', 'golangci-lint'],
    security: ['security', 'codeql', 'snyk', 'sonar', 'sonarqube', 'sonarcloud', 'sast', 'security-scan', 'vulnerability', 'dependency-check'],
    release: ['release', 'publish', 'npm publish'],
    scan: ['scan', 'sonar-scanner', 'sonarqube-scan', 'security-scan', 'vulnerability-scan'],
  };

  for (const [action, patterns] of Object.entries(actionPatterns)) {
    if (patterns.some(p => content.includes(p))) result.actions.push(action);
  }

  return result;
};

const selectActionLabel = (actions: string[]): string => {
  if (actions.includes('security') || actions.includes('scan')) {
    if (actions.includes('security') && actions.includes('scan')) return 'security_scan';
    return actions.includes('security') ? 'security' : 'scan';
  }
  if (actions.includes('build') && actions.includes('deploy')) return 'cicd';
  if (actions.includes('build') && actions.includes('test')) return 'build_test';
  return actions.slice(0, 2).join('_');
};

const selectTriggerLabel = (triggers: string[]): string | null => {
  if (triggers.includes('workflow_dispatch') && triggers.length === 1) return 'manual';
  if (triggers.includes('schedule')) return 'scheduled';
  if (triggers.includes('pull_request') && !triggers.includes('push')) return 'on_pr';
  if (triggers.includes('push')) return 'on_push';
  return null;
};

export const generateIntelligentName = (
  analysis: WorkflowAnalysis,
  options: {
    projectCode?: string;
    fallbackPrefix?: string;
    maxLength?: number;
    includeProjectCode?: boolean;
  } = {}
): string => {
  const { projectCode = '', fallbackPrefix = '', maxLength = 50, includeProjectCode = true } = options;
  const parts: string[] = [];

  if (includeProjectCode && projectCode) {
    parts.push(`AM_${projectCode.toUpperCase()}`);
  } else if (fallbackPrefix) {
    parts.push(fallbackPrefix);
  }

  if (analysis.technology) parts.push(analysis.technology);

  const actionPriority = ['security', 'scan', 'deploy', 'build', 'test', 'package', 'lint', 'release'];
  const sortedActions = [...analysis.actions].sort((a, b) => {
    const ai = actionPriority.indexOf(a);
    const bi = actionPriority.indexOf(b);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
  });

  if (sortedActions.length > 0) {
    parts.push(selectActionLabel(sortedActions));
  }

  if (!analysis.isReusable && analysis.triggers.length > 0) {
    const triggerLabel = selectTriggerLabel(analysis.triggers);
    if (triggerLabel) parts.push(triggerLabel);
  }

  let name = parts.join('_').toLowerCase()
    .replace(/[^a-z0-9_]/g, '_')
    .replace(/_+/g, '_')
    .replace(/(^_|_$)/g, '');

  if (!name || name.length < 3) {
    name = analysis.technology ? `${analysis.technology}_workflow` : 'workflow';
  }

  if (name.length > maxLength) {
    name = name.substring(0, maxLength).replace(/_[^_]*$/, '');
  }

  return name;
};

export const generateAIWorkflowName = (
  yamlContent: string,
  projectName = '',
  buildTypes: string[] = []
): string => {
  const analysis = analyzeWorkflowContent(yamlContent);

  if (!analysis.technology && buildTypes.length > 0) {
    const buildType = buildTypes[0].toLowerCase();
    if (buildType.includes('java') || buildType.includes('maven')) analysis.technology = 'java';
    else if (buildType.includes('node') || buildType.includes('npm')) analysis.technology = 'node';
    else if (buildType.includes('python')) analysis.technology = 'python';
    else if (buildType.includes('docker')) analysis.technology = 'docker';
  }

  return generateIntelligentName(analysis, {
    projectCode: projectName,
    includeProjectCode: false,
    fallbackPrefix: 'ai_generated',
  });
};

export const generateBuildDetectionName = (
  technology: string,
  buildTypeName: string,
  repository = ''
): string => {
  const tech = technology.toLowerCase().replace('.js', '').replace('/', '_');
  const buildType = buildTypeName.toLowerCase();

  let name = `${tech}_${buildType}`;

  if (buildType.includes('maven') || buildType.includes('gradle')) {
    name += '_cicd';
  } else if (buildType.includes('npm') || buildType.includes('node')) {
    name += '_pipeline';
  } else {
    name += '_build';
  }

  if (repository) {
    const repoName = repository.split('/').pop()!.toLowerCase()
      .replace(/[^a-z0-9]/g, '_')
      .substring(0, 15);
    name = `${repoName}_${name}`;
  }

  return name;
};

const detectTechnology = (
  primaryTech: string,
  includeActions: boolean
): { technology: string; workflowType: string } => {
  if (primaryTech.includes('maven') || primaryTech.includes('java'))
    return { technology: 'maven', workflowType: includeActions ? 'maven_cicd' : 'maven_build' };
  if (primaryTech.includes('node') || primaryTech.includes('npm') || primaryTech.includes('javascript'))
    return { technology: 'node', workflowType: includeActions ? 'node_pipeline' : 'node_build' };
  if (primaryTech.includes('python') || primaryTech.includes('pip'))
    return { technology: 'python', workflowType: includeActions ? 'python_cicd' : 'python_build' };
  if (primaryTech.includes('docker'))
    return { technology: 'docker', workflowType: includeActions ? 'docker_deploy' : 'docker_build' };
  if (primaryTech.includes('helm'))
    return { technology: 'helm', workflowType: includeActions ? 'helm_deploy' : 'helm_build' };
  if (primaryTech.includes('go'))
    return { technology: 'go', workflowType: includeActions ? 'go_cicd' : 'go_build' };
  if (primaryTech.includes('rust'))
    return { technology: 'rust', workflowType: includeActions ? 'rust_cicd' : 'rust_build' };
  if (primaryTech.includes('dotnet') || primaryTech.includes('c#'))
    return { technology: 'dotnet', workflowType: includeActions ? 'dotnet_cicd' : 'dotnet_build' };
  return { technology: '', workflowType: 'build_deploy' };
};

export const generateReusableWorkflowNames = (
  buildTypes: string[],
  projectCode: string,
  options: ReusableWorkflowNamesOptions = {}
): WorkflowNames => {
  const { includeActions = true, includeProjectPrefix = false } = options;

  let workflowType = 'build_deploy';
  let technology: string | null = null;

  if (buildTypes && buildTypes.length > 0) {
    const detected = detectTechnology(buildTypes[0].toLowerCase(), includeActions);
    if (detected.technology) {
      technology = detected.technology;
      workflowType = detected.workflowType;
    }
  }

  const projectPrefix = includeProjectPrefix ? `AM_${(projectCode || 'PROJECT').toUpperCase()}_` : '';

  return {
    reusable: `${projectPrefix}${workflowType}`,
    caller: `${projectPrefix}${workflowType}_caller`,
    technology,
  };
};

export const generateTemplateName = (
  templateType: string,
  buildType = '',
  projectCode = ''
): string => {
  const tech = buildType ? buildType.toLowerCase() : '';
  const project = projectCode ? `${projectCode} ` : '';

  switch (templateType) {
    case 'standard':
      return tech
        ? `${project}${tech.charAt(0).toUpperCase() + tech.slice(1)} CI/CD Pipeline`
        : `${project}CI/CD Pipeline`;
    case 'reusable':
      return tech
        ? `${project}${tech.charAt(0).toUpperCase() + tech.slice(1)} Reusable Workflow`
        : `${project}Reusable Build Workflow`;
    case 'build':
      return tech
        ? `${project}${tech.charAt(0).toUpperCase() + tech.slice(1)} Build Process`
        : `${project}Build Process`;
    default:
      return `${project}Workflow`;
  }
};
