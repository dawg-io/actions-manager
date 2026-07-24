# Privacy Notice for ActionsManager Self-Hosted Beta

This notice describes the current self-hosted beta behavior. It is product documentation, not legal advice. Privacy terms for any future Cloud/SaaS or paid offering should be reviewed before launch.

## Where the self-hosted beta runs

The self-hosted beta runs on infrastructure controlled by the operator. ActionsManager stores application data in the user-configured database for that deployment. By default, the self-hosted container uses SQLite stored in the mounted application data volume; operators may configure PostgreSQL where supported.

## Data the application may store

Depending on how the application is used, stored data may include:

- GitHub account identifiers, usernames, avatar URLs, and related profile metadata.
- Repository names, organization or owner names, project configuration, workflow YAML, workflow state, and configuration metadata.
- Pull request metadata, branch names, workflow rollout state, drift-detection state, and audit or webhook metadata needed by enabled features.
- License tier metadata derived from a configured self-hosted `LICENSE_KEY`, when present.

## Secrets, tokens, and credentials

Repository secret values should not be stored locally by ActionsManager. Secret names or metadata may be tracked where needed to support repository and environment secret management.

Operators must protect GitHub OAuth credentials, saved personal access tokens, local environment variables, `.env.self-hosted`, database files, backups, webhook secrets, license keys, and any optional external API keys. Never commit a real `.env` file or token to source control.

## Telemetry and external calls

The self-hosted beta does not include documented product telemetry, crash reporting, or phone-home analytics. The application does call external services that the operator configures or explicitly uses, including GitHub APIs for authentication and repository/workflow operations.

## Backups and deletion

Self-hosted operators control database backups, retention, access, and deletion. Review backups before sharing logs or support bundles, because they may contain repository metadata, workflow YAML, pull request metadata, credentials metadata, and other configuration details.
